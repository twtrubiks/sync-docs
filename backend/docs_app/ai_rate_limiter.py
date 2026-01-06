"""
AI API 速率限制器
使用 Redis 實現簡單的滑動窗口算法（同步版本）
"""

import time
import logging
import redis
from django.conf import settings

logger = logging.getLogger('docs_app')


class AIRateLimiter:
    """
    AI API 速率限制器（同步版本）

    使用 Redis Sorted Set 追蹤請求時間戳
    """

    def __init__(self):
        self.redis_host = getattr(settings, 'REDIS_HOST', 'django-redis')
        self.redis_port = int(getattr(settings, 'REDIS_PORT', 6379))
        self._redis = None

    def _get_redis(self):
        """獲取 Redis 連接（懶加載）"""
        if self._redis is None:
            self._redis = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                decode_responses=True
            )
        return self._redis

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

            # 使用 pipeline 原子操作
            pipe = r.pipeline()
            # 移除過期的時間戳
            pipe.zremrangebyscore(key, '-inf', window_start_ms)
            # 計算當前窗口內的請求數
            pipe.zcard(key)
            results = pipe.execute()

            current_count = results[1]

            if current_count >= max_requests:
                logger.warning(
                    f"AI rate limit exceeded: key={key}, "
                    f"count={current_count}/{max_requests}"
                )
                return False

            # 添加當前時間戳
            r.zadd(key, {str(now_ms): now_ms})
            # 設置過期時間
            r.expire(key, window_seconds + 1)

            return True

        except Exception as e:
            logger.error(f"AI rate limiter error: {str(e)}")
            # 發生錯誤時允許通過（fail-open）
            return True


# 單例
ai_rate_limiter = AIRateLimiter()
