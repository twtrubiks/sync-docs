"""
WebSocket 整合測試模組

使用 WebsocketCommunicator 測試 Mock 無法覆蓋的實際 WebSocket 連接行為：
- 實際連接握手和權限驗證
- 多客戶端之間的消息廣播
- Echo Prevention（發送者不收到自己的消息）
- 並發連接場景
- Unicode 端到端傳輸
"""

import asyncio
import pytest
from channels.testing import WebsocketCommunicator

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio
]


async def consume_connection_success(communicator, timeout=2):
    """
    消費並驗證 connection_success 訊息及後續的 presence_sync 訊息

    連接成功後，伺服器會發送：
    1. connection_success 訊息
    2. presence_sync 訊息

    測試需要先消費這些訊息才能進行後續操作。
    """
    response = await communicator.receive_json_from(timeout=timeout)
    assert response['type'] == 'connection_success'

    # 消費 presence_sync（新功能）
    presence_response = await communicator.receive_json_from(timeout=timeout)
    assert presence_response['type'] == 'presence_sync'

    return response


async def consume_initial_messages(communicator, timeout=2):
    """
    消費所有初始消息（connection_success, presence_sync, 可能的 user_join）

    適用於多客戶端測試，返回所有收到的初始消息。
    """
    messages = []
    response = await communicator.receive_json_from(timeout=timeout)
    assert response['type'] == 'connection_success'
    messages.append(response)

    # 消費 presence_sync
    presence_response = await communicator.receive_json_from(timeout=timeout)
    assert presence_response['type'] == 'presence_sync'
    messages.append(presence_response)

    return messages


async def consume_user_join_if_any(communicator, timeout=0.3):
    """
    嘗試消費 user_join 消息（如果有的話）

    在多客戶端測試中，先連接的客戶端可能會收到 user_join 消息。
    """
    try:
        msg = await asyncio.wait_for(
            communicator.receive_json_from(), timeout=timeout
        )
        if msg.get('type') == 'user_join':
            return msg
        return None
    except asyncio.TimeoutError:
        return None


class TestWebSocketConnection:
    """
    測試 WebSocket 連接場景

    驗證實際的 WebSocket 握手和權限檢查，
    這些是 Mock 測試無法覆蓋的。
    """

    async def test_owner_can_connect(
        self,
        websocket_application,
        test_document,
        jwt_token_for_user
    ):
        """測試文檔擁有者可以成功連接"""
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        try:
            connected, subprotocol = await communicator.connect()
            assert connected is True
            assert subprotocol == f"access_token.{jwt_token_for_user}"
        finally:
            await communicator.disconnect()

    async def test_collaborator_can_connect(
        self,
        websocket_application,
        shared_document,
        jwt_token_for_another_user
    ):
        """測試協作者可以成功連接到共享文檔"""
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        try:
            connected, subprotocol = await communicator.connect()
            assert connected is True
        finally:
            await communicator.disconnect()

    async def test_unauthorized_user_rejected(
        self,
        websocket_application,
        test_document,
        jwt_token_for_another_user
    ):
        """測試無權限的用戶連接會被拒絕"""
        # another_user 沒有 test_document 的訪問權限
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        connected, _ = await communicator.connect()
        # 連接會先被接受，然後發送錯誤消息並關閉
        assert connected is True

        # 應該收到權限錯誤消息
        response = await communicator.receive_json_from(timeout=2)
        assert response['type'] == 'connection_error'
        assert response['error_code'] == 'PERMISSION_DENIED'

        await communicator.disconnect()

    async def test_anonymous_user_rejected(
        self,
        websocket_application,
        test_document
    ):
        """測試匿名用戶（無 token）連接會被拒絕"""
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/"
            # 沒有 subprotocols，即沒有 token
        )

        connected, _ = await communicator.connect()
        # 連接會先被接受，然後發送錯誤消息並關閉
        assert connected is True

        # 應該收到認證錯誤消息
        response = await communicator.receive_json_from(timeout=2)
        assert response['type'] == 'connection_error'
        assert response['error_code'] == 'NO_TOKEN'

        await communicator.disconnect()


class TestWebSocketReadOnlyPermission:
    """
    測試 WebSocket 只讀權限場景

    驗證只讀用戶可以連接但無法編輯。
    """

    async def test_read_only_user_cannot_send_delta(
        self,
        websocket_application,
        read_only_shared_document,
        jwt_token_for_user,
        jwt_token_for_read_only_user
    ):
        """測試只讀用戶發送 delta 會被拒絕"""
        # 擁有者連接
        comm_owner = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{read_only_shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        # 只讀用戶連接
        comm_read_only = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{read_only_shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_read_only_user}"]
        )

        try:
            await comm_owner.connect()
            await comm_read_only.connect()

            # 消費 connection_success 和 presence_sync
            owner_response = await consume_connection_success(comm_owner)
            read_only_response = await consume_connection_success(comm_read_only)

            # 消費可能的 user_join
            await consume_user_join_if_any(comm_owner)

            # 驗證只讀用戶 can_write=False
            assert owner_response['can_write'] is True
            assert read_only_response['can_write'] is False

            # 只讀用戶嘗試發送 delta
            await comm_read_only.send_json_to({
                "delta": {"ops": [{"insert": "test"}]}
            })

            # 應該收到 READ_ONLY 錯誤
            error_response = await comm_read_only.receive_json_from(timeout=2)
            assert error_response['type'] == 'error'
            assert error_response['error_code'] == 'READ_ONLY'

        finally:
            await comm_owner.disconnect()
            await comm_read_only.disconnect()

    async def test_read_only_user_receives_broadcast(
        self,
        websocket_application,
        read_only_shared_document,
        jwt_token_for_user,
        jwt_token_for_read_only_user
    ):
        """測試只讀用戶可以接收其他用戶的廣播"""
        # 擁有者連接
        comm_owner = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{read_only_shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        # 只讀用戶連接
        comm_read_only = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{read_only_shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_read_only_user}"]
        )

        try:
            await comm_owner.connect()
            await comm_read_only.connect()

            # 消費 connection_success 和 presence_sync
            await consume_connection_success(comm_owner)
            await consume_connection_success(comm_read_only)

            # 消費可能的 user_join
            await consume_user_join_if_any(comm_owner)

            # 擁有者發送 delta
            await comm_owner.send_json_to({
                "delta": {"ops": [{"insert": "Hello from owner"}]}
            })

            # 只讀用戶應該收到廣播
            response = await comm_read_only.receive_json_from(timeout=2)
            assert response['type'] == 'doc_update'
            assert response['delta']['ops'][0]['insert'] == 'Hello from owner'

        finally:
            await comm_owner.disconnect()
            await comm_read_only.disconnect()


class TestWebSocketBroadcast:
    """
    測試 WebSocket 廣播功能

    驗證多客戶端之間的消息傳遞，
    這是 Mock 測試無法模擬的真實場景。
    """

    async def test_broadcast_to_other_client(
        self,
        websocket_application,
        shared_document,
        jwt_token_for_user,
        jwt_token_for_another_user
    ):
        """測試客戶端 A 發送消息，客戶端 B 能收到"""
        # 擁有者連接
        comm_owner = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        # 協作者連接
        comm_collaborator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        try:
            connected_owner, _ = await comm_owner.connect()
            connected_collaborator, _ = await comm_collaborator.connect()

            assert connected_owner is True
            assert connected_collaborator is True

            # 消費 connection_success 和 presence_sync 訊息
            await consume_connection_success(comm_owner)
            await consume_connection_success(comm_collaborator)

            # 消費 owner 可能收到的 user_join（collaborator 加入）
            await consume_user_join_if_any(comm_owner)

            # 擁有者發送 delta
            delta_message = {
                "delta": {
                    "ops": [{"insert": "Hello from owner"}]
                }
            }
            await comm_owner.send_json_to(delta_message)

            # 協作者應該收到廣播
            response = await comm_collaborator.receive_json_from(timeout=2)

            assert response["type"] == "doc_update"
            assert response["delta"]["ops"][0]["insert"] == "Hello from owner"

        finally:
            await comm_owner.disconnect()
            await comm_collaborator.disconnect()

    async def test_sender_excluded_from_broadcast(
        self,
        websocket_application,
        shared_document,
        jwt_token_for_user,
        jwt_token_for_another_user
    ):
        """測試發送者不會收到自己發送的消息（Echo Prevention）"""
        # 擁有者連接
        comm_owner = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        # 協作者連接
        comm_collaborator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        try:
            await comm_owner.connect()
            await comm_collaborator.connect()

            # 消費 connection_success 和 presence_sync 訊息
            await consume_connection_success(comm_owner)
            await consume_connection_success(comm_collaborator)

            # 消費 owner 可能收到的 user_join
            await consume_user_join_if_any(comm_owner)

            # 擁有者發送 delta
            delta_message = {
                "delta": {
                    "ops": [{"insert": "Test message"}]
                }
            }
            await comm_owner.send_json_to(delta_message)

            # 協作者應該收到
            response = await comm_collaborator.receive_json_from(timeout=2)
            assert response["type"] == "doc_update"

            # 擁有者不應該收到自己的消息
            nothing_received = await comm_owner.receive_nothing(timeout=0.5)
            assert nothing_received is True

        finally:
            await comm_owner.disconnect()
            await comm_collaborator.disconnect()

    async def test_three_clients_broadcast(
        self,
        websocket_application,
        multi_shared_document,
        jwt_token_for_user,
        jwt_token_for_another_user,
        jwt_token_for_third_user
    ):
        """測試三個客戶端的廣播：一個發送，其他兩個接收"""
        # 三個客戶端連接
        comm_1 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{multi_shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )
        comm_2 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{multi_shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )
        comm_3 = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{multi_shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_third_user}"]
        )

        try:
            await comm_1.connect()
            await comm_2.connect()
            await comm_3.connect()

            # 消費 connection_success 和 presence_sync 訊息
            await consume_connection_success(comm_1)
            await consume_connection_success(comm_2)
            await consume_connection_success(comm_3)

            # 消費可能的 user_join 消息
            await consume_user_join_if_any(comm_1)
            await consume_user_join_if_any(comm_1)  # 可能收到兩個 user_join
            await consume_user_join_if_any(comm_2)

            # 客戶端 1 發送
            delta_message = {
                "delta": {
                    "ops": [{"insert": "Broadcast to all"}]
                }
            }
            await comm_1.send_json_to(delta_message)

            # 客戶端 2 和 3 都應該收到
            response_2 = await comm_2.receive_json_from(timeout=2)
            response_3 = await comm_3.receive_json_from(timeout=2)

            assert response_2["type"] == "doc_update"
            assert response_3["type"] == "doc_update"
            assert response_2["delta"]["ops"][0]["insert"] == "Broadcast to all"
            assert response_3["delta"]["ops"][0]["insert"] == "Broadcast to all"

            # 發送者不應收到
            nothing = await comm_1.receive_nothing(timeout=0.5)
            assert nothing is True

        finally:
            await comm_1.disconnect()
            await comm_2.disconnect()
            await comm_3.disconnect()


class TestWebSocketConcurrency:
    """
    測試 WebSocket 並發場景

    驗證快速消息發送和同時連接的穩定性。
    """

    async def test_rapid_sequential_messages(
        self,
        websocket_application,
        shared_document,
        jwt_token_for_user,
        jwt_token_for_another_user
    ):
        """測試快速連續發送 10 個 delta，所有消息都能正確傳遞"""
        comm_sender = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )
        comm_receiver = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        try:
            await comm_sender.connect()
            await comm_receiver.connect()

            # 消費 connection_success 和 presence_sync 訊息
            await consume_connection_success(comm_sender)
            await consume_connection_success(comm_receiver)

            # 消費可能的 user_join
            await consume_user_join_if_any(comm_sender)

            # 快速發送 10 個消息
            num_messages = 10
            for i in range(num_messages):
                await comm_sender.send_json_to({
                    "delta": {
                        "ops": [{"insert": f"Message {i}"}]
                    }
                })

            # 接收所有消息
            received_count = 0
            for _ in range(num_messages):
                try:
                    response = await comm_receiver.receive_json_from(timeout=3)
                    if response.get("type") == "doc_update":
                        received_count += 1
                except asyncio.TimeoutError:
                    break

            # 所有消息都應該被接收
            assert received_count == num_messages

        finally:
            await comm_sender.disconnect()
            await comm_receiver.disconnect()

    async def test_simultaneous_connections(
        self,
        websocket_application,
        multi_shared_document,
        jwt_token_for_user,
        jwt_token_for_another_user,
        jwt_token_for_third_user
    ):
        """測試三個用戶同時連接不會產生問題"""
        comms = []
        tokens = [jwt_token_for_user, jwt_token_for_another_user, jwt_token_for_third_user]

        try:
            # 同時創建連接
            for token in tokens:
                comm = WebsocketCommunicator(
                    websocket_application,
                    f"/ws/docs/{multi_shared_document.id}/",
                    subprotocols=[f"access_token.{token}"]
                )
                comms.append(comm)

            # 同時連接
            connect_results = await asyncio.gather(
                *[comm.connect() for comm in comms]
            )

            # 所有連接都應該成功
            for connected, _ in connect_results:
                assert connected is True

        finally:
            # 清理所有連接
            for comm in comms:
                await comm.disconnect()


class TestWebSocketUnicode:
    """
    測試 WebSocket Unicode 端到端傳輸

    驗證各種 Unicode 字符能正確通過 WebSocket 傳輸。
    """

    async def test_unicode_chinese_emoji(
        self,
        websocket_application,
        shared_document,
        jwt_token_for_user,
        jwt_token_for_another_user
    ):
        """測試中文和 emoji 字符能正確傳輸"""
        comm_sender = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )
        comm_receiver = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        try:
            await comm_sender.connect()
            await comm_receiver.connect()

            # 消費 connection_success 和 presence_sync 訊息
            await consume_connection_success(comm_sender)
            await consume_connection_success(comm_receiver)

            # 消費可能的 user_join
            await consume_user_join_if_any(comm_sender)

            # 發送包含中文和 emoji 的消息
            unicode_text = "Hello 世界! 你好 🎉🚀💻 繁體中文測試"
            await comm_sender.send_json_to({
                "delta": {
                    "ops": [{"insert": unicode_text}]
                }
            })

            # 接收並驗證
            response = await comm_receiver.receive_json_from(timeout=2)
            assert response["type"] == "doc_update"
            assert response["delta"]["ops"][0]["insert"] == unicode_text

        finally:
            await comm_sender.disconnect()
            await comm_receiver.disconnect()

    async def test_special_symbols(
        self,
        websocket_application,
        shared_document,
        jwt_token_for_user,
        jwt_token_for_another_user
    ):
        """測試特殊符號和控制字符能正確傳輸"""
        comm_sender = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )
        comm_receiver = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        try:
            await comm_sender.connect()
            await comm_receiver.connect()

            # 消費 connection_success 和 presence_sync 訊息
            await consume_connection_success(comm_sender)
            await consume_connection_success(comm_receiver)

            # 消費可能的 user_join
            await consume_user_join_if_any(comm_sender)

            # 發送包含特殊符號的消息
            special_text = "Symbols: ©®™ <script> &nbsp; \"quotes\" 'apostrophe' \t\n"
            await comm_sender.send_json_to({
                "delta": {
                    "ops": [{"insert": special_text}]
                }
            })

            # 接收並驗證
            response = await comm_receiver.receive_json_from(timeout=2)
            assert response["type"] == "doc_update"
            assert response["delta"]["ops"][0]["insert"] == special_text

        finally:
            await comm_sender.disconnect()
            await comm_receiver.disconnect()
