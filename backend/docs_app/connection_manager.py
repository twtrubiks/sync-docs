"""
WebSocket 連接管理器
使用 Redis 追蹤並限制用戶連接數
"""

import asyncio
import logging

import redis.asyncio as redis
from django.conf import settings

logger = logging.getLogger('docs_app')


class ConnectionManager:
    """
    管理 WebSocket 連接計數和限制

    使用 Redis SET 追蹤每用戶的活躍連接：
    - Key: ws:connections:user:{user_id}
    - Value: SET of channel_names

    使用 Lua 腳本確保操作原子性
    """

    # 連接記錄 TTL（秒）- 5 分鐘，與 presence 系統一致
    CONNECTION_TTL = int(getattr(settings, 'WEBSOCKET_CONNECTION_TTL', 300))

    # 移除連接時的最大重試次數
    REMOVE_MAX_RETRIES = 3

    def __init__(self):
        self.redis_host = getattr(settings, 'REDIS_HOST', 'django-redis')
        self.redis_port = int(getattr(settings, 'REDIS_PORT', 6379))
        self.max_connections = getattr(
            settings, 'WEBSOCKET_MAX_CONNECTIONS_PER_USER', 5
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

    def _get_key(self, user_id: int) -> str:
        """生成用戶連接追蹤的 Redis key"""
        return f"ws:connections:user:{user_id}"

    async def can_connect(self, user_id: int) -> bool:
        """
        檢查用戶是否可以建立新連接

        Args:
            user_id: 用戶 ID

        Returns:
            bool: True 表示可以連接，False 表示已達上限
        """
        r = await self.get_redis()
        key = self._get_key(user_id)
        count = await r.scard(key)
        return count < self.max_connections

    async def add_connection(self, user_id: int, channel_name: str) -> bool:
        """
        嘗試添加連接

        使用 Lua 腳本確保原子性：檢查並添加在同一操作中完成

        Args:
            user_id: 用戶 ID
            channel_name: WebSocket channel 名稱

        Returns:
            bool: True 表示成功添加，False 表示已達上限
        """
        r = await self.get_redis()
        key = self._get_key(user_id)

        # Lua 腳本：原子性檢查並添加
        lua_script = """
        local key = KEYS[1]
        local channel = ARGV[1]
        local max_conn = tonumber(ARGV[2])
        local ttl = tonumber(ARGV[3])

        local count = redis.call('SCARD', key)
        if count >= max_conn then
            return 0
        end
        redis.call('SADD', key, channel)
        -- 設置 TTL 過期，防止異常情況下的數據殘留
        redis.call('EXPIRE', key, ttl)
        return 1
        """

        try:
            result = await r.eval(
                lua_script, 1, key,
                channel_name, self.max_connections, self.CONNECTION_TTL
            )
            success = result == 1

            if success:
                logger.debug(
                    f"用戶 {user_id} 添加連接 {channel_name}，"
                    f"當前連接數: {await self.get_connection_count(user_id)}"
                )
            else:
                logger.warning(
                    f"用戶 {user_id} 連接數已達上限 {self.max_connections}，"
                    f"拒絕新連接 {channel_name}"
                )

            return success
        except Exception as e:
            logger.error(f"添加連接時發生錯誤: {str(e)}")
            # 發生錯誤時拒絕連接（fail-closed），確保連接追蹤一致性
            return False

    async def remove_connection(self, user_id: int, channel_name: str):
        """
        移除連接（帶重試邏輯）

        Args:
            user_id: 用戶 ID
            channel_name: WebSocket channel 名稱
        """
        for attempt in range(self.REMOVE_MAX_RETRIES):
            try:
                r = await self.get_redis()
                key = self._get_key(user_id)
                await r.srem(key, channel_name)
                logger.debug(
                    f"用戶 {user_id} 移除連接 {channel_name}，"
                    f"剩餘連接數: {await self.get_connection_count(user_id)}"
                )
                return  # 成功，退出
            except Exception as e:
                logger.error(
                    f"移除連接時發生錯誤 (嘗試 {attempt + 1}/{self.REMOVE_MAX_RETRIES}): "
                    f"{str(e)}"
                )
                if attempt < self.REMOVE_MAX_RETRIES - 1:
                    # 指數退避重試
                    await asyncio.sleep(0.1 * (attempt + 1))

        # 所有重試都失敗
        logger.warning(
            f"無法移除用戶 {user_id} 的連接 {channel_name}，"
            f"已重試 {self.REMOVE_MAX_RETRIES} 次"
        )

    async def get_connection_count(self, user_id: int) -> int:
        """
        獲取用戶當前連接數

        Args:
            user_id: 用戶 ID

        Returns:
            int: 當前連接數
        """
        try:
            r = await self.get_redis()
            key = self._get_key(user_id)
            return await r.scard(key)
        except Exception as e:
            logger.error(f"獲取連接數時發生錯誤: {str(e)}")
            return 0

    async def clear_user_connections(self, user_id: int):
        """
        清除用戶的所有連接記錄（用於測試或管理）

        Args:
            user_id: 用戶 ID
        """
        try:
            r = await self.get_redis()
            key = self._get_key(user_id)
            await r.delete(key)
            logger.info(f"已清除用戶 {user_id} 的所有連接記錄")
        except Exception as e:
            logger.error(f"清除連接記錄時發生錯誤: {str(e)}")

    async def refresh_connection(self, user_id: int, channel_name: str):
        """
        刷新連接 TTL（心跳用）

        當連接活躍時調用此方法延長 TTL，防止活躍連接因 TTL 過期被清除。

        Args:
            user_id: 用戶 ID
            channel_name: WebSocket channel 名稱
        """
        try:
            r = await self.get_redis()
            key = self._get_key(user_id)

            # 只有當 channel 存在時才刷新 TTL
            if await r.sismember(key, channel_name):
                await r.expire(key, self.CONNECTION_TTL)
                logger.debug(f"刷新用戶 {user_id} 的連接 TTL")
        except Exception as e:
            logger.error(f"刷新連接 TTL 時發生錯誤: {str(e)}")


# 全局實例
connection_manager = ConnectionManager()
