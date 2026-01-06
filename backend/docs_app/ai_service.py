"""
AI 服務模組
使用 Google Gemini API 提供文字摘要和潤稿功能
"""

from google import genai
from google.genai.errors import APIError
from django.conf import settings
import logging

logger = logging.getLogger('docs_app')

# Prompt 模板
PROMPTS = {
    "summarize": """請將以下文字摘要成精簡的重點：

{text}

要求：
- 保留核心訊息
- 使用繁體中文
- 條列式呈現（如適用）
- 長度約為原文的 1/3""",

    "polish": """請潤飾以下文字，改善表達方式：

{text}

要求：
- 保持原意不變
- 改善語句流暢度
- 修正可能的語法問題
- 使用繁體中文
- 直接輸出潤飾後的文字，不要加任何說明"""
}


class AIService:
    """AI 服務（使用延遲初始化避免模組載入時 settings 未就緒）"""
    _initialized = False
    _client = None

    def _ensure_initialized(self):
        """延遲初始化：確保 Gemini Client 已建立"""
        if not self._initialized:
            if settings.GEMINI_API_KEY:
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
            self._initialized = True

    async def process(self, action: str, text: str) -> str:
        """處理 AI 請求（異步版本）"""
        self._ensure_initialized()

        if action not in PROMPTS:
            raise ValueError(f"Unknown action: {action}")

        if not text.strip():
            raise ValueError("Text cannot be empty")

        if not self._client:
            raise RuntimeError("AI 服務未配置")

        # 限制輸入長度（避免 token 過多）
        max_chars = 5000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        prompt = PROMPTS[action].format(text=text)

        try:
            response = await self._client.aio.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt
            )
            return response.text
        except APIError as e:
            if e.code == 429:
                logger.warning("Gemini API quota exhausted")
                raise RuntimeError("API 配額已用盡，請稍後再試")
            logger.error(f"Google API error: {e}")
            raise RuntimeError("AI 服務暫時無法使用")
        except Exception as e:
            logger.error(f"Gemini API unexpected error: {e}")
            raise RuntimeError(f"AI 處理失敗：{str(e)}")


# 單例
ai_service = AIService()
