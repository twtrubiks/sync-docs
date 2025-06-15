from ninja_extra import api_controller, http_post, route, http_get
from ninja import Schema
from django.contrib.auth.models import User
from ninja_jwt.controller import NinjaJWTDefaultController
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.tokens import RefreshToken

class UserSchema(Schema):
    username: str
    email: str = None

class RegisterSchema(Schema):
    username: str
    password: str

@api_controller("/auth", tags=["auth"], permissions=[])
class AuthController(NinjaJWTDefaultController):
    @http_post("/register", response=UserSchema, auth=None)
    def register(self, payload: RegisterSchema):
        """
        Register a new user.
        """
        user = User.objects.create_user(username=payload.username, password=payload.password)
        return user

    @http_post("/logout", auth=JWTAuth())
    def logout(self, request):
        """
        Logout a user.
        """
        # JWT is stateless, so logout is handled on the client side by deleting the token.
        # Optionally, you can implement token blacklisting here.
        return {"success": True}

    @http_get("/me", response=UserSchema, auth=JWTAuth())
    def me(self, request):
        """
        Get current user info.
        """
        return request.user
