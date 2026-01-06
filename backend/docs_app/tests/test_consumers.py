"""
WebSocket消費者測試模組
測試文檔協作的WebSocket功能
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from django.contrib.auth.models import AnonymousUser
from docs_app.consumers import DocConsumer, MAX_MESSAGE_SIZE, MAX_OPS_COUNT

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


