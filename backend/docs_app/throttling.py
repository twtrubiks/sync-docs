"""
認證端點限流
複用 ai_rate_limiter 的 Redis 滑動窗口，以 IP 為 key 防護登入/註冊暴力破解
"""

import logging

from django.conf import settings
from ninja.throttling import BaseThrottle

from .ai_rate_limiter import ai_rate_limiter

logger = logging.getLogger('docs_app')


class AuthRateThrottle(BaseThrottle):
    """
    登入/註冊端點的 IP 滑動窗口限流

    掛在 ninja 操作的 throttle 參數上，會在請求 body 解析「之前」執行——
    這點很關鍵：ninja_jwt 的密碼驗證發生在 schema 驗證階段，
    若限流放在端點函數內，失敗的登入嘗試（401）根本不會經過限流計數。

    以 REMOTE_ADDR 為 key：本專案後端未經信任的反向代理直接曝露（8000 埠），
    信任 X-Forwarded-For 反而讓攻擊者偽造 IP 繞過限流或鎖定他人。
    若部署在信任的反向代理後方，需改用代理傳遞的真實 client IP。
    """

    def __init__(self, scope: str, max_requests: int, window_seconds: int):
        """
        Args:
            scope: 限流範圍標籤（如 'login'、'register'），構成 Redis key 前綴
            max_requests: 窗口內最大請求數
            window_seconds: 窗口大小（秒）
        """
        self.scope = scope
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def allow_request(self, request) -> bool:
        # 測試環境透過此設定關閉，避免測試套件的大量登入互相干擾
        if not getattr(settings, 'AUTH_RATE_LIMIT_ENABLED', True):
            return True

        ip = request.META.get('REMOTE_ADDR', 'unknown')
        allowed = ai_rate_limiter.is_allowed(
            f"{self.scope}:{ip}", self.max_requests, self.window_seconds
        )
        if not allowed:
            logger.warning(f"{self.scope} 端點觸發限流: ip={ip}")
        return allowed
