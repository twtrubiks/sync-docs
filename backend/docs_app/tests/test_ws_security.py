"""
WebSocket 安全機制測試
測試認證失敗回傳、連接限制、速率限制
"""

import pytest
import asyncio
from channels.testing import WebsocketCommunicator
from unittest.mock import patch, AsyncMock

from docs_app.consumers import WSCloseCodes
from docs_app.connection_manager import ConnectionManager
from docs_app.rate_limiter import RateLimiter

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio
]


class TestAuthErrorResponse:
    """測試認證失敗原因回傳"""

    async def test_expired_token_returns_error_before_close(
        self, websocket_application, test_document, expired_jwt_token
    ):
        """測試過期 token 連接時收到錯誤原因"""
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/",
            subprotocols=[f"access_token.{expired_jwt_token}"]
        )

        connected, _ = await communicator.connect()
        assert connected is True  # 先接受連接以便發送錯誤

        # 應該收到錯誤消息
        response = await communicator.receive_json_from(timeout=2)
        assert response['type'] == 'connection_error'
        assert response['error_code'] == 'TOKEN_EXPIRED'
        assert 'expired' in response['message'].lower()

        await communicator.disconnect()

    async def test_invalid_token_returns_error(
        self, websocket_application, test_document, invalid_jwt_token
    ):
        """測試無效 token 連接時收到錯誤原因"""
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/",
            subprotocols=[f"access_token.{invalid_jwt_token}"]
        )

        connected, _ = await communicator.connect()
        assert connected is True

        response = await communicator.receive_json_from(timeout=2)
        assert response['type'] == 'connection_error'
        assert response['error_code'] == 'INVALID_TOKEN'

        await communicator.disconnect()

    async def test_no_token_returns_error(
        self, websocket_application, test_document
    ):
        """測試無 token 連接時收到錯誤原因"""
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/",
            subprotocols=[]  # 無 token
        )

        connected, _ = await communicator.connect()
        assert connected is True

        response = await communicator.receive_json_from(timeout=2)
        assert response['type'] == 'connection_error'
        assert response['error_code'] == 'NO_TOKEN'

        await communicator.disconnect()

    async def test_permission_denied_returns_error(
        self, websocket_application, test_document, jwt_token_for_another_user
    ):
        """測試無權限用戶收到權限錯誤"""
        # another_user 沒有訪問 test_document 的權限
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        connected, _ = await communicator.connect()
        assert connected is True

        response = await communicator.receive_json_from(timeout=2)
        assert response['type'] == 'connection_error'
        assert response['error_code'] == 'PERMISSION_DENIED'

        await communicator.disconnect()

    async def test_document_not_found_returns_error(
        self, websocket_application, jwt_token_for_user
    ):
        """測試文檔不存在時收到錯誤"""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{fake_uuid}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        connected, _ = await communicator.connect()
        assert connected is True

        response = await communicator.receive_json_from(timeout=2)
        assert response['type'] == 'connection_error'
        assert response['error_code'] == 'DOCUMENT_NOT_FOUND'

        await communicator.disconnect()

    async def test_valid_owner_connection_success(
        self, websocket_application, test_document, jwt_token_for_user
    ):
        """測試文檔擁有者可以成功連接"""
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{test_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        connected, _ = await communicator.connect()
        assert connected is True

        # 不應該收到錯誤消息
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                communicator.receive_json_from(),
                timeout=0.5
            )

        await communicator.disconnect()

    async def test_valid_collaborator_connection_success(
        self, websocket_application, shared_document, jwt_token_for_another_user
    ):
        """測試協作者可以成功連接"""
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_another_user}"]
        )

        connected, _ = await communicator.connect()
        assert connected is True

        # 不應該收到錯誤消息
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                communicator.receive_json_from(),
                timeout=0.5
            )

        await communicator.disconnect()


class TestConnectionLimit:
    """測試連接數量限制"""

    async def test_connection_within_limit_succeeds(
        self, websocket_application, shared_document, jwt_token_for_user
    ):
        """測試在限制內的連接成功"""
        communicators = []

        try:
            # 連接 2 個（在默認限制 5 內）
            for _ in range(2):
                comm = WebsocketCommunicator(
                    websocket_application,
                    f"/ws/docs/{shared_document.id}/",
                    subprotocols=[f"access_token.{jwt_token_for_user}"]
                )
                connected, _ = await comm.connect()
                assert connected is True
                communicators.append(comm)

                # 確認沒有錯誤消息
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        comm.receive_json_from(),
                        timeout=0.3
                    )

        finally:
            for comm in communicators:
                await comm.disconnect()

    async def test_exceeds_connection_limit_rejected(
        self, websocket_application, shared_document, jwt_token_for_user, test_user
    ):
        """測試超過連接數限制時被拒絕"""
        communicators = []

        # Mock add_connection 方法來模擬達到限制
        with patch(
            'docs_app.consumers.connection_manager.add_connection',
            new_callable=AsyncMock
        ) as mock_add:
            # 前兩個連接成功，第三個失敗
            mock_add.side_effect = [True, True, False]

            try:
                # 建立 2 個連接（應該成功）
                for i in range(2):
                    comm = WebsocketCommunicator(
                        websocket_application,
                        f"/ws/docs/{shared_document.id}/",
                        subprotocols=[f"access_token.{jwt_token_for_user}"]
                    )
                    connected, _ = await comm.connect()
                    assert connected is True
                    communicators.append(comm)

                # 第 3 個連接應該收到錯誤
                comm3 = WebsocketCommunicator(
                    websocket_application,
                    f"/ws/docs/{shared_document.id}/",
                    subprotocols=[f"access_token.{jwt_token_for_user}"]
                )
                connected, _ = await comm3.connect()
                assert connected is True  # 先接受以發送錯誤

                response = await comm3.receive_json_from(timeout=2)
                assert response['type'] == 'connection_error'
                assert response['error_code'] == 'TOO_MANY_CONNECTIONS'
                communicators.append(comm3)

            finally:
                for comm in communicators:
                    await comm.disconnect()


class TestRateLimiting:
    """測試消息頻率限制"""

    async def test_messages_within_limit_succeed(
        self, websocket_application, shared_document, jwt_token_for_user
    ):
        """測試在限制內的消息成功發送"""
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        try:
            await communicator.connect()

            # Mock rate_limiter 允許所有消息
            with patch(
                'docs_app.consumers.rate_limiter.is_allowed',
                new_callable=AsyncMock
            ) as mock_is_allowed:
                mock_is_allowed.return_value = (True, {
                    'remaining': 29, 'limit': 30, 'window': 10, 'retry_after': 0
                })

                # 發送消息
                await communicator.send_json_to({
                    "delta": {"ops": [{"insert": "test"}]}
                })

                # 不應該收到錯誤
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        communicator.receive_json_from(),
                        timeout=0.3
                    )

        finally:
            await communicator.disconnect()

    async def test_rate_limit_exceeded_returns_error(
        self, websocket_application, shared_document, jwt_token_for_user
    ):
        """測試超過速率限制時收到錯誤"""
        communicator = WebsocketCommunicator(
            websocket_application,
            f"/ws/docs/{shared_document.id}/",
            subprotocols=[f"access_token.{jwt_token_for_user}"]
        )

        try:
            await communicator.connect()

            # Mock rate_limiter 拒絕消息
            with patch(
                'docs_app.consumers.rate_limiter.is_allowed',
                new_callable=AsyncMock
            ) as mock_is_allowed:
                mock_is_allowed.return_value = (False, {
                    'remaining': 0, 'limit': 30, 'window': 10, 'retry_after': 5.5
                })

                # 發送消息
                await communicator.send_json_to({
                    "delta": {"ops": [{"insert": "test"}]}
                })

                # 應該收到速率限制錯誤
                response = await communicator.receive_json_from(timeout=2)
                assert response['type'] == 'error'
                assert response['error_code'] == 'RATE_LIMITED'
                assert 'retry_after' in response
                assert response['retry_after'] == 5.5

        finally:
            await communicator.disconnect()


class TestConnectionManagerUnit:
    """連接管理器單元測試（Mock Redis）"""

    async def test_add_connection_success(self):
        """測試成功添加連接"""
        manager = ConnectionManager()

        with patch.object(manager, 'get_redis', new_callable=AsyncMock) as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.eval.return_value = 1  # 成功

            result = await manager.add_connection(1, "channel_1")
            assert result is True

    async def test_add_connection_exceeds_limit(self):
        """測試超過限制"""
        manager = ConnectionManager()

        with patch.object(manager, 'get_redis', new_callable=AsyncMock) as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.eval.return_value = 0  # 失敗

            result = await manager.add_connection(1, "channel_3")
            assert result is False

    async def test_remove_connection(self):
        """測試移除連接"""
        manager = ConnectionManager()

        with patch.object(manager, 'get_redis', new_callable=AsyncMock) as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.srem = AsyncMock()
            mock_redis_instance.scard = AsyncMock(return_value=0)

            await manager.remove_connection(1, "channel_1")
            mock_redis_instance.srem.assert_called_once()


class TestRateLimiterUnit:
    """速率限制器單元測試（Mock Redis）"""

    async def test_allows_under_limit(self):
        """測試未達限制時允許"""
        limiter = RateLimiter()

        with patch.object(limiter, 'get_redis', new_callable=AsyncMock) as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.eval.return_value = [1, 5, 0]  # allowed, count, retry_after

            allowed, info = await limiter.is_allowed(1, "doc_1")
            assert allowed is True
            assert info['remaining'] == 25  # 30 - 5

    async def test_blocks_over_limit(self):
        """測試超過限制時阻止"""
        limiter = RateLimiter()

        with patch.object(limiter, 'get_redis', new_callable=AsyncMock) as mock_redis:
            mock_redis_instance = AsyncMock()
            mock_redis.return_value = mock_redis_instance
            mock_redis_instance.eval.return_value = [0, 30, 5000]  # blocked, count, retry_after_ms

            allowed, info = await limiter.is_allowed(1, "doc_1")
            assert allowed is False
            assert info['remaining'] == 0
            assert info['retry_after'] == 5.0  # 5000ms = 5s


class TestWSCloseCodes:
    """測試 WebSocket 關閉代碼定義"""

    def test_close_codes_in_valid_range(self):
        """測試關閉代碼在有效範圍內 (4000-4999)"""
        codes = [
            WSCloseCodes.AUTH_FAILED,
            WSCloseCodes.TOKEN_EXPIRED,
            WSCloseCodes.PERMISSION_DENIED,
            WSCloseCodes.DOCUMENT_NOT_FOUND,
            WSCloseCodes.TOO_MANY_CONNECTIONS,
            WSCloseCodes.INVALID_MESSAGE,
            WSCloseCodes.MESSAGE_TOO_LARGE,
            WSCloseCodes.RATE_LIMITED,
        ]

        for code in codes:
            assert 4000 <= code <= 4999, f"Code {code} is not in valid range"

    def test_close_codes_are_unique(self):
        """測試關閉代碼唯一"""
        codes = [
            WSCloseCodes.AUTH_FAILED,
            WSCloseCodes.TOKEN_EXPIRED,
            WSCloseCodes.PERMISSION_DENIED,
            WSCloseCodes.DOCUMENT_NOT_FOUND,
            WSCloseCodes.TOO_MANY_CONNECTIONS,
            WSCloseCodes.INVALID_MESSAGE,
            WSCloseCodes.MESSAGE_TOO_LARGE,
            WSCloseCodes.RATE_LIMITED,
        ]

        assert len(codes) == len(set(codes)), "Close codes are not unique"
