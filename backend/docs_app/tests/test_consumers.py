"""
WebSocket消費者測試模組
測試文檔協作的WebSocket功能
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from django.contrib.auth.models import AnonymousUser
from docs_app.consumers import DocConsumer, MAX_MESSAGE_SIZE, MAX_OPS_COUNT, WSCloseCodes
from docs_app.ai_service import ai_service
from docs_app.ai_rate_limiter import ai_rate_limiter

pytestmark = pytest.mark.django_db


class TestDocConsumer:
    """DocConsumer測試類"""

    def test_has_permission_authenticated_user(self, test_user):
        """測試已認證用戶的基本權限檢查"""
        # 測試用戶是否已認證
        assert test_user.is_authenticated

        # 測試匿名用戶
        anonymous_user = AnonymousUser()
        assert not anonymous_user.is_authenticated

    def test_document_creation_and_ownership(self, test_user, test_document):
        """測試文檔創建和擁有權"""
        # 確保文檔擁有者是測試用戶
        assert test_document.owner == test_user
        assert test_document.title == "Test Document"

        # 測試文檔的can_user_access方法
        assert test_document.can_user_access(test_user) is True

    def test_shared_document_access(self, test_user, another_user, shared_document):
        """測試共享文檔訪問權限"""
        # 確保文檔擁有者是test_user
        assert shared_document.owner == test_user

        # 確保another_user是協作者
        assert shared_document.collaborators.filter(user=another_user).exists()

        # 測試擁有者和協作者都能訪問
        assert shared_document.can_user_access(test_user) is True
        assert shared_document.can_user_access(another_user) is True

    def test_anonymous_user_properties(self):
        """測試匿名用戶的屬性"""
        anonymous_user = AnonymousUser()
        assert not anonymous_user.is_authenticated
        assert anonymous_user.id is None

    def test_consumer_initialization(self):
        """測試消費者初始化"""
        consumer = DocConsumer()
        assert consumer is not None


class TestPermissionChangedHandler:
    """測試 permission_changed 事件處理（協作者權限變更對既有連線即時生效）"""

    @pytest.fixture
    def mock_consumer(self, test_user, test_document):
        """創建模擬的 consumer 實例"""
        consumer = DocConsumer()
        consumer.user = test_user
        consumer.document_id = str(test_document.id)
        consumer.room_group_name = f'doc_{test_document.id}'
        consumer.channel_name = 'test_channel'
        consumer.channel_layer = MagicMock()
        consumer.channel_layer.group_send = AsyncMock()
        consumer.send = AsyncMock()
        consumer.close = AsyncMock()
        consumer.can_write = True
        return consumer

    async def test_removed_sends_error_and_closes(self, mock_consumer, test_user):
        """測試被移除協作者資格時收到錯誤消息並以 PERMISSION_DENIED 斷線"""
        await mock_consumer.permission_changed({
            'type': 'permission_changed',
            'user_id': str(test_user.id),
            'removed': True,
            'can_write': False,
        })

        sent_data = json.loads(mock_consumer.send.call_args.kwargs['text_data'])
        assert sent_data['type'] == 'connection_error'
        assert sent_data['error_code'] == 'PERMISSION_DENIED'
        mock_consumer.close.assert_called_once_with(code=WSCloseCodes.PERMISSION_DENIED)

    async def test_demote_updates_can_write_and_notifies(self, mock_consumer, test_user):
        """測試降權為只讀時 can_write 即時更新並通知 client"""
        await mock_consumer.permission_changed({
            'type': 'permission_changed',
            'user_id': str(test_user.id),
            'removed': False,
            'can_write': False,
        })

        assert mock_consumer.can_write is False
        sent_data = json.loads(mock_consumer.send.call_args.kwargs['text_data'])
        assert sent_data['type'] == 'permission_update'
        assert sent_data['can_write'] is False
        mock_consumer.close.assert_not_called()

    async def test_promote_updates_can_write_and_notifies(self, mock_consumer, test_user):
        """測試只讀升權為編輯時 can_write 即時更新並通知 client"""
        mock_consumer.can_write = False

        await mock_consumer.permission_changed({
            'type': 'permission_changed',
            'user_id': str(test_user.id),
            'removed': False,
            'can_write': True,
        })

        assert mock_consumer.can_write is True
        sent_data = json.loads(mock_consumer.send.call_args.kwargs['text_data'])
        assert sent_data['type'] == 'permission_update'
        assert sent_data['can_write'] is True

    async def test_event_for_other_user_is_ignored(self, mock_consumer):
        """測試其他用戶的權限變更事件不影響自己的連線"""
        await mock_consumer.permission_changed({
            'type': 'permission_changed',
            'user_id': '99999',
            'removed': True,
            'can_write': False,
        })

        assert mock_consumer.can_write is True
        mock_consumer.send.assert_not_called()
        mock_consumer.close.assert_not_called()

    async def test_same_permission_no_notification(self, mock_consumer, test_user):
        """測試權限未實際變化時不發送通知"""
        await mock_consumer.permission_changed({
            'type': 'permission_changed',
            'user_id': str(test_user.id),
            'removed': False,
            'can_write': True,  # 原本就是 True
        })

        assert mock_consumer.can_write is True
        mock_consumer.send.assert_not_called()


class TestDocConsumerValidation:
    """測試 WebSocket 消息驗證功能"""

    @pytest.fixture
    def mock_consumer(self, test_user, test_document):
        """創建模擬的 consumer 實例"""
        consumer = DocConsumer()
        consumer.user = test_user
        consumer.document_id = str(test_document.id)
        consumer.room_group_name = f'doc_{test_document.id}'
        consumer.channel_name = 'test_channel'
        consumer.channel_layer = MagicMock()
        consumer.channel_layer.group_send = AsyncMock()
        consumer.send = AsyncMock()
        consumer.can_write = True  # 設置編輯權限
        return consumer

    async def test_receive_invalid_json_returns_error(self, mock_consumer):
        """測試發送無效 JSON 會收到錯誤回應"""
        # 發送無效 JSON
        await mock_consumer.receive(text_data='invalid json {{{')

        # 驗證收到 INVALID_JSON 錯誤
        mock_consumer.send.assert_called_once()
        call_args = mock_consumer.send.call_args
        sent_data = json.loads(call_args.kwargs['text_data'])

        assert sent_data['type'] == 'error'
        assert sent_data['error_code'] == 'INVALID_JSON'

    async def test_receive_missing_delta_returns_error(self, mock_consumer):
        """測試缺少 delta 欄位會收到錯誤回應"""
        # 發送沒有 delta 的消息
        await mock_consumer.receive(text_data=json.dumps({'other': 'data'}))

        # 驗證收到 INVALID_DELTA_FORMAT 錯誤
        mock_consumer.send.assert_called_once()
        call_args = mock_consumer.send.call_args
        sent_data = json.loads(call_args.kwargs['text_data'])

        assert sent_data['type'] == 'error'
        assert sent_data['error_code'] == 'INVALID_DELTA_FORMAT'

    async def test_receive_invalid_delta_format_returns_error(self, mock_consumer):
        """測試無效的 delta 格式會收到錯誤回應"""
        # 發送無效的 delta 格式（缺少 ops）
        await mock_consumer.receive(text_data=json.dumps({
            'delta': {'invalid': 'data'}
        }))

        # 驗證收到 INVALID_DELTA_FORMAT 錯誤
        mock_consumer.send.assert_called_once()
        call_args = mock_consumer.send.call_args
        sent_data = json.loads(call_args.kwargs['text_data'])

        assert sent_data['type'] == 'error'
        assert sent_data['error_code'] == 'INVALID_DELTA_FORMAT'

    async def test_receive_empty_ops_returns_error(self, mock_consumer):
        """測試空的 ops 陣列會收到錯誤回應"""
        await mock_consumer.receive(text_data=json.dumps({
            'delta': {'ops': []}
        }))

        mock_consumer.send.assert_called_once()
        call_args = mock_consumer.send.call_args
        sent_data = json.loads(call_args.kwargs['text_data'])

        assert sent_data['type'] == 'error'
        assert sent_data['error_code'] == 'INVALID_DELTA_FORMAT'
        assert 'empty' in sent_data['message'].lower()

    async def test_receive_invalid_operation_returns_error(self, mock_consumer):
        """測試無效的操作（同時有 insert 和 delete）會收到錯誤回應"""
        await mock_consumer.receive(text_data=json.dumps({
            'delta': {'ops': [{'insert': 'text', 'delete': 5}]}
        }))

        mock_consumer.send.assert_called_once()
        call_args = mock_consumer.send.call_args
        sent_data = json.loads(call_args.kwargs['text_data'])

        assert sent_data['type'] == 'error'
        assert sent_data['error_code'] == 'INVALID_DELTA_FORMAT'

    async def test_receive_valid_delta_broadcasts_successfully(self, mock_consumer):
        """測試發送有效的 delta 會成功廣播"""
        valid_delta = {'delta': {'ops': [{'insert': 'Hello World'}]}}

        await mock_consumer.receive(text_data=json.dumps(valid_delta))

        # 不應該發送錯誤
        mock_consumer.send.assert_not_called()

        # 應該廣播到群組
        mock_consumer.channel_layer.group_send.assert_called_once()
        call_args = mock_consumer.channel_layer.group_send.call_args
        assert call_args[0][0] == mock_consumer.room_group_name
        assert call_args[0][1]['type'] == 'doc_update'
        assert call_args[0][1]['delta']['ops'][0]['insert'] == 'Hello World'

    async def test_receive_complex_delta_broadcasts_successfully(self, mock_consumer):
        """測試複雜的 delta 格式會成功廣播"""
        complex_delta = {
            'delta': {
                'ops': [
                    {'retain': 10},
                    {'insert': 'new text', 'attributes': {'bold': True}},
                    {'delete': 5}
                ]
            }
        }

        await mock_consumer.receive(text_data=json.dumps(complex_delta))

        # 不應該發送錯誤
        mock_consumer.send.assert_not_called()

        # 應該廣播到群組
        mock_consumer.channel_layer.group_send.assert_called_once()

    async def test_receive_message_too_large_returns_error(self, mock_consumer):
        """測試超大消息會收到錯誤回應"""
        # 創建超過 256KB 的消息
        large_text = 'x' * (MAX_MESSAGE_SIZE + 1000)
        large_message = json.dumps({'delta': {'ops': [{'insert': large_text}]}})

        await mock_consumer.receive(text_data=large_message)

        mock_consumer.send.assert_called_once()
        call_args = mock_consumer.send.call_args
        sent_data = json.loads(call_args.kwargs['text_data'])

        assert sent_data['type'] == 'error'
        assert sent_data['error_code'] == 'MESSAGE_TOO_LARGE'

    async def test_receive_too_many_operations_returns_error(self, mock_consumer):
        """測試操作數量超過限制會收到錯誤回應"""
        # 創建超過 1000 個操作的 delta
        many_ops = [{'insert': f'text{i}'} for i in range(MAX_OPS_COUNT + 10)]
        message = json.dumps({'delta': {'ops': many_ops}})

        await mock_consumer.receive(text_data=message)

        mock_consumer.send.assert_called_once()
        call_args = mock_consumer.send.call_args
        sent_data = json.loads(call_args.kwargs['text_data'])

        assert sent_data['type'] == 'error'
        assert sent_data['error_code'] == 'TOO_MANY_OPERATIONS'

    async def test_receive_negative_retain_returns_error(self, mock_consumer):
        """測試負數的 retain 值會收到錯誤回應"""
        await mock_consumer.receive(text_data=json.dumps({
            'delta': {'ops': [{'retain': -5}]}
        }))

        mock_consumer.send.assert_called_once()
        call_args = mock_consumer.send.call_args
        sent_data = json.loads(call_args.kwargs['text_data'])

        assert sent_data['type'] == 'error'
        assert sent_data['error_code'] == 'INVALID_DELTA_FORMAT'
        assert 'positive' in sent_data['message'].lower()

    async def test_receive_zero_delete_returns_error(self, mock_consumer):
        """測試零值的 delete 會收到錯誤回應"""
        await mock_consumer.receive(text_data=json.dumps({
            'delta': {'ops': [{'delete': 0}]}
        }))

        mock_consumer.send.assert_called_once()
        call_args = mock_consumer.send.call_args
        sent_data = json.loads(call_args.kwargs['text_data'])

        assert sent_data['type'] == 'error'
        assert sent_data['error_code'] == 'INVALID_DELTA_FORMAT'

    async def test_receive_image_embed_broadcasts_successfully(self, mock_consumer):
        """測試圖片嵌入的 delta 會成功廣播"""
        image_delta = {
            'delta': {
                'ops': [{'insert': {'image': 'data:image/png;base64,abc123'}}]
            }
        }

        await mock_consumer.receive(text_data=json.dumps(image_delta))

        # 不應該發送錯誤
        mock_consumer.send.assert_not_called()

        # 應該廣播到群組
        mock_consumer.channel_layer.group_send.assert_called_once()


class TestDocConsumerAIStream:
    """測試 WebSocket AI 串流（摘要/潤稿，逐字回傳給發送者本人）"""

    @pytest.fixture
    def mock_consumer(self, test_user, test_document):
        """創建模擬的 consumer 實例（AI 串流不要求寫入權限，與 HTTP /ai/process 一致）"""
        consumer = DocConsumer()
        consumer.user = test_user
        consumer.document_id = str(test_document.id)
        consumer.room_group_name = f'doc_{test_document.id}'
        consumer.channel_name = 'test_channel'
        consumer.channel_layer = MagicMock()
        consumer.channel_layer.group_send = AsyncMock()
        consumer.send = AsyncMock()
        consumer.can_write = True
        return consumer

    @staticmethod
    def _sent_messages(mock_consumer):
        """擷取所有經由 self.send 送出的訊息（已解析 JSON）"""
        return [
            json.loads(call.kwargs['text_data'])
            for call in mock_consumer.send.call_args_list
        ]

    async def test_ai_stream_sends_start_chunks_end(self, mock_consumer):
        """正常串流：依序送出 start → chunk(s) → end，且 chunk 內容正確"""
        async def fake_stream(action, text):
            for c in ['你好', '世界']:
                yield c

        with patch.object(ai_service, 'process_stream', fake_stream), \
                patch.object(ai_rate_limiter, 'is_allowed', return_value=True):
            await mock_consumer.receive(text_data=json.dumps({
                'type': 'ai_stream', 'action': 'summarize', 'text': '測試'
            }))
            # 等背景串流任務完成
            await mock_consumer._ai_stream_task

        messages = self._sent_messages(mock_consumer)
        assert [m['type'] for m in messages] == [
            'ai_stream_start', 'ai_stream_chunk', 'ai_stream_chunk', 'ai_stream_end'
        ]
        chunks = [m['chunk'] for m in messages if m['type'] == 'ai_stream_chunk']
        assert chunks == ['你好', '世界']
        assert messages[0]['action'] == 'summarize'

    async def test_ai_stream_rate_limited(self, mock_consumer):
        """超過速率限制：回傳 ai_stream_error，且不啟動串流任務"""
        with patch.object(ai_rate_limiter, 'is_allowed', return_value=False):
            await mock_consumer.receive(text_data=json.dumps({
                'type': 'ai_stream', 'action': 'summarize', 'text': '測試'
            }))

        messages = self._sent_messages(mock_consumer)
        assert len(messages) == 1
        assert messages[0]['type'] == 'ai_stream_error'
        assert '頻繁' in messages[0]['message']
        assert getattr(mock_consumer, '_ai_stream_task', None) is None

    async def test_ai_stream_invalid_action(self, mock_consumer):
        """無效 action：回傳 ai_stream_error（驗證在速率限制之前）"""
        await mock_consumer.receive(text_data=json.dumps({
            'type': 'ai_stream', 'action': 'translate', 'text': '測試'
        }))

        messages = self._sent_messages(mock_consumer)
        assert len(messages) == 1
        assert messages[0]['type'] == 'ai_stream_error'

    async def test_ai_stream_service_error_sends_stream_error(self, mock_consumer):
        """串流期間服務拋錯：start 之後回傳 ai_stream_error"""
        async def failing_stream(action, text):
            raise RuntimeError('AI 服務暫時無法使用')
            yield  # pragma: no cover - 使函式成為 async generator

        with patch.object(ai_service, 'process_stream', failing_stream), \
                patch.object(ai_rate_limiter, 'is_allowed', return_value=True):
            await mock_consumer.receive(text_data=json.dumps({
                'type': 'ai_stream', 'action': 'polish', 'text': '測試'
            }))
            await mock_consumer._ai_stream_task

        messages = self._sent_messages(mock_consumer)
        assert messages[0]['type'] == 'ai_stream_start'
        assert messages[-1]['type'] == 'ai_stream_error'
        assert messages[-1]['message'] == 'AI 服務暫時無法使用'

    async def test_ai_stream_cancel_stops_task(self, mock_consumer):
        """收到 ai_stream_cancel：取消進行中的串流任務"""
        started = asyncio.Event()

        async def slow_stream(action, text):
            started.set()
            for i in range(1000):
                yield f'chunk{i}'
                await asyncio.sleep(0.01)

        with patch.object(ai_service, 'process_stream', slow_stream), \
                patch.object(ai_rate_limiter, 'is_allowed', return_value=True):
            await mock_consumer.receive(text_data=json.dumps({
                'type': 'ai_stream', 'action': 'summarize', 'text': '測試'
            }))
            await started.wait()
            await mock_consumer.handle_ai_stream_cancel()

            with pytest.raises(asyncio.CancelledError):
                await mock_consumer._ai_stream_task

    async def test_ai_stream_busy_rejects_second_request(self, mock_consumer):
        """已有串流進行中時，第二個請求被拒（ai_stream_error）"""
        release = asyncio.Event()

        async def blocking_stream(action, text):
            await release.wait()
            yield '完成'

        with patch.object(ai_service, 'process_stream', blocking_stream), \
                patch.object(ai_rate_limiter, 'is_allowed', return_value=True):
            # 第一個請求：啟動後卡在 release.wait()
            await mock_consumer.receive(text_data=json.dumps({
                'type': 'ai_stream', 'action': 'summarize', 'text': '第一個'
            }))
            await asyncio.sleep(0)  # 讓背景任務開始執行
            # 第二個請求：應被拒
            await mock_consumer.receive(text_data=json.dumps({
                'type': 'ai_stream', 'action': 'summarize', 'text': '第二個'
            }))

            busy_messages = [
                m for m in self._sent_messages(mock_consumer)
                if m['type'] == 'ai_stream_error'
            ]
            assert len(busy_messages) == 1
            assert '進行中' in busy_messages[0]['message']

            # 收尾：放行第一個任務並等待完成
            release.set()
            await mock_consumer._ai_stream_task

    async def test_ai_ask_stream_sends_start_chunks_end(self, mock_consumer):
        """文件問答串流：依序送出 start → chunk(s) → end（action 標籤為 ask）"""
        async def fake_ask_stream(question, document_text):
            for c in ['根據', '文件']:
                yield c

        with patch.object(ai_service, 'ask_stream', fake_ask_stream), \
                patch.object(ai_rate_limiter, 'is_allowed', return_value=True):
            await mock_consumer.receive(text_data=json.dumps({
                'type': 'ai_ask_stream', 'question': '重點是什麼？', 'document_text': '文件內容'
            }))
            await mock_consumer._ai_stream_task

        messages = self._sent_messages(mock_consumer)
        assert [m['type'] for m in messages] == [
            'ai_stream_start', 'ai_stream_chunk', 'ai_stream_chunk', 'ai_stream_end'
        ]
        chunks = [m['chunk'] for m in messages if m['type'] == 'ai_stream_chunk']
        assert chunks == ['根據', '文件']
        assert messages[0]['action'] == 'ask'

    async def test_ai_ask_stream_missing_question(self, mock_consumer):
        """缺少 question：回傳 ai_stream_error（驗證在速率限制之前），不啟動串流任務"""
        await mock_consumer.receive(text_data=json.dumps({
            'type': 'ai_ask_stream', 'document_text': '文件內容'
        }))

        messages = self._sent_messages(mock_consumer)
        assert len(messages) == 1
        assert messages[0]['type'] == 'ai_stream_error'
        assert getattr(mock_consumer, '_ai_stream_task', None) is None

    async def test_ai_ask_stream_oversized_payload_rejected_before_parse(self, mock_consumer):
        """超大 ai_ask_stream payload 在解析與啟動串流前即被大小檢查擋下，
        不會被完整讀進記憶體，也不會啟動串流任務"""
        huge_doc = 'x' * (MAX_MESSAGE_SIZE + 1000)
        await mock_consumer.receive(text_data=json.dumps({
            'type': 'ai_ask_stream', 'question': '重點？', 'document_text': huge_doc
        }))

        messages = self._sent_messages(mock_consumer)
        assert len(messages) == 1
        assert messages[0]['type'] == 'error'
        assert messages[0]['error_code'] == 'MESSAGE_TOO_LARGE'
        assert getattr(mock_consumer, '_ai_stream_task', None) is None


