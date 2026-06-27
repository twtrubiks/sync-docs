"""
AI API Controller
提供 AI 文字處理功能（摘要/潤稿）
"""

from ninja_extra import api_controller, http_post
from ninja_jwt.authentication import AsyncJWTAuth
from ninja_extra.permissions import IsAuthenticated

from .schemas import (
    AIProcessRequest,
    AIProcessResponse,
    AskRequest,
    AskResponse,
    MetadataRequest,
    MetadataResponse,
    ProofreadRequest,
    ProofreadResponse,
)
from .ai_service import ai_service
from .ai_rate_limiter import ai_rate_limiter

import logging

logger = logging.getLogger('docs_app')

# AI API 速率限制設定
AI_RATE_LIMIT_REQUESTS = 10  # 每用戶最大請求數
AI_RATE_LIMIT_WINDOW = 60    # 時間窗口（秒）


@api_controller("/ai", tags=["ai"], auth=AsyncJWTAuth(), permissions=[IsAuthenticated])
class AIController:

    # 註：摘要/潤稿前端已改走 WebSocket 串流逐字輸出（consumers.py 的 ai_stream），
    # 此 HTTP 端點不再被前端呼叫；保留為 REST 對等 API（有測試 test_ai_api.py），暫不移除。
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

    @http_post("/proofread", response=ProofreadResponse)
    async def proofread_text(self, payload: ProofreadRequest):
        """AI 結構化校對（回傳逐項寫作建議 + 整體分數）"""
        user = self.context.request.auth

        # 速率限制檢查（與 /process 共用同一額度）
        rate_key = f"ai:{user.id}"
        if not ai_rate_limiter.is_allowed(rate_key, AI_RATE_LIMIT_REQUESTS, AI_RATE_LIMIT_WINDOW):
            logger.warning(f"AI rate limit exceeded: user={user.id}")
            return ProofreadResponse(success=False, error="請求過於頻繁，請稍後再試")

        try:
            result = await ai_service.proofread(payload.text)

            logger.info(f"AI proofread: user={user.id}, input_len={len(payload.text)}, "
                       f"issues={len(result.issues)}, score={result.overall_score}")

            return ProofreadResponse(success=True, result=result)
        except ValueError as e:
            return ProofreadResponse(success=False, error=str(e))
        except RuntimeError as e:
            return ProofreadResponse(success=False, error=str(e))

    @http_post("/metadata", response=MetadataResponse)
    async def generate_metadata(self, payload: MetadataRequest):
        """AI 文件 metadata（摘要 / 標籤 / 語言 / 閱讀時間）"""
        user = self.context.request.auth

        # 速率限制檢查（與 /process 共用同一額度）
        rate_key = f"ai:{user.id}"
        if not ai_rate_limiter.is_allowed(rate_key, AI_RATE_LIMIT_REQUESTS, AI_RATE_LIMIT_WINDOW):
            logger.warning(f"AI rate limit exceeded: user={user.id}")
            return MetadataResponse(success=False, error="請求過於頻繁，請稍後再試")

        try:
            result = await ai_service.generate_metadata(payload.text)

            logger.info(f"AI metadata: user={user.id}, input_len={len(payload.text)}, "
                       f"tags={len(result.tags)}, reading_time={result.reading_time}")

            return MetadataResponse(success=True, result=result)
        except ValueError as e:
            return MetadataResponse(success=False, error=str(e))
        except RuntimeError as e:
            return MetadataResponse(success=False, error=str(e))

    # 註：文件問答前端已改走 WebSocket 串流逐字輸出（consumers.py 的 ai_ask_stream），
    # 此 HTTP 端點不再被前端呼叫；保留為 REST 對等 API（有測試 test_ai_api.py），暫不移除。
    @http_post("/ask", response=AskResponse)
    async def ask_document(self, payload: AskRequest):
        """AI 文件問答（依據整份文件內容回答問題）"""
        user = self.context.request.auth

        # 速率限制檢查（與 /process 共用同一額度）
        rate_key = f"ai:{user.id}"
        if not ai_rate_limiter.is_allowed(rate_key, AI_RATE_LIMIT_REQUESTS, AI_RATE_LIMIT_WINDOW):
            logger.warning(f"AI rate limit exceeded: user={user.id}")
            return AskResponse(success=False, error="請求過於頻繁，請稍後再試")

        try:
            answer = await ai_service.ask(payload.question, payload.document_text)

            logger.info(f"AI ask: user={user.id}, question_len={len(payload.question)}, "
                       f"doc_len={len(payload.document_text)}, answer_len={len(answer)}")

            return AskResponse(success=True, answer=answer)
        except ValueError as e:
            return AskResponse(success=False, error=str(e))
        except RuntimeError as e:
            return AskResponse(success=False, error=str(e))
