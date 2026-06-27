"""
AI 服務模組
使用 Pydantic AI 提供文字摘要和潤稿功能（供應商可切換：NVIDIA NIM 或 Gemini）

依 settings.AI_PROVIDER 決定供應商，惰性建立 model / agent（首次使用時才需要 API key）。
process(action, text) 介面與回傳純文字維持不變，向下相容既有 ai_api.py 與前端。
"""

import logging

from django.conf import settings
from httpx import AsyncClient
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from .schemas import DocumentMetadata, ProofreadResult

logger = logging.getLogger('docs_app')

# 生成參數（temperature 偏低求穩定；max_tokens 預留較長回覆；timeout 防外部服務卡死）
AI_TEMPERATURE = 0.6
AI_MAX_TOKENS = 2048
AI_TIMEOUT_SECONDS = 60.0
SYSTEM_PROMPT = "你是專業中文寫作助手，一律使用繁體中文。"
PROOFREAD_SYSTEM_PROMPT = (
    "你是專業的繁體中文寫作校對助手。請仔細檢查使用者提供的文字，找出用詞、語法、"
    "流暢度、標點等問題，逐項給出原文片段、建議改寫與原因，並評估整體寫作品質分數（0-100）。"
    "original 必須與原文完全一致以利前端定位；若文字沒有明顯問題，issues 回傳空陣列並給高分。"
)
METADATA_SYSTEM_PROMPT = (
    "你是文件分析助手。請閱讀使用者提供的文件內容，產生結構化 metadata："
    "一句話摘要（summary，繁體中文）、3-5 個主題標籤（tags）、"
    "主要語言代碼（language，如 zh-Hant / en）、預估閱讀時間分鐘數（reading_time）。"
)

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

# 共用模型與 agent（惰性建立，避免 import 時就要求 API key）
_model: Model | None = None
_agent: Agent | None = None
_proofread_agent: Agent | None = None
_metadata_agent: Agent | None = None


def _get_api_key() -> str:
    """回傳當前供應商的 API key（未配置時為空字串）。"""
    if settings.AI_PROVIDER == 'gemini':
        return settings.GOOGLE_API_KEY
    return settings.NVIDIA_API_KEY


def _build_gemini_model() -> Model:
    """建立 Gemini（Google 原生 SDK）模型。

    - timeout 須透過自訂 httpx client 設定（ModelSettings.timeout 對 Google 不生效）。
    - thinking_budget=0 關閉思考：思考 token 會算進 max_tokens 預算，不關可能把回覆截斷。
    """
    return GoogleModel(
        settings.GEMINI_MODEL,
        provider=GoogleProvider(
            api_key=settings.GOOGLE_API_KEY,
            http_client=AsyncClient(timeout=AI_TIMEOUT_SECONDS),
        ),
        settings=GoogleModelSettings(
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS,
            google_thinking_config={"thinking_budget": 0},
        ),
    )


def _build_nvidia_model() -> Model:
    """建立 NVIDIA NIM（OpenAI 相容端點）模型。"""
    return OpenAIChatModel(
        settings.NVIDIA_MODEL,
        provider=OpenAIProvider(
            base_url=settings.NVIDIA_BASE_URL,
            api_key=settings.NVIDIA_API_KEY,
        ),
        settings=ModelSettings(
            temperature=AI_TEMPERATURE,
            max_tokens=AI_MAX_TOKENS,
            timeout=AI_TIMEOUT_SECONDS,
        ),
    )


def _get_model() -> Model:
    """惰性建立共用模型（依 settings.AI_PROVIDER 切換供應商，所有 agent 共用）。"""
    global _model
    if _model is None:
        if settings.AI_PROVIDER == 'gemini':
            _model = _build_gemini_model()
        else:
            _model = _build_nvidia_model()
    return _model


def _get_agent() -> Agent:
    """惰性建立摘要 / 潤稿共用 agent。"""
    global _agent
    if _agent is None:
        _agent = Agent(_get_model(), system_prompt=SYSTEM_PROMPT)
    return _agent


def _get_proofread_agent() -> Agent:
    """惰性建立結構化校對 agent（output_type=ProofreadResult，自動驗證 + 重試）。"""
    global _proofread_agent
    if _proofread_agent is None:
        _proofread_agent = Agent(
            _get_model(),
            output_type=ProofreadResult,
            system_prompt=PROOFREAD_SYSTEM_PROMPT,
        )
    return _proofread_agent


def _get_metadata_agent() -> Agent:
    """惰性建立文件 metadata agent（output_type=DocumentMetadata，自動驗證 + 重試）。"""
    global _metadata_agent
    if _metadata_agent is None:
        _metadata_agent = Agent(
            _get_model(),
            output_type=DocumentMetadata,
            system_prompt=METADATA_SYSTEM_PROMPT,
        )
    return _metadata_agent


class AIService:
    """AI 服務（摘要 / 潤稿），底層為 Pydantic AI agent。"""

    async def process(self, action: str, text: str) -> str:
        """處理 AI 請求（異步），回傳純文字結果。"""
        if action not in PROMPTS:
            raise ValueError(f"Unknown action: {action}")

        if not text.strip():
            raise ValueError("Text cannot be empty")

        if not _get_api_key():
            raise RuntimeError("AI 服務未配置")

        # 限制輸入長度（避免 token 過多）
        max_chars = 5000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        prompt = PROMPTS[action].format(text=text)

        try:
            result = await _get_agent().run(prompt)
            return result.output
        except ModelHTTPError as e:
            if getattr(e, "status_code", None) == 429:
                logger.warning("AI API quota exhausted")
                raise RuntimeError("API 配額已用盡，請稍後再試")
            logger.error(f"AI API error: {e}")
            raise RuntimeError("AI 服務暫時無法使用")
        except Exception as e:
            logger.error(f"AI unexpected error: {e}")
            raise RuntimeError(f"AI 處理失敗：{str(e)}")

    async def proofread(self, text: str) -> ProofreadResult:
        """結構化校對：回傳 ProofreadResult（issues + overall_score）。

        相較 process() 回傳純文字，本方法透過 output_type=ProofreadResult
        取得型別安全的結構化建議（驗證 / 重試由 Pydantic AI 處理）。
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        if not _get_api_key():
            raise RuntimeError("AI 服務未配置")

        # 限制輸入長度（避免 token 過多）
        max_chars = 5000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        try:
            result = await _get_proofread_agent().run(text)
            return result.output
        except ModelHTTPError as e:
            if getattr(e, "status_code", None) == 429:
                logger.warning("AI API quota exhausted")
                raise RuntimeError("API 配額已用盡，請稍後再試")
            logger.error(f"AI API error: {e}")
            raise RuntimeError("AI 服務暫時無法使用")
        except Exception as e:
            logger.error(f"AI proofread unexpected error: {e}")
            raise RuntimeError(f"AI 處理失敗：{str(e)}")

    async def generate_metadata(self, text: str) -> DocumentMetadata:
        """產生文件 metadata：回傳 DocumentMetadata（summary / tags / language / reading_time）。"""
        if not text.strip():
            raise ValueError("Text cannot be empty")

        if not _get_api_key():
            raise RuntimeError("AI 服務未配置")

        # 限制輸入長度（避免 token 過多）
        max_chars = 5000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        try:
            result = await _get_metadata_agent().run(text)
            return result.output
        except ModelHTTPError as e:
            if getattr(e, "status_code", None) == 429:
                logger.warning("AI API quota exhausted")
                raise RuntimeError("API 配額已用盡，請稍後再試")
            logger.error(f"AI API error: {e}")
            raise RuntimeError("AI 服務暫時無法使用")
        except Exception as e:
            logger.error(f"AI metadata unexpected error: {e}")
            raise RuntimeError(f"AI 處理失敗：{str(e)}")


# 單例
ai_service = AIService()
