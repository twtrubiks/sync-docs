"""
AI API 測試
使用單元測試方式測試 AIService 和 AIRateLimiter

AIService 行為測試以 TestModel / FunctionModel override agent，全程不打外部 API。
"""

import pytest
from unittest.mock import patch, MagicMock
from django.test import override_settings
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from docs_app import ai_service as ai_service_module
from docs_app.ai_service import AIService, _get_agent, _get_model
from docs_app.ai_rate_limiter import AIRateLimiter
from docs_app.schemas import AIProcessRequest, AIProcessResponse

# 使用 pytest-django 的 db fixture 來確保資料庫在測試之間是乾淨的
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_ai_globals():
    """每個測試前後重置模組級單例，避免供應商切換互相污染。"""
    ai_service_module._model = None
    ai_service_module._agent = None
    yield
    ai_service_module._model = None
    ai_service_module._agent = None


class TestAIService:
    """AI Service 單元測試（以 TestModel / FunctionModel override agent，全程不打 API）"""

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_process_summarize(self):
        """測試摘要功能"""
        with _get_agent().override(model=TestModel(custom_output_text="這是摘要結果")):
            result = await AIService().process('summarize', '測試文字')
            assert result == "這是摘要結果"

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_process_polish(self):
        """測試潤稿功能"""
        with _get_agent().override(model=TestModel(custom_output_text="潤飾後的文字")):
            result = await AIService().process('polish', '原始文字')
            assert result == "潤飾後的文字"

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_empty_text_error(self):
        """測試空文字錯誤"""
        with pytest.raises(ValueError, match="Text cannot be empty"):
            await AIService().process('summarize', '')

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_invalid_action_error(self):
        """測試無效操作錯誤"""
        with pytest.raises(ValueError, match="Unknown action"):
            await AIService().process('invalid', '文字')

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='')
    async def test_api_not_configured_error(self):
        """測試 API Key 未配置錯誤"""
        with pytest.raises(RuntimeError, match="AI 服務未配置"):
            await AIService().process('summarize', '文字')

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_text_truncation(self):
        """測試文字長度限制（超過 5000 字元會被截斷後才送進 agent）"""
        captured = {}

        async def capture_fn(messages, info):
            for message in messages:
                for part in message.parts:
                    if isinstance(part, UserPromptPart):
                        captured['prompt'] = str(part.content)
            return ModelResponse(parts=[TextPart('結果')])

        long_text = 'A' * 6000
        with _get_agent().override(model=FunctionModel(capture_fn)):
            await AIService().process('summarize', long_text)

        # 送進 agent 的 prompt 應含截斷省略號
        assert '...' in captured['prompt']

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='nv-key')
    def test_nvidia_builds_openai_model(self):
        """nvidia 供應商建立 OpenAIChatModel（不打 API）"""
        from pydantic_ai.models.openai import OpenAIChatModel
        assert isinstance(_get_model(), OpenAIChatModel)

    @override_settings(AI_PROVIDER='gemini', GOOGLE_API_KEY='g-key')
    def test_gemini_builds_google_model(self):
        """gemini 供應商建立 GoogleModel（不打 API）"""
        from pydantic_ai.models.google import GoogleModel
        assert isinstance(_get_model(), GoogleModel)

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='nv-key')
    def test_model_is_cached(self):
        """惰性單例：重複呼叫回傳同一實例"""
        assert _get_model() is _get_model()


class TestAIRateLimiter:
    """AI Rate Limiter 單元測試"""

    def test_is_allowed_returns_true_when_under_limit(self):
        """測試在限制內時返回 True"""
        with patch.object(AIRateLimiter, '_get_redis') as mock_redis:
            mock_r = MagicMock()
            mock_pipe = MagicMock()
            mock_pipe.execute.return_value = [None, 0]  # 0 個請求
            mock_r.pipeline.return_value = mock_pipe
            mock_redis.return_value = mock_r

            limiter = AIRateLimiter()
            result = limiter.is_allowed('test_key', 10, 60)

            assert result is True

    def test_is_allowed_returns_false_when_over_limit(self):
        """測試超過限制時返回 False"""
        with patch.object(AIRateLimiter, '_get_redis') as mock_redis:
            mock_r = MagicMock()
            mock_pipe = MagicMock()
            mock_pipe.execute.return_value = [None, 10]  # 已達到 10 個請求的限制
            mock_r.pipeline.return_value = mock_pipe
            mock_redis.return_value = mock_r

            limiter = AIRateLimiter()
            result = limiter.is_allowed('test_key', 10, 60)

            assert result is False

    def test_is_allowed_fail_open_on_error(self):
        """測試發生錯誤時允許通過（fail-open）"""
        with patch.object(AIRateLimiter, '_get_redis') as mock_redis:
            mock_redis.side_effect = Exception("Redis connection error")

            limiter = AIRateLimiter()
            result = limiter.is_allowed('test_key', 10, 60)

            # 發生錯誤時應該返回 True（fail-open）
            assert result is True


class TestAISchemas:
    """AI Schema 驗證測試"""

    def test_ai_process_request_valid_summarize(self):
        """測試有效的摘要請求"""
        request = AIProcessRequest(action='summarize', text='測試文字')
        assert request.action == 'summarize'
        assert request.text == '測試文字'

    def test_ai_process_request_valid_polish(self):
        """測試有效的潤稿請求"""
        request = AIProcessRequest(action='polish', text='測試文字')
        assert request.action == 'polish'
        assert request.text == '測試文字'

    def test_ai_process_request_invalid_action(self):
        """測試無效的操作類型"""
        with pytest.raises(ValidationError):
            AIProcessRequest(action='invalid', text='測試文字')

    def test_ai_process_response(self):
        """測試回應 Schema"""
        response = AIProcessResponse(
            success=True,
            result='結果',
            action='summarize'
        )
        assert response.success is True
        assert response.result == '結果'
        assert response.error is None

        response_with_error = AIProcessResponse(
            success=False,
            result='',
            action='summarize',
            error='錯誤訊息'
        )
        assert response_with_error.success is False
        assert response_with_error.error == '錯誤訊息'
