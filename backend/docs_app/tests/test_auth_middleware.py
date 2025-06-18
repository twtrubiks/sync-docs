"""
JWT認證中間件測試模組
測試WebSocket連接的JWT認證功能
"""

import pytest
import jwt
from django.conf import settings
from django.contrib.auth.models import User, AnonymousUser
from docs_app.auth_middleware import JWTAuthMiddleware

pytestmark = pytest.mark.django_db


@pytest.fixture
def test_user():
    """創建測試用戶"""
    return User.objects.create_user(
        username="testuser",
        password="testpassword",
        email="test@example.com"
    )


@pytest.fixture
def valid_jwt_token(test_user):
    """創建有效的JWT token"""
    payload = {
        'user_id': test_user.id,
        'username': test_user.username
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


@pytest.fixture
def expired_jwt_token(test_user):
    """創建過期的JWT token"""
    import time
    payload = {
        'user_id': test_user.id,
        'username': test_user.username,
        'exp': int(time.time()) - 3600  # 1小時前過期
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


@pytest.fixture
def invalid_jwt_token():
    """創建無效的JWT token"""
    return "invalid.jwt.token"


class MockConsumer:
    """模擬WebSocket消費者用於測試"""
    async def __call__(self, scope, receive, send):
        # 簡單的echo消費者，返回scope中的user信息
        await send({
            'type': 'websocket.accept'
        })

        user = scope.get('user')
        if hasattr(user, 'username'):
            message = f"authenticated:{user.username}"
        else:
            message = "anonymous"

        await send({
            'type': 'websocket.send',
            'text': message
        })


def test_user_creation_and_properties(test_user):
    """測試用戶創建和屬性"""
    assert test_user.username == "testuser"
    assert test_user.is_authenticated
    assert test_user.id is not None

def test_anonymous_user_properties():
    """測試匿名用戶屬性"""
    anonymous_user = AnonymousUser()
    assert not anonymous_user.is_authenticated
    assert anonymous_user.id is None


def test_jwt_token_creation_and_parsing(test_user, valid_jwt_token):
    """測試JWT token的創建和解析"""
    import jwt
    from django.conf import settings

    # 驗證token能被正確解析
    payload = jwt.decode(valid_jwt_token, settings.SECRET_KEY, algorithms=["HS256"])
    assert payload.get('user_id') == test_user.id
    assert payload.get('username') == test_user.username


def test_expired_jwt_token_parsing(test_user, expired_jwt_token):
    """測試過期JWT token的解析"""
    import jwt
    from django.conf import settings

    # 驗證過期token會拋出異常
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(expired_jwt_token, settings.SECRET_KEY, algorithms=["HS256"])

def test_invalid_jwt_token_parsing(invalid_jwt_token):
    """測試無效JWT token的解析"""
    import jwt
    from django.conf import settings

    # 驗證無效token會拋出異常
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(invalid_jwt_token, settings.SECRET_KEY, algorithms=["HS256"])

def test_jwt_middleware_initialization():
    """測試JWT中間件初始化"""
    middleware = JWTAuthMiddleware(MockConsumer())
    assert middleware is not None
    assert middleware.app is not None
