"""
WebSocket 速率限制器
使用 Redis Sorted Set 實現滑動窗口算法
"""

import time
import logging
import redis.asyncio as redis
from django.conf import settings
from typing import Tuple, Dict, Any

logger = logging.getLogger('docs_app')


class RateLimiter:
    """
    滑動窗口速率限制器

    使用 Redis Sorted Set 追蹤消息時間戳：
    - Key: ws:ratelimit:user:{user_id}:doc:{document_id}
    - Member: 消息時間戳（毫秒）
    - Score: 消息時間戳（毫秒）

    滑動窗口算法：
    1. 移除窗口外的舊時間戳
    2. 計算窗口內的消息數量
    3. 如果未超限，添加當前時間戳
    """

    def __init__(self):
        self.redis_host = getattr(settings, 'REDIS_HOST', 'django-redis')
        self.redis_port = int(getattr(settings, 'REDIS_PORT', 6379))
        self.max_messages = getattr(
            settings, 'WEBSOCKET_RATE_LIMIT_MESSAGES', 30
        )
        self.window_seconds = getattr(
            settings, 'WEBSOCKET_RATE_LIMIT_WINDOW', 10
        )
        self._redis = None

    async def get_redis(self):
        """獲取 Redis 連接（懶加載）"""
        if self._redis is None:
            self._redis = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True
            )
        return self._redis

    def _get_key(self, user_id: int, document_id: str) -> str:
        """生成速率限制的 Redis key"""
        return f"ws:ratelimit:user:{user_id}:doc:{document_id}"

    async def is_allowed(
        self, user_id: int, document_id: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        檢查是否允許發送消息

        Args:
            user_id: 用戶 ID
            document_id: 文檔 ID

        Returns:
            tuple: (allowed: bool, info: dict)
            info 包含:
            - remaining: 剩餘額度
            - limit: 最大消息數
            - window: 窗口大小（秒）
            - retry_after: 如果被限制，多久後可重試（秒）
        """
        r = await self.get_redis()
        key = self._get_key(user_id, document_id)
        now_ms = int(time.time() * 1000)
        window_start_ms = now_ms - (self.window_seconds * 1000)

        # Lua 腳本：原子性操作
        lua_script = """
        local key = KEYS[1]
        local now_ms = tonumber(ARGV[1])
        local window_start_ms = tonumber(ARGV[2])
        local max_messages = tonumber(ARGV[3])
        local window_ms = tonumber(ARGV[4])

        -- 移除過期的時間戳
        redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start_ms)

        -- 計算當前窗口內的消息數
        local count = redis.call('ZCARD', key)

        if count >= max_messages then
            -- 獲取最早的消息時間戳，計算何時可以再次發送
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            local retry_after = 0
            if #oldest > 0 then
                retry_after = oldest[2] + window_ms - now_ms
                if retry_after < 0 then
                    retry_after = 0
                end
            end
            return {0, count, retry_after}
        end

        -- 添加當前時間戳（使用時間戳作為 member 確保唯一性）
        redis.call('ZADD', key, now_ms, now_ms)
        -- 設置 key 過期時間（略大於窗口，確保舊數據被清理）
        redis.call('EXPIRE', key, math.ceil(window_ms / 1000) + 1)

        return {1, count + 1, 0}
        """

        try:
            result = await r.eval(
                lua_script, 1, key,
                now_ms, window_start_ms,
                self.max_messages, self.window_seconds * 1000
            )

            allowed = result[0] == 1
            current_count = result[1]
            retry_after_ms = result[2]

            info = {
                'remaining': max(0, self.max_messages - current_count),
                'limit': self.max_messages,
                'window': self.window_seconds,
                'retry_after': retry_after_ms / 1000 if retry_after_ms > 0 else 0
            }

            if not allowed:
                logger.warning(
                    f"用戶 {user_id} 在文檔 {document_id} 觸發速率限制: "
                    f"{current_count}/{self.max_messages} 消息在 {self.window_seconds} 秒內, "
                    f"retry_after={info['retry_after']:.2f}s"
                )

            return allowed, info

        except Exception as e:
            logger.error(f"速率限制檢查時發生錯誤: {str(e)}")
            # 發生錯誤時允許通過（fail-open），避免影響正常使用
            return True, {
                'remaining': self.max_messages,
                'limit': self.max_messages,
                'window': self.window_seconds,
                'retry_after': 0
            }

    async def get_current_count(self, user_id: int, document_id: str) -> int:
        """
        獲取當前窗口內的消息數量

        Args:
            user_id: 用戶 ID
            document_id: 文檔 ID

        Returns:
            int: 當前窗口內的消息數量
        """
        try:
            r = await self.get_redis()
            key = self._get_key(user_id, document_id)
            now_ms = int(time.time() * 1000)
            window_start_ms = now_ms - (self.window_seconds * 1000)

            # 先清理過期的
            await r.zremrangebyscore(key, '-inf', window_start_ms)
            return await r.zcard(key)
        except Exception as e:
            logger.error(f"獲取消息計數時發生錯誤: {str(e)}")
            return 0

    async def reset(self, user_id: int, document_id: str):
        """
        重置用戶在特定文檔的速率限制（用於測試或管理）

        Args:
            user_id: 用戶 ID
            document_id: 文檔 ID
        """
        try:
            r = await self.get_redis()
            key = self._get_key(user_id, document_id)
            await r.delete(key)
            logger.info(f"已重置用戶 {user_id} 在文檔 {document_id} 的速率限制")
        except Exception as e:
            logger.error(f"重置速率限制時發生錯誤: {str(e)}")


# 全局實例
rate_limiter = RateLimiter()
