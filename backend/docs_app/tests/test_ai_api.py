"""
AI API 測試
使用單元測試方式測試 AIService 和 AIRateLimiter

AIService 行為測試以 TestModel / FunctionModel override agent，全程不打外部 API。
"""

import pytest
from unittest.mock import patch, MagicMock
from django.test import override_settings
from pydantic import ValidationError
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from docs_app import ai_service as ai_service_module
from docs_app.ai_service import (
    AIService,
    _get_agent,
    _get_doc_agent,
    _get_metadata_agent,
    _get_model,
    _get_proofread_agent,
)
from docs_app.ai_rate_limiter import AIRateLimiter
from docs_app.schemas import (
    AIProcessRequest,
    AIProcessResponse,
    DocumentMetadata,
    ProofreadResult,
    WritingIssue,
)

# 使用 pytest-django 的 db fixture 來確保資料庫在測試之間是乾淨的
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_ai_globals():
    """每個測試前後重置模組級單例，避免供應商切換互相污染。"""
    ai_service_module._model = None
    ai_service_module._agent = None
    ai_service_module._proofread_agent = None
    ai_service_module._metadata_agent = None
    ai_service_module._doc_agent = None
    yield
    ai_service_module._model = None
    ai_service_module._agent = None
    ai_service_module._proofread_agent = None
    ai_service_module._metadata_agent = None
    ai_service_module._doc_agent = None


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


class TestProofread:
    """結構化校對測試（output_type=ProofreadResult，以 TestModel override agent，不打 API）"""

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_returns_structured_result(self):
        """回傳型別安全的 ProofreadResult（TestModel 自動產生符合 schema 的輸出）"""
        with _get_proofread_agent().override(model=TestModel()):
            result = await AIService().proofread('測試文字')

        assert isinstance(result, ProofreadResult)
        assert isinstance(result.issues, list)
        assert 0 <= result.overall_score <= 100

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_custom_output_flows_through(self):
        """指定結構化輸出時，issues 與分數原樣回傳"""
        custom = {
            "issues": [
                {
                    "original": "錯字",
                    "suggestion": "正字",
                    "reason": "用字錯誤",
                    "severity": "warning",
                }
            ],
            "overall_score": 80,
        }
        with _get_proofread_agent().override(model=TestModel(custom_output_args=custom)):
            result = await AIService().proofread('一段含錯字的文字')

        assert result.overall_score == 80
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert isinstance(issue, WritingIssue)
        assert issue.original == "錯字"
        assert issue.suggestion == "正字"
        assert issue.severity == "warning"

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_empty_text_error(self):
        """測試空文字錯誤"""
        with pytest.raises(ValueError, match="Text cannot be empty"):
            await AIService().proofread('')

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='')
    async def test_not_configured_error(self):
        """測試 API Key 未配置錯誤"""
        with pytest.raises(RuntimeError, match="AI 服務未配置"):
            await AIService().proofread('文字')


class TestMetadata:
    """文件 metadata 測試（output_type=DocumentMetadata，以 TestModel override agent，不打 API）"""

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_returns_structured_result(self):
        """回傳型別安全的 DocumentMetadata（TestModel 自動產生符合 schema 的輸出）"""
        with _get_metadata_agent().override(model=TestModel()):
            result = await AIService().generate_metadata('一段文件內容')

        assert isinstance(result, DocumentMetadata)
        assert isinstance(result.tags, list)
        assert result.reading_time >= 0

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_custom_output_flows_through(self):
        """指定結構化輸出時，欄位原樣回傳"""
        custom = {
            "summary": "這是一份關於 Docker 的教學文件",
            "tags": ["Docker", "容器化", "教學"],
            "language": "zh-Hant",
            "reading_time": 5,
        }
        with _get_metadata_agent().override(model=TestModel(custom_output_args=custom)):
            result = await AIService().generate_metadata('Docker 教學內容')

        assert result.summary == "這是一份關於 Docker 的教學文件"
        assert result.tags == ["Docker", "容器化", "教學"]
        assert result.language == "zh-Hant"
        assert result.reading_time == 5

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_empty_text_error(self):
        """測試空文字錯誤"""
        with pytest.raises(ValueError, match="Text cannot be empty"):
            await AIService().generate_metadata('')

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='')
    async def test_not_configured_error(self):
        """測試 API Key 未配置錯誤"""
        with pytest.raises(RuntimeError, match="AI 服務未配置"):
            await AIService().generate_metadata('文字')


class TestDocQA:
    """文件問答測試（deps_type=DocDeps + @agent.tool，以 TestModel/FunctionModel override，不打 API）"""

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_ask_returns_answer(self):
        """end-to-end 跑通 deps + 工具，回傳字串答案；agent 對外曝露 get_document_text 工具"""
        model = TestModel()
        with _get_doc_agent().override(model=model):
            answer = await AIService().ask('這份文件在說什麼？', '介紹 Docker 的文件')

        assert isinstance(answer, str)
        tool_names = [t.name for t in model.last_model_request_parameters.function_tools]
        assert tool_names == ['get_document_text']

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_tool_provides_injected_document_text(self):
        """依賴注入：模型呼叫工具後，工具回傳的文件內容正是注入的 document_text"""
        captured = {}

        async def fake_model(messages, info):
            # 工具已回傳 → 擷取其內容並結束
            for message in messages:
                for part in message.parts:
                    if isinstance(part, ToolReturnPart) and part.tool_name == 'get_document_text':
                        captured['doc'] = str(part.content)
                        return ModelResponse(parts=[TextPart('已根據文件回答')])
            # 尚未呼叫工具 → 先呼叫工具
            return ModelResponse(parts=[
                ToolCallPart(tool_name='get_document_text', args={}, tool_call_id='c1')
            ])

        with _get_doc_agent().override(model=FunctionModel(fake_model)):
            answer = await AIService().ask('文件重點？', '這份文件介紹 Docker 容器化技術')

        assert answer == '已根據文件回答'
        assert captured['doc'] == '這份文件介紹 Docker 容器化技術'

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_empty_question_error(self):
        """測試空問題錯誤"""
        with pytest.raises(ValueError, match="Question cannot be empty"):
            await AIService().ask('', '文件內容')

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='')
    async def test_not_configured_error(self):
        """測試 API Key 未配置錯誤"""
        with pytest.raises(RuntimeError, match="AI 服務未配置"):
            await AIService().ask('問題', '文件內容')


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
