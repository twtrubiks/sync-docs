"""
JWT認證中間件測試模組
測試WebSocket連接的JWT認證功能
"""

import time

import pytest
import jwt
from django.conf import settings
from django.contrib.auth.models import User, AnonymousUser
from docs_app.auth_middleware import JWTAuthMiddleware, extract_token_from_subprotocol

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
    # 驗證token能被正確解析
    payload = jwt.decode(valid_jwt_token, settings.SECRET_KEY, algorithms=["HS256"])
    assert payload.get('user_id') == test_user.id
    assert payload.get('username') == test_user.username


def test_expired_jwt_token_parsing(test_user, expired_jwt_token):
    """測試過期JWT token的解析"""
    # 驗證過期token會拋出異常
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(expired_jwt_token, settings.SECRET_KEY, algorithms=["HS256"])

def test_invalid_jwt_token_parsing(invalid_jwt_token):
    """測試無效JWT token的解析"""
    # 驗證無效token會拋出異常
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(invalid_jwt_token, settings.SECRET_KEY, algorithms=["HS256"])

def test_jwt_middleware_initialization():
    """測試JWT中間件初始化"""
    middleware = JWTAuthMiddleware(MockConsumer())
    assert middleware is not None
    assert middleware.app is not None


# ===== Subprotocol Token 提取測試 =====

def test_extract_token_from_valid_subprotocol():
    """測試從有效 subprotocol 提取 token"""
    subprotocols = ['access_token.eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxx']
    token = extract_token_from_subprotocol(subprotocols)
    assert token == 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xxx'


def test_extract_token_from_multiple_subprotocols():
    """測試從多個 subprotocol 中提取 token"""
    subprotocols = ['graphql', 'access_token.mytoken', 'json']
    token = extract_token_from_subprotocol(subprotocols)
    assert token == 'mytoken'


def test_extract_token_from_empty_subprotocols():
    """測試空 subprotocol 列表"""
    subprotocols = []
    token = extract_token_from_subprotocol(subprotocols)
    assert token is None


def test_extract_token_from_no_access_token_subprotocol():
    """測試沒有 access_token 的 subprotocol 列表"""
    subprotocols = ['graphql', 'json']
    token = extract_token_from_subprotocol(subprotocols)
    assert token is None


def test_extract_token_with_empty_token_value():
    """測試 access_token. 後沒有值的情況"""
    subprotocols = ['access_token.']
    token = extract_token_from_subprotocol(subprotocols)
    assert token == ''  # 返回空字符串，由後續驗證處理


def test_extract_token_from_subprotocol_with_dots():
    """測試 token 本身包含點號的情況（JWT 格式）"""
    jwt_token = 'eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoxfQ.signature'
    subprotocols = [f'access_token.{jwt_token}']
    token = extract_token_from_subprotocol(subprotocols)
    assert token == jwt_token


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_middleware_with_subprotocol_authentication(test_user, valid_jwt_token):
    """測試中間件通過 subprotocol 認證用戶"""
    scope = {
        'type': 'websocket',
        'subprotocols': [f'access_token.{valid_jwt_token}'],
    }

    received_scope = {}

    async def mock_app(scope, receive, send):
        received_scope.update(scope)

    middleware = JWTAuthMiddleware(mock_app)
    await middleware(scope, None, None)

    assert received_scope['user'].id == test_user.id
    assert received_scope['user'].username == test_user.username
    assert received_scope['accepted_subprotocol'] == f'access_token.{valid_jwt_token}'


@pytest.mark.asyncio
async def test_middleware_with_no_subprotocol():
    """測試中間件在沒有 subprotocol 時返回匿名用戶"""
    scope = {
        'type': 'websocket',
        'subprotocols': [],
    }

    received_scope = {}

    async def mock_app(scope, receive, send):
        received_scope.update(scope)

    middleware = JWTAuthMiddleware(mock_app)
    await middleware(scope, None, None)

    assert isinstance(received_scope['user'], AnonymousUser)
    assert received_scope['accepted_subprotocol'] is None


@pytest.mark.asyncio
async def test_middleware_with_invalid_token_in_subprotocol():
    """測試中間件處理無效 token"""
    scope = {
        'type': 'websocket',
        'subprotocols': ['access_token.invalid.token.here'],
    }

    received_scope = {}

    async def mock_app(scope, receive, send):
        received_scope.update(scope)

    middleware = JWTAuthMiddleware(mock_app)
    await middleware(scope, None, None)

    assert isinstance(received_scope['user'], AnonymousUser)


@pytest.mark.asyncio
async def test_middleware_with_expired_token_in_subprotocol(expired_jwt_token):
    """測試中間件處理過期 token"""
    scope = {
        'type': 'websocket',
        'subprotocols': [f'access_token.{expired_jwt_token}'],
    }

    received_scope = {}

    async def mock_app(scope, receive, send):
        received_scope.update(scope)

    middleware = JWTAuthMiddleware(mock_app)
    await middleware(scope, None, None)

    assert isinstance(received_scope['user'], AnonymousUser)
