"""
AI API 速率限制器
使用 Redis 實現簡單的滑動窗口算法（同步版本）
"""

import time
import uuid
import logging
from .redis_pool import get_sync_redis

logger = logging.getLogger('docs_app')

# Lua 腳本：原子性地清除過期記錄、檢查額度並記錄本次請求。
# 若拆成「先查數量、再另外 ZADD」，並發請求可能同時通過檢查而超出額度。
SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_start_ms = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])
local window_seconds = tonumber(ARGV[4])
local member = ARGV[5]

-- 移除過期的時間戳
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start_ms)

-- 計算當前窗口內的請求數
local count = redis.call('ZCARD', key)
if count >= max_requests then
    return 0
end

-- 記錄本次請求（score 為時間戳；member 由呼叫端產生、保證唯一）
redis.call('ZADD', key, now_ms, member)
-- 設置過期時間（略大於窗口，確保舊數據被清理）
redis.call('EXPIRE', key, window_seconds + 1)
return 1
"""


class AIRateLimiter:
    """
    AI API 速率限制器（同步版本）

    使用 Redis Sorted Set 追蹤請求時間戳
    """

    def _get_redis(self):
        """獲取 Redis 連接（委託給統一連接池）"""
        return get_sync_redis()

    def is_allowed(
        self, key: str, max_requests: int, window_seconds: int
    ) -> bool:
        """
        檢查是否允許請求

        Args:
            key: 速率限制的鍵（如 "ai:user_id"）
            max_requests: 時間窗口內最大請求數
            window_seconds: 時間窗口大小（秒）

        Returns:
            bool: 是否允許請求
        """
        try:
            r = self._get_redis()
            now_ms = int(time.time() * 1000)
            window_start_ms = now_ms - (window_seconds * 1000)
            # member 必須唯一：只用時間戳的話，同一毫秒內的多個請求會寫到同一個 member、只算一次
            member = f"{now_ms}-{uuid.uuid4().hex}"

            allowed = r.eval(
                SLIDING_WINDOW_SCRIPT, 1, key,
                now_ms, window_start_ms, max_requests, window_seconds, member
            ) == 1

            if not allowed:
                logger.warning(
                    f"AI rate limit exceeded: key={key}, limit={max_requests}/{window_seconds}s"
                )
            return allowed

        except Exception as e:
            logger.error(f"AI rate limiter error: {str(e)}")
            # 發生錯誤時允許通過（fail-open）
            return True


# 單例
ai_rate_limiter = AIRateLimiter()
