"""
AI API 測試
使用單元測試方式測試 AIService 和 AIRateLimiter
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pydantic import ValidationError

from docs_app.ai_service import AIService
from docs_app.ai_rate_limiter import AIRateLimiter
from docs_app.schemas import AIProcessRequest, AIProcessResponse

# 使用 pytest-django 的 db fixture 來確保資料庫在測試之間是乾淨的
pytestmark = pytest.mark.django_db


class TestAIService:
    """AI Service 單元測試"""

    @pytest.mark.asyncio
    async def test_process_summarize(self):
        """測試摘要功能"""
        with patch('docs_app.ai_service.genai') as mock_genai:
            # 設定 mock - 新 SDK 使用 Client().aio.models.generate_content
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "這是摘要結果"
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            # 創建新的 AIService 實例以使用 mock
            with patch('docs_app.ai_service.settings') as mock_settings:
                mock_settings.GEMINI_API_KEY = 'test_key'
                mock_settings.GEMINI_MODEL = 'test_model'

                service = AIService()
                service._initialized = False  # 強制重新初始化

                result = await service.process('summarize', '測試文字')

                assert result == "這是摘要結果"

    @pytest.mark.asyncio
    async def test_process_polish(self):
        """測試潤稿功能"""
        with patch('docs_app.ai_service.genai') as mock_genai:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "潤飾後的文字"
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            with patch('docs_app.ai_service.settings') as mock_settings:
                mock_settings.GEMINI_API_KEY = 'test_key'
                mock_settings.GEMINI_MODEL = 'test_model'

                service = AIService()
                service._initialized = False

                result = await service.process('polish', '原始文字')

                assert result == "潤飾後的文字"

    @pytest.mark.asyncio
    async def test_empty_text_error(self):
        """測試空文字錯誤"""
        with patch('docs_app.ai_service.settings') as mock_settings:
            mock_settings.GEMINI_API_KEY = 'test_key'
            mock_settings.GEMINI_MODEL = 'test_model'

            service = AIService()

            with pytest.raises(ValueError, match="Text cannot be empty"):
                await service.process('summarize', '')

    @pytest.mark.asyncio
    async def test_invalid_action_error(self):
        """測試無效操作錯誤"""
        with patch('docs_app.ai_service.settings') as mock_settings:
            mock_settings.GEMINI_API_KEY = 'test_key'
            mock_settings.GEMINI_MODEL = 'test_model'

            service = AIService()

            with pytest.raises(ValueError, match="Unknown action"):
                await service.process('invalid', '文字')

    @pytest.mark.asyncio
    async def test_api_not_configured_error(self):
        """測試 API Key 未配置錯誤"""
        with patch('docs_app.ai_service.settings') as mock_settings:
            mock_settings.GEMINI_API_KEY = ''  # 空的 API key
            mock_settings.GEMINI_MODEL = 'test_model'

            service = AIService()
            service._initialized = False

            with pytest.raises(RuntimeError, match="AI 服務未配置"):
                await service.process('summarize', '文字')

    @pytest.mark.asyncio
    async def test_text_truncation(self):
        """測試文字長度限制（超過 5000 字元會被截斷）"""
        with patch('docs_app.ai_service.genai') as mock_genai:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.text = "結果"
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            with patch('docs_app.ai_service.settings') as mock_settings:
                mock_settings.GEMINI_API_KEY = 'test_key'
                mock_settings.GEMINI_MODEL = 'test_model'

                service = AIService()
                service._initialized = False

                # 創建超過 5000 字元的文字
                long_text = 'A' * 6000

                await service.process('summarize', long_text)

                # 檢查傳遞給 API 的 contents 是否被截斷
                call_kwargs = mock_client.aio.models.generate_content.call_args[1]
                assert '...' in call_kwargs['contents']  # 應該有省略號


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
