import jwt
import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async

User = get_user_model()
logger = logging.getLogger('docs_app')


# 認證錯誤類型
class AuthErrorType:
    """認證錯誤類型常量"""
    NO_TOKEN = 'NO_TOKEN'
    TOKEN_EXPIRED = 'TOKEN_EXPIRED'
    INVALID_TOKEN = 'INVALID_TOKEN'
    USER_NOT_FOUND = 'USER_NOT_FOUND'


@database_sync_to_async
def get_user(user_id):
    try:
        if user_id is None:
            return AnonymousUser()
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()


def extract_token_from_subprotocol(subprotocols):
    """
    從 WebSocket subprotocol 提取 JWT token

    Subprotocol 格式: 'access_token.<JWT_TOKEN>'

    Args:
        subprotocols: WebSocket subprotocol 列表

    Returns:
        str or None: 提取的 JWT token，如果沒有找到則返回 None
    """
    for protocol in subprotocols:
        if protocol.startswith('access_token.'):
            return protocol[len('access_token.'):]
    return None


class JWTAuthMiddleware:
    """
    Custom middleware for Django Channels to authenticate users via JWT in WebSocket subprotocol.

    前端連接時使用: new WebSocket(url, ['access_token.<JWT_TOKEN>'])

    認證結果會存儲在 scope 中:
    - scope['user']: 認證成功的用戶對象，或 AnonymousUser
    - scope['auth_error']: 認證錯誤類型（None 表示成功）
    - scope['accepted_subprotocol']: 接受的 subprotocol
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # 從 subprotocol 提取 token
        subprotocols = scope.get('subprotocols', [])
        token = extract_token_from_subprotocol(subprotocols)

        # 記錄接受的 subprotocol 和認證錯誤
        accepted_subprotocol = None
        auth_error = None

        if token:
            try:
                # Decode the token to get user_id
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = payload.get('user_id')
                user = await get_user(user_id)

                if user.is_authenticated:
                    scope['user'] = user
                    # 記錄使用的 subprotocol
                    for protocol in subprotocols:
                        if protocol.startswith('access_token.'):
                            accepted_subprotocol = protocol
                            break
                    logger.debug(f"用戶 {user.username} 認證成功")
                else:
                    # user_id 有效但用戶不存在
                    scope['user'] = AnonymousUser()
                    auth_error = AuthErrorType.USER_NOT_FOUND
                    logger.warning(f"用戶 ID {user_id} 不存在")

            except jwt.ExpiredSignatureError:
                scope['user'] = AnonymousUser()
                auth_error = AuthErrorType.TOKEN_EXPIRED
                logger.warning("JWT token 已過期")

            except jwt.InvalidTokenError as e:
                scope['user'] = AnonymousUser()
                auth_error = AuthErrorType.INVALID_TOKEN
                logger.warning(f"無效的 JWT token: {str(e)}")
        else:
            scope['user'] = AnonymousUser()
            auth_error = AuthErrorType.NO_TOKEN
            logger.debug("未提供認證 token")

        # 保存認證結果供 consumer 使用
        scope['auth_error'] = auth_error
        scope['accepted_subprotocol'] = accepted_subprotocol

        return await self.app(scope, receive, send)
