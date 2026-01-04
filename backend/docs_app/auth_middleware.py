import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async

User = get_user_model()


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
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # 從 subprotocol 提取 token
        subprotocols = scope.get('subprotocols', [])
        token = extract_token_from_subprotocol(subprotocols)

        # 記錄接受的 subprotocol
        accepted_subprotocol = None

        if token:
            try:
                # Decode the token to get user_id
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = payload.get('user_id')
                scope['user'] = await get_user(user_id)

                # 記錄使用的 subprotocol
                for protocol in subprotocols:
                    if protocol.startswith('access_token.'):
                        accepted_subprotocol = protocol
                        break
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                scope['user'] = AnonymousUser()
        else:
            scope['user'] = AnonymousUser()

        # 保存接受的 subprotocol 供 consumer 使用
        scope['accepted_subprotocol'] = accepted_subprotocol

        return await self.app(scope, receive, send)
