"""
游標與在線狀態測試

測試 cursor_move、user_join、user_leave、presence_sync 功能
"""

import json
import asyncio
import pytest
from channels.testing import WebsocketCommunicator


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
class TestCursorPresence:
    """游標與在線狀態測試"""

    async def test_cursor_move_broadcast(
        self, websocket_application, shared_document,
        jwt_token_for_user, jwt_token_for_another_user
    ):
        """測試游標位置廣播給其他用戶"""
        # 建立兩個連線（owner 和 collaborator）
        comm1 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )
        comm2 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        connected1, _ = await comm1.connect()
        connected2, _ = await comm2.connect()
        assert connected1 and connected2

        # 清空初始消息（connection_success, presence_sync, user_join）
        await comm1.receive_json_from(timeout=2)  # connection_success
        await comm1.receive_json_from(timeout=2)  # presence_sync

        await comm2.receive_json_from(timeout=2)  # connection_success
        await comm2.receive_json_from(timeout=2)  # presence_sync

        # user1 可能收到 user_join (user2)
        try:
            data = await asyncio.wait_for(comm1.receive_json_from(), timeout=0.5)
            if data.get('type') == 'user_join':
                pass  # 預期
        except asyncio.TimeoutError:
            pass

        # user1 發送游標更新
        await comm1.send_to(text_data=json.dumps({
            'type': 'cursor_move',
            'index': 10,
            'length': 5
        }))

        # user2 應收到游標更新
        data = await comm2.receive_json_from(timeout=2)
        assert data['type'] == 'cursor_move'
        assert data['cursor']['index'] == 10
        assert data['cursor']['length'] == 5
        assert 'timestamp' in data
        assert 'color' in data

        await comm1.disconnect()
        await comm2.disconnect()

    async def test_cursor_not_sent_to_sender(
        self, websocket_application, test_document, jwt_token_for_user
    ):
        """測試游標不發回給發送者"""
        comm = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        await comm.connect()
        await comm.receive_json_from(timeout=2)  # connection_success
        await comm.receive_json_from(timeout=2)  # presence_sync

        # 發送游標更新
        await comm.send_to(text_data=json.dumps({
            'type': 'cursor_move',
            'index': 5,
            'length': 0
        }))

        # 不應收到自己的游標更新（設置超時）
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(comm.receive_from(), timeout=0.5)

        await comm.disconnect()

    async def test_user_join_notification(
        self, websocket_application, shared_document,
        jwt_token_for_user, jwt_token_for_another_user
    ):
        """測試用戶加入通知"""
        comm1 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        await comm1.connect()
        await comm1.receive_json_from(timeout=2)  # connection_success
        await comm1.receive_json_from(timeout=2)  # presence_sync

        # 第二個用戶加入
        comm2 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )
        await comm2.connect()

        # user1 應收到 user_join 通知
        data = await comm1.receive_json_from(timeout=2)
        assert data['type'] == 'user_join'
        assert 'user_id' in data
        assert 'username' in data
        assert 'color' in data

        await comm1.disconnect()
        await comm2.disconnect()

    async def test_user_leave_notification(
        self, websocket_application, shared_document,
        jwt_token_for_user, jwt_token_for_another_user
    ):
        """測試用戶離開通知"""
        comm1 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )
        comm2 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        await comm1.connect()
        await comm2.connect()

        # 清空初始消息
        await comm1.receive_json_from(timeout=2)  # connection_success
        await comm1.receive_json_from(timeout=2)  # presence_sync
        await comm2.receive_json_from(timeout=2)  # connection_success
        await comm2.receive_json_from(timeout=2)  # presence_sync

        # 消費 user_join 通知
        try:
            await asyncio.wait_for(comm1.receive_json_from(), timeout=0.5)
        except asyncio.TimeoutError:
            pass

        # user2 斷開連接
        await comm2.disconnect()

        # user1 應收到 user_leave 通知
        data = await comm1.receive_json_from(timeout=2)
        assert data['type'] == 'user_leave'
        assert 'user_id' in data

        await comm1.disconnect()

    async def test_presence_sync_on_connect(
        self, websocket_application, shared_document,
        jwt_token_for_user, jwt_token_for_another_user
    ):
        """測試連接時同步在線用戶列表"""
        # 第一個用戶連接
        comm1 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )
        await comm1.connect()
        await comm1.receive_json_from(timeout=2)  # connection_success
        sync1 = await comm1.receive_json_from(timeout=2)  # presence_sync
        assert sync1['type'] == 'presence_sync'
        assert 'users' in sync1
        # 第一個用戶連接時，列表裡只有自己
        assert len(sync1['users']) >= 1

        # 第二個用戶連接
        comm2 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )
        await comm2.connect()
        await comm2.receive_json_from(timeout=2)  # connection_success
        sync2 = await comm2.receive_json_from(timeout=2)  # presence_sync
        assert sync2['type'] == 'presence_sync'
        # 第二個用戶連接時，應看到至少兩個用戶（自己和第一個）
        assert len(sync2['users']) >= 2

        await comm1.disconnect()
        await comm2.disconnect()

    async def test_read_only_user_cannot_send_cursor(
        self, websocket_application, read_only_shared_document,
        jwt_token_for_read_only_user
    ):
        """測試只讀用戶無法發送游標更新（靜默忽略）"""
        comm = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{read_only_shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_read_only_user}"]
        )

        await comm.connect()
        data = await comm.receive_json_from(timeout=2)  # connection_success
        assert data['can_write'] is False
        await comm.receive_json_from(timeout=2)  # presence_sync

        # 發送游標更新（應被靜默忽略）
        await comm.send_to(text_data=json.dumps({
            'type': 'cursor_move',
            'index': 10,
            'length': 0
        }))

        # 不應收到任何回應或錯誤
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(comm.receive_from(), timeout=0.5)

        await comm.disconnect()

    async def test_connection_success_includes_color(
        self, websocket_application, test_document, jwt_token_for_user
    ):
        """測試 connection_success 消息包含用戶顏色"""
        comm = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        await comm.connect()
        data = await comm.receive_json_from(timeout=2)  # connection_success

        assert data['type'] == 'connection_success'
        assert 'user_id' in data
        assert 'color' in data
        assert data['color'].startswith('#')  # 顏色為 hex 格式

        await comm.disconnect()

    async def test_cursor_move_invalid_format(
        self, websocket_application, test_document, jwt_token_for_user
    ):
        """測試無效的 cursor_move 格式回傳錯誤"""
        comm = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        await comm.connect()
        await comm.receive_json_from(timeout=2)  # connection_success
        await comm.receive_json_from(timeout=2)  # presence_sync

        # 發送無效格式（缺少 index）
        await comm.send_to(text_data=json.dumps({
            'type': 'cursor_move',
            'length': 0
        }))

        # 應收到錯誤消息
        data = await comm.receive_json_from(timeout=2)
        assert data['type'] == 'error'
        assert data['error_code'] == 'INVALID_CURSOR_MESSAGE'

        await comm.disconnect()
