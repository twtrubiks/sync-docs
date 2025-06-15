import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from urllib.parse import parse_qs

User = get_user_model()

@database_sync_to_async
def get_user(user_id):
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return AnonymousUser()

class JWTAuthMiddleware:
    """
    Custom middleware for Django Channels to authenticate users via JWT in query string.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        token = query_params.get("token", [None])[0]

        if token:
            try:
                # Decode the token to get user_id
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = payload.get('user_id')
                scope['user'] = await get_user(user_id)
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                scope['user'] = AnonymousUser()
        else:
            scope['user'] = AnonymousUser()

        return await self.app(scope, receive, send)
