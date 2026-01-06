"""
AI API Controller
提供 AI 文字處理功能（摘要/潤稿）
"""

from ninja_extra import api_controller, http_post
from ninja_jwt.authentication import AsyncJWTAuth
from ninja_extra.permissions import IsAuthenticated

from .schemas import AIProcessRequest, AIProcessResponse
from .ai_service import ai_service
from .ai_rate_limiter import ai_rate_limiter

import logging

logger = logging.getLogger('docs_app')

# AI API 速率限制設定
AI_RATE_LIMIT_REQUESTS = 10  # 每用戶最大請求數
AI_RATE_LIMIT_WINDOW = 60    # 時間窗口（秒）


@api_controller("/ai", tags=["ai"], auth=AsyncJWTAuth(), permissions=[IsAuthenticated])
class AIController:

    @http_post("/process", response=AIProcessResponse)
    async def process_text(self, payload: AIProcessRequest):
        """AI 文字處理（摘要/潤稿）"""
        user = self.context.request.auth

        # 速率限制檢查
        rate_key = f"ai:{user.id}"
        if not ai_rate_limiter.is_allowed(rate_key, AI_RATE_LIMIT_REQUESTS, AI_RATE_LIMIT_WINDOW):
            logger.warning(f"AI rate limit exceeded: user={user.id}")
            return AIProcessResponse(
                success=False,
                result="",
                action=payload.action,
                error="請求過於頻繁，請稍後再試"
            )

        try:
            result = await ai_service.process(payload.action, payload.text)

            logger.info(f"AI process: user={user.id}, action={payload.action}, "
                       f"input_len={len(payload.text)}, output_len={len(result)}")

            return AIProcessResponse(
                success=True,
                result=result,
                action=payload.action
            )
        except ValueError as e:
            return AIProcessResponse(
                success=False,
                result="",
                action=payload.action,
                error=str(e)
            )
        except RuntimeError as e:
            return AIProcessResponse(
                success=False,
                result="",
                action=payload.action,
                error=str(e)
            )
