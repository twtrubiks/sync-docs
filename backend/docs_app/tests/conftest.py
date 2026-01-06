"""
測試配置檔案
提供共用的測試fixtures和配置
"""

import time

import pytest
import jwt
from django.conf import settings
from django.contrib.auth.models import User
from docs_app.models import Document, DocumentCollaborator, PermissionLevel


@pytest.fixture
def test_user():
    """創建測試用戶的fixture"""
    return User.objects.create_user(
        username="testuser",
        password="testpassword123",
        email="test@example.com"
    )


@pytest.fixture
def another_user():
    """創建另一個測試用戶的fixture"""
    return User.objects.create_user(
        username="anotheruser",
        password="testpassword123",
        email="another@example.com"
    )


@pytest.fixture
def test_document(test_user):
    """創建測試文檔的fixture"""
    return Document.objects.create(
        title="Test Document",
        content={"type": "doc", "content": []},
        owner=test_user
    )


@pytest.fixture
def shared_document(test_user, another_user):
    """創建共享文檔的fixture（編輯權限）"""
    doc = Document.objects.create(
        title="Shared Document",
        content={"type": "doc", "content": []},
        owner=test_user
    )
    DocumentCollaborator.objects.create(
        document=doc,
        user=another_user,
        permission=PermissionLevel.WRITE
    )
    return doc


# ===== 權限相關 Fixtures =====

@pytest.fixture
def read_only_user():
    """創建只讀測試用戶"""
    return User.objects.create_user(
        username="readonlyuser",
        password="testpassword123",
        email="readonly@example.com"
    )


@pytest.fixture
def read_only_shared_document(test_user, read_only_user):
    """創建只讀共享文檔"""
    doc = Document.objects.create(
        title="Read Only Shared Document",
        content={"ops": [{"insert": "\n"}]},
        owner=test_user
    )
    DocumentCollaborator.objects.create(
        document=doc,
        user=read_only_user,
        permission=PermissionLevel.READ
    )
    return doc


@pytest.fixture
def jwt_token_for_read_only_user(read_only_user):
    """生成 read_only_user 的 JWT token"""
    payload = {
        'user_id': read_only_user.id,
        'username': read_only_user.username
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


# ===== WebSocket 整合測試 Fixtures =====

@pytest.fixture
def third_user():
    """創建第三個測試用戶，用於三客戶端測試"""
    return User.objects.create_user(
        username="thirduser",
        password="testpassword123",
        email="third@example.com"
    )


@pytest.fixture
def multi_shared_document(test_user, another_user, third_user):
    """創建三人共享的文檔（都是編輯權限）"""
    doc = Document.objects.create(
        title="Multi Shared Document",
        content={"ops": [{"insert": "\n"}]},
        owner=test_user
    )
    DocumentCollaborator.objects.create(
        document=doc,
        user=another_user,
        permission=PermissionLevel.WRITE
    )
    DocumentCollaborator.objects.create(
        document=doc,
        user=third_user,
        permission=PermissionLevel.WRITE
    )
    return doc


@pytest.fixture
def jwt_token_for_user(test_user):
    """生成 test_user 的 JWT token"""
    payload = {
        'user_id': test_user.id,
        'username': test_user.username
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


@pytest.fixture
def jwt_token_for_another_user(another_user):
    """生成 another_user 的 JWT token"""
    payload = {
        'user_id': another_user.id,
        'username': another_user.username
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


@pytest.fixture
def jwt_token_for_third_user(third_user):
    """生成 third_user 的 JWT token"""
    payload = {
        'user_id': third_user.id,
        'username': third_user.username
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


@pytest.fixture
def expired_jwt_token(test_user):
    """生成已過期的 JWT token"""
    payload = {
        'user_id': test_user.id,
        'username': test_user.username,
        'exp': int(time.time()) - 3600  # 1 小時前過期
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


@pytest.fixture
def invalid_jwt_token():
    """生成無效的 JWT token"""
    return "invalid.token.here"


@pytest.fixture
def jwt_token_for_nonexistent_user():
    """生成不存在用戶的 JWT token"""
    payload = {
        'user_id': 99999,
        'username': 'nonexistent'
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


@pytest.fixture
def mock_connection_manager():
    """
    Mock connection_manager 以避免測試時的 Redis 依賴。
    所有連線操作都會成功，不實際連接 Redis。
    """
    from unittest.mock import patch, AsyncMock
    from docs_app import connection_manager as cm_module

    # 創建 async mock 函數
    async_true = AsyncMock(return_value=True)
    async_none = AsyncMock(return_value=None)

    # Mock 所有 async 方法
    with patch.object(cm_module.connection_manager, 'add_connection', async_true), \
         patch.object(cm_module.connection_manager, 'remove_connection', async_none), \
         patch.object(cm_module.connection_manager, 'refresh_connection', async_none), \
         patch.object(cm_module.connection_manager, 'get_connection_count', AsyncMock(return_value=0)):
        yield cm_module.connection_manager


@pytest.fixture
def websocket_application(settings, mock_connection_manager):
    """
    WebSocket ASGI 應用，使用 InMemoryChannelLayer 避免 Redis 依賴
    """
    # 覆蓋 channel layer 設定
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer"
        }
    }

    # 延遲 import：必須在修改 settings.CHANNEL_LAYERS 後才 import，
    # 因為這些模組在 import 時會讀取 channel layer 設定
    from channels.routing import ProtocolTypeRouter, URLRouter
    from docs_app.auth_middleware import JWTAuthMiddleware
    import docs_app.routing

    return ProtocolTypeRouter({
        "websocket": JWTAuthMiddleware(
            URLRouter(docs_app.routing.websocket_urlpatterns)
        ),
    })
