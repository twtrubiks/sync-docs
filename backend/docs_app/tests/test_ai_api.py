"""
AI API 測試
使用單元測試方式測試 AIService 和 AIRateLimiter

AIService 行為測試以 TestModel / FunctionModel override agent，全程不打外部 API。
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from django.test import override_settings
from ninja_jwt.tokens import AccessToken
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import DeltaToolCall, FunctionModel
from pydantic_ai.models.test import TestModel

from docs_app import ai_service as ai_service_module
from docs_app.ai_service import (
    AIService,
    ai_service,
    _get_agent,
    _get_doc_agent,
    _get_metadata_agent,
    _get_model,
    _get_proofread_agent,
)
from docs_app.ai_rate_limiter import AIRateLimiter, ai_rate_limiter
from docs_app.schemas import DocumentMetadata, ProofreadResult, WritingIssue

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
    async def test_process_stream_yields_chunks(self):
        """串流摘要：逐塊 yield 的文字 delta 拼接後等於完整輸出"""
        with _get_agent().override(model=TestModel(custom_output_text="這是串流摘要")):
            chunks = [c async for c in AIService().process_stream('summarize', '測試文字')]

        assert ''.join(chunks) == "這是串流摘要"

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_process_stream_empty_text_error(self):
        """串流：空文字錯誤（迭代時拋出）"""
        with pytest.raises(ValueError, match=r"^Text cannot be empty$"):
            async for _ in AIService().process_stream('summarize', ''):
                pass

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_process_stream_invalid_action_error(self):
        """串流：無效操作錯誤"""
        with pytest.raises(ValueError, match=r"^Unknown action: invalid$"):
            async for _ in AIService().process_stream('invalid', '文字'):
                pass

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='')
    async def test_process_stream_not_configured_error(self):
        """串流：API Key 未配置錯誤"""
        with pytest.raises(RuntimeError, match=r"^AI 服務未配置$"):
            async for _ in AIService().process_stream('summarize', '文字'):
                pass

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_process_stream_text_truncation(self):
        """串流：超過 5000 字元的輸入會被截斷後才送進 agent"""
        captured = {}

        async def capture_stream(messages, info):
            for message in messages:
                for part in message.parts:
                    if isinstance(part, UserPromptPart):
                        captured['prompt'] = str(part.content)
            yield '結果'

        long_text = 'A' * 6000
        with _get_agent().override(model=FunctionModel(stream_function=capture_stream)):
            async for _ in AIService().process_stream('summarize', long_text):
                pass

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
        model = _get_model()
        assert isinstance(model, GoogleModel)
        # 關閉思考：思考 token 會吃掉 max_tokens 預算導致回覆被截斷
        assert model.settings['google_thinking_config'] == {'thinking_budget': 0}

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
        with pytest.raises(ValueError, match=r"^Text cannot be empty$"):
            await AIService().proofread('')

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='')
    async def test_not_configured_error(self):
        """測試 API Key 未配置錯誤"""
        with pytest.raises(RuntimeError, match=r"^AI 服務未配置$"):
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
        with pytest.raises(ValueError, match=r"^Text cannot be empty$"):
            await AIService().generate_metadata('')

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='')
    async def test_not_configured_error(self):
        """測試 API Key 未配置錯誤"""
        with pytest.raises(RuntimeError, match=r"^AI 服務未配置$"):
            await AIService().generate_metadata('文字')


class TestDocQA:
    """文件問答測試（deps_type=DocDeps + @agent.tool，以 TestModel/FunctionModel override，不打 API）"""

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_ask_stream_yields_chunks(self):
        """串流文件問答：deps + 工具跑通，逐塊 yield 的 delta 拼接後等於完整答案"""
        with _get_doc_agent().override(model=TestModel(custom_output_text="這是串流答案")):
            chunks = [
                c async for c in AIService().ask_stream('文件重點？', '介紹 Docker 的文件')
            ]

        assert ''.join(chunks) == "這是串流答案"

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_ask_stream_empty_question_error(self):
        """串流：空問題錯誤（迭代時拋出）"""
        with pytest.raises(ValueError, match=r"^Question cannot be empty$"):
            async for _ in AIService().ask_stream('', '文件內容'):
                pass

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='')
    async def test_ask_stream_not_configured_error(self):
        """串流：API Key 未配置錯誤"""
        with pytest.raises(RuntimeError, match=r"^AI 服務未配置$"):
            async for _ in AIService().ask_stream('問題', '文件內容'):
                pass

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_ask_stream_exposes_document_tool(self):
        """end-to-end 跑通 deps + 工具；agent 對外曝露 get_document_text 工具"""
        model = TestModel()
        with _get_doc_agent().override(model=model):
            chunks = [
                c async for c in AIService().ask_stream('這份文件在說什麼？', '介紹 Docker 的文件')
            ]

        assert isinstance(''.join(chunks), str)
        tool_names = [t.name for t in model.last_model_request_parameters.function_tools]
        assert tool_names == ['get_document_text']

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_ask_stream_tool_provides_injected_document_text(self):
        """依賴注入：模型呼叫工具後，工具回傳的文件內容正是注入的 document_text"""
        captured = {}

        async def fake_stream(messages, info):
            # 工具已回傳 → 擷取其內容並輸出答案
            for message in messages:
                for part in message.parts:
                    if isinstance(part, ToolReturnPart) and part.tool_name == 'get_document_text':
                        captured['doc'] = str(part.content)
                        yield '已根據文件回答'
                        return
            # 尚未呼叫工具 → 先呼叫工具
            yield {0: DeltaToolCall(name='get_document_text', json_args='{}', tool_call_id='c1')}

        with _get_doc_agent().override(model=FunctionModel(stream_function=fake_stream)):
            chunks = [
                c async for c in AIService().ask_stream('文件重點？', '這份文件介紹 Docker 容器化技術')
            ]

        assert ''.join(chunks) == '已根據文件回答'
        assert captured['doc'] == '這份文件介紹 Docker 容器化技術'


class TestAIRateLimiter:
    """AI Rate Limiter 單元測試"""

    def test_is_allowed_returns_true_when_under_limit(self):
        """測試在限制內時返回 True（Lua 腳本回傳 1）"""
        with patch.object(AIRateLimiter, '_get_redis') as mock_redis:
            mock_r = MagicMock()
            mock_r.eval.return_value = 1
            mock_redis.return_value = mock_r

            limiter = AIRateLimiter()
            result = limiter.is_allowed('test_key', 10, 60)

            assert result is True

    def test_is_allowed_returns_false_when_over_limit(self):
        """測試超過限制時返回 False（Lua 腳本回傳 0）"""
        with patch.object(AIRateLimiter, '_get_redis') as mock_redis:
            mock_r = MagicMock()
            mock_r.eval.return_value = 0
            mock_redis.return_value = mock_r

            limiter = AIRateLimiter()
            result = limiter.is_allowed('test_key', 10, 60)

            assert result is False

    def test_warns_only_when_blocking(self):
        with patch.object(AIRateLimiter, '_get_redis') as mock_redis, \
                patch('docs_app.ai_rate_limiter.logger') as logger:
            mock_redis.return_value.eval.return_value = 1
            AIRateLimiter().is_allowed('test_key', 10, 60)
            logger.warning.assert_not_called()

            mock_redis.return_value.eval.return_value = 0
            AIRateLimiter().is_allowed('test_key', 10, 60)
            logger.warning.assert_called_once()

    def test_is_allowed_fail_open_on_error(self):
        """測試發生錯誤時允許通過（fail-open）"""
        with patch.object(AIRateLimiter, '_get_redis') as mock_redis:
            mock_redis.side_effect = Exception("Redis connection error")

            limiter = AIRateLimiter()
            result = limiter.is_allowed('test_key', 10, 60)

            # 發生錯誤時應該返回 True（fail-open）
            assert result is True


def _raising_model(exc):
    """回傳一個無論一般 / 串流呼叫都拋出 exc 的 FunctionModel（模擬供應商錯誤）"""
    def run(messages, info):
        raise exc

    async def stream(messages, info):
        raise exc
        yield  # pragma: no cover - 讓函數成為 async generator

    return FunctionModel(function=run, stream_function=stream)


async def _call_service(method):
    """以一致介面呼叫四種 AIService 方法（串流方法會被完整迭代）"""
    service = AIService()
    if method == 'process_stream':
        return [c async for c in service.process_stream('summarize', '文字')]
    if method == 'ask_stream':
        return [c async for c in service.ask_stream('問題', '文件內容')]
    if method == 'proofread':
        return await service.proofread('文字')
    return await service.generate_metadata('文字')


AGENT_GETTERS = {
    'process_stream': _get_agent,
    'ask_stream': _get_doc_agent,
    'proofread': _get_proofread_agent,
    'generate_metadata': _get_metadata_agent,
}


class TestAIServiceErrorHandling:
    """供應商錯誤轉譯為使用者可讀的 RuntimeError（前端直接顯示這些訊息）"""

    @pytest.mark.parametrize('method', list(AGENT_GETTERS))
    @pytest.mark.parametrize('exc, expected', [
        (ModelHTTPError(429, 'test-model'), 'API 配額已用盡，請稍後再試'),
        (ModelHTTPError(500, 'test-model'), 'AI 服務暫時無法使用'),
        (Exception('boom'), 'AI 處理失敗：boom'),
    ], ids=['quota-429', 'http-500', 'unexpected'])
    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_provider_errors_are_translated(self, method, exc, expected):
        with AGENT_GETTERS[method]().override(model=_raising_model(exc)):
            with pytest.raises(RuntimeError) as excinfo:
                await _call_service(method)
        assert str(excinfo.value) == expected

    @pytest.mark.parametrize('method', ['process_stream', 'ask_stream'])
    @pytest.mark.parametrize('exc', [ValueError('bad output'), RuntimeError('model gave up')])
    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_stream_value_and_runtime_errors_propagate_unchanged(self, method, exc):
        with AGENT_GETTERS[method]().override(model=_raising_model(exc)):
            with pytest.raises(type(exc)) as excinfo:
                await _call_service(method)
        assert excinfo.value is exc

    @override_settings(AI_PROVIDER='gemini', GOOGLE_API_KEY='g-key', NVIDIA_API_KEY='')
    async def test_gemini_with_google_key_is_configured(self):
        """供應商為 gemini 且有 GOOGLE_API_KEY 時，即使沒有 NVIDIA key 也可使用"""
        with _get_proofread_agent().override(model=TestModel()):
            result = await AIService().proofread('文字')
        assert isinstance(result, ProofreadResult)

    @override_settings(AI_PROVIDER='gemini', GOOGLE_API_KEY='', NVIDIA_API_KEY='nv-key')
    async def test_gemini_requires_google_key(self):
        """供應商為 gemini 時檢查的是 GOOGLE_API_KEY，而非 NVIDIA_API_KEY"""
        with pytest.raises(RuntimeError, match='AI 服務未配置'):
            await AIService().proofread('文字')

    @pytest.mark.parametrize('method', ['proofread', 'generate_metadata'])
    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_structured_input_truncated_to_5000_chars(self, method):
        """校對 / 分析：超過 5000 字元只送前 5000 字並加省略號"""
        captured = {}

        def capture(messages, info):
            for message in messages:
                for part in message.parts:
                    if isinstance(part, UserPromptPart):
                        captured['prompt'] = str(part.content)
            raise RuntimeError('stop after capture')

        with AGENT_GETTERS[method]().override(model=FunctionModel(function=capture)):
            with pytest.raises(RuntimeError):
                await getattr(AIService(), method)('A' * 5000 + 'B' * 10)

        assert captured['prompt'] == 'A' * 5000 + '...'

    @pytest.mark.parametrize('method', ['proofread', 'generate_metadata'])
    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_structured_input_at_limit_not_truncated(self, method):
        """剛好 5000 字元不截斷（邊界）"""
        captured = {}

        def capture(messages, info):
            for message in messages:
                for part in message.parts:
                    if isinstance(part, UserPromptPart):
                        captured['prompt'] = str(part.content)
            raise RuntimeError('stop after capture')

        with AGENT_GETTERS[method]().override(model=FunctionModel(function=capture)):
            with pytest.raises(RuntimeError):
                await getattr(AIService(), method)('A' * 5000)

        assert captured['prompt'] == 'A' * 5000

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_stream_inputs_at_limit_not_truncated(self):
        """串流（摘要 / 問答）：剛好 5000 字元不加省略號"""
        captured = {}

        async def capture_prompt(messages, info):
            for message in messages:
                for part in message.parts:
                    if isinstance(part, UserPromptPart):
                        captured['prompt'] = str(part.content)
            yield '結果'

        async def capture_tool(messages, info):
            for message in messages:
                for part in message.parts:
                    if isinstance(part, ToolReturnPart):
                        captured['doc'] = str(part.content)
                        yield '答'
                        return
            yield {0: DeltaToolCall(name='get_document_text', json_args='{}', tool_call_id='c1')}

        with _get_agent().override(model=FunctionModel(stream_function=capture_prompt)):
            [c async for c in AIService().process_stream('summarize', 'A' * 5000)]
        with _get_doc_agent().override(model=FunctionModel(stream_function=capture_tool)):
            [c async for c in AIService().ask_stream('問題', 'A' * 5000)]

        assert 'A' * 5000 in captured['prompt'] and '...' not in captured['prompt']
        assert captured['doc'] == 'A' * 5000

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_streams_yield_incremental_deltas(self):
        """串流回傳的是增量 delta（前端逐段串接），不是累積全文"""
        # 片段間隔需大於 pydantic-ai stream_text 的 debounce（0.1s），否則會被合併成一段
        async def two_chunks(messages, info):
            yield '你好'
            await asyncio.sleep(0.15)
            yield '世界'

        async def tool_then_two_chunks(messages, info):
            for message in messages:
                for part in message.parts:
                    if isinstance(part, ToolReturnPart):
                        yield '你好'
                        await asyncio.sleep(0.15)
                        yield '世界'
                        return
            yield {0: DeltaToolCall(name='get_document_text', json_args='{}', tool_call_id='c1')}

        with _get_agent().override(model=FunctionModel(stream_function=two_chunks)):
            summary = [c async for c in AIService().process_stream('summarize', '文字')]
        with _get_doc_agent().override(model=FunctionModel(stream_function=tool_then_two_chunks)):
            answer = [c async for c in AIService().ask_stream('問題', '文件')]

        # 若回傳累積全文（delta=False），串接後會變成「你好你好世界」
        assert ''.join(summary) == '你好世界'
        assert ''.join(answer) == '你好世界'

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_ask_stream_document_truncated_to_5000_chars(self):
        """文件問答：注入給工具的文件超過 5000 字元會截斷"""
        captured = {}

        async def fake_stream(messages, info):
            for message in messages:
                for part in message.parts:
                    if isinstance(part, ToolReturnPart):
                        captured['doc'] = str(part.content)
                        yield '答'
                        return
            yield {0: DeltaToolCall(name='get_document_text', json_args='{}', tool_call_id='c1')}

        with _get_doc_agent().override(model=FunctionModel(stream_function=fake_stream)):
            [c async for c in AIService().ask_stream('問題', 'A' * 5000 + 'B')]

        assert captured['doc'] == 'A' * 5000 + '...'

    @override_settings(AI_PROVIDER='nvidia', NVIDIA_API_KEY='test-key')
    async def test_process_stream_truncation_keeps_exactly_5000_chars(self):
        """摘要 / 潤稿：截斷後保留前 5000 字（不多不少）"""
        captured = {}

        async def capture_stream(messages, info):
            for message in messages:
                for part in message.parts:
                    if isinstance(part, UserPromptPart):
                        captured['prompt'] = str(part.content)
            yield '結果'

        with _get_agent().override(model=FunctionModel(stream_function=capture_stream)):
            [c async for c in AIService().process_stream('polish', 'A' * 5000 + 'B')]

        assert 'A' * 5000 + '...' in captured['prompt']
        assert 'A' * 5001 not in captured['prompt']
        assert 'B' not in captured['prompt']


class TestAIController:
    """AI HTTP 端點（校對 / 文件分析）：認證、與串流共用的額度、錯誤回應格式"""

    ENDPOINTS = [
        ('/api/ai/proofread', 'proofread',
         ProofreadResult(issues=[WritingIssue(original='錯', suggestion='對', reason='錯字', severity='error')],
                         overall_score=80)),
        ('/api/ai/metadata', 'generate_metadata',
         DocumentMetadata(summary='摘要', tags=['a', 'b', 'c'], language='zh-Hant', reading_time=3)),
    ]

    @pytest.fixture
    def auth_headers(self, test_user):
        return {'HTTP_AUTHORIZATION': f'Bearer {AccessToken.for_user(test_user)}'}

    @pytest.mark.parametrize('url, method, result', ENDPOINTS, ids=['proofread', 'metadata'])
    def test_success_returns_structured_result(self, client, auth_headers, test_user, url, method, result):
        with patch.object(ai_rate_limiter, 'is_allowed', return_value=True) as limiter, \
                patch.object(ai_service, method, AsyncMock(return_value=result)) as service_call:
            response = client.post(url, data={'text': '一段文字'}, content_type='application/json', **auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body['success'] is True
        assert body['error'] is None
        assert body['result'] == result.model_dump()
        service_call.assert_awaited_once_with('一段文字')
        # 與 WebSocket 串流共用同一額度鍵與上限
        limiter.assert_called_once_with(f'ai:{test_user.id}', 10, 60)

    @pytest.mark.parametrize('url, method, result', ENDPOINTS, ids=['proofread', 'metadata'])
    def test_rate_limited_does_not_call_service(self, client, auth_headers, url, method, result):
        with patch.object(ai_rate_limiter, 'is_allowed', return_value=False), \
                patch.object(ai_service, method, AsyncMock(return_value=result)) as service_call:
            response = client.post(url, data={'text': '一段文字'}, content_type='application/json', **auth_headers)

        assert response.status_code == 200
        assert response.json() == {'success': False, 'result': None, 'error': '請求過於頻繁，請稍後再試'}
        service_call.assert_not_called()

    @pytest.mark.parametrize('url, method, result', ENDPOINTS, ids=['proofread', 'metadata'])
    @pytest.mark.parametrize('exc', [ValueError('Text cannot be empty'), RuntimeError('AI 服務未配置')],
                             ids=['value-error', 'runtime-error'])
    def test_service_errors_become_error_response(self, client, auth_headers, url, method, result, exc):
        with patch.object(ai_rate_limiter, 'is_allowed', return_value=True), \
                patch.object(ai_service, method, AsyncMock(side_effect=exc)):
            response = client.post(url, data={'text': ''}, content_type='application/json', **auth_headers)

        assert response.status_code == 200
        assert response.json() == {'success': False, 'result': None, 'error': str(exc)}

    @pytest.mark.parametrize('url', ['/api/ai/proofread', '/api/ai/metadata'])
    def test_requires_authentication(self, client, url):
        response = client.post(url, data={'text': '文字'}, content_type='application/json')
        assert response.status_code == 401


class TestAIRateLimiterSlidingWindow:
    """AI / 登入 / 註冊共用的同步限流器實際行為（真實 Redis + 假時鐘）"""

    KEY = 'ai:test-sliding-window'
    OTHER_KEY = 'ai:test-sliding-window-other'

    @pytest.fixture
    def redis_client(self):
        import redis
        from docs_app.redis_pool import _get_host_port

        host, port = _get_host_port()
        r = redis.Redis(host=host, port=port, decode_responses=True)
        r.delete(self.KEY, self.OTHER_KEY)
        yield r
        r.delete(self.KEY, self.OTHER_KEY)
        r.close()

    @pytest.fixture
    def clock(self):
        class Clock:
            now = 1_000_000.0

        with patch('docs_app.ai_rate_limiter.time.time', side_effect=lambda: Clock.now):
            yield Clock

    @pytest.fixture
    def limiter(self, redis_client, clock):
        limiter = AIRateLimiter()
        with patch.object(limiter, '_get_redis', return_value=redis_client):
            yield limiter

    def _call(self, limiter, clock, at, key=None):
        clock.now = at
        return limiter.is_allowed(key or self.KEY, 3, 10)

    def test_allows_up_to_limit_then_blocks(self, limiter, clock):
        assert [self._call(limiter, clock, t) for t in (1_000_000.0, 1_000_000.1, 1_000_000.2)] == [True] * 3
        assert self._call(limiter, clock, 1_000_000.3) is False

    def test_window_boundary_and_rejections_not_counted(self, limiter, clock):
        for t in (1_000_000.0, 1_000_001.0, 1_000_002.0):
            self._call(limiter, clock, t)
        assert self._call(limiter, clock, 1_000_005.0) is False
        assert self._call(limiter, clock, 1_000_009.999) is False
        # 剛好 10 秒：最早一則滑出窗口，只空出一個名額
        assert self._call(limiter, clock, 1_000_010.0) is True
        assert self._call(limiter, clock, 1_000_010.5) is False

    def test_key_expires_after_window(self, limiter, clock, redis_client):
        self._call(limiter, clock, 1_000_000.0)

        assert redis_client.ttl(self.KEY) == 11

    def test_keys_are_independent(self, limiter, clock):
        for t in (1_000_000.0, 1_000_000.1, 1_000_000.2):
            self._call(limiter, clock, t)

        assert self._call(limiter, clock, 1_000_000.3, key=self.OTHER_KEY) is True

    def test_same_millisecond_burst_is_limited(self, limiter, clock, redis_client):
        """同一毫秒內的多個請求必須各自計數（member 不可只用時間戳）"""
        results = [self._call(limiter, clock, 1_000_000.0) for _ in range(5)]

        assert results == [True, True, True, False, False]
        assert redis_client.zcard(self.KEY) == 3

    def test_concurrent_requests_never_exceed_limit(self, redis_client):
        """並發請求不可同時通過檢查而超出額度（檢查與記錄必須是原子操作）"""
        import threading

        limiter = AIRateLimiter()
        barrier = threading.Barrier(20)
        results = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            allowed = limiter.is_allowed(self.KEY, 5, 10)
            with lock:
                results.append(allowed)

        with patch.object(limiter, '_get_redis', return_value=redis_client):
            threads = [threading.Thread(target=worker) for _ in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert results.count(True) == 5
        assert results.count(False) == 15
        assert redis_client.zcard(self.KEY) == 5

    def test_uses_shared_sync_redis_pool(self):
        sentinel = object()
        with patch('docs_app.ai_rate_limiter.get_sync_redis', return_value=sentinel):
            assert AIRateLimiter()._get_redis() is sentinel



def test_sync_redis_client_is_cached_and_decodes_responses():
    from docs_app import redis_pool

    original = redis_pool._sync_redis
    redis_pool._sync_redis = None
    try:
        first = redis_pool.get_sync_redis()
        assert redis_pool.get_sync_redis() is first
        assert first.connection_pool.connection_kwargs['decode_responses'] is True
    finally:
        redis_pool._sync_redis = original
