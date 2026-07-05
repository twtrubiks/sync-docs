"""
認證API模組
處理用戶註冊、登錄、登出和用戶信息獲取
"""

import logging
from ninja_extra import ControllerBase, api_controller, http_post, http_get
from ninja_extra.permissions import AllowAny
from django.contrib.auth.models import User
from ninja_jwt.controller import NinjaJWTDefaultController
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.tokens import RefreshToken
from ninja_jwt.exceptions import TokenError
from ninja_jwt.schema_control import SchemaControl
from ninja_jwt.settings import api_settings
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from ninja.errors import HttpError
from .schemas import UserSchema, RegisterSchema, LogoutSchema
from .throttling import AuthRateThrottle

# 獲取日誌記錄器
logger = logging.getLogger('docs_app')

# ninja_jwt 的 token schema（與 NinjaJWTDefaultController 使用相同來源）
token_schema = SchemaControl(api_settings)

# 認證端點限流（IP 滑動窗口，防暴力破解）
LOGIN_RATE_LIMIT = 10       # 次
LOGIN_RATE_WINDOW = 300     # 秒（5 分鐘）
REGISTER_RATE_LIMIT = 10    # 次
REGISTER_RATE_WINDOW = 3600  # 秒（1 小時）


@api_controller("/token", permissions=[AllowAny], tags=["token"], auth=None)
class TokenController(NinjaJWTDefaultController):
    """
    Token 控制器（帶登入限流）

    取代直接註冊 NinjaJWTDefaultController：
    1. /token/pair 加上 IP 限流防暴力破解（throttle 在 body 解析前執行，
       故失敗的登入嘗試也會被計數）
    2. 避免先前 NinjaJWTDefaultController 與繼承它的 AuthController
       重複註冊出兩組登入端點（/token/pair 與 /auth/pair），限流留下後門
    """

    auto_import = False

    @http_post(
        "/pair",
        response=token_schema.obtain_pair_schema.get_response_schema(),
        url_name="token_obtain_pair",
        operation_id="token_obtain_pair",
        throttle=[AuthRateThrottle('login', LOGIN_RATE_LIMIT, LOGIN_RATE_WINDOW)],
    )
    def obtain_token(self, user_token: token_schema.obtain_pair_schema):
        return super().obtain_token(user_token)


@api_controller("/auth", tags=["auth"], permissions=[])
class AuthController(ControllerBase):
    """
    認證控制器

    處理用戶認證相關的API端點，包括：
    - 用戶註冊
    - 用戶登出
    - 獲取當前用戶信息

    Token 相關端點（登入/刷新/驗證）由 TokenController 提供
    """

    @http_post(
        "/register",
        response={201: UserSchema},
        auth=None,
        throttle=[AuthRateThrottle('register', REGISTER_RATE_LIMIT, REGISTER_RATE_WINDOW)],
    )
    def register(self, payload: RegisterSchema):
        """
        註冊新用戶

        Args:
            payload: 包含用戶名、密碼和可選 email 的註冊數據

        Returns:
            UserSchema: 新創建的用戶信息

        Raises:
            ValidationError: 當用戶名已存在或密碼不符合要求時
        """
        try:
            logger.info(f"嘗試註冊新用戶: {payload.username}")

            # 檢查用戶名是否已存在
            if User.objects.filter(username=payload.username).exists():
                logger.warning(f"註冊失敗，用戶名已存在: {payload.username}")
                raise ValidationError("用戶名已存在")

            # 驗證密碼強度
            validate_password(payload.password)

            # 創建新用戶
            user = User.objects.create_user(
                username=payload.username,
                password=payload.password,
                email=payload.email or ""
            )

            logger.info(f"成功註冊新用戶: {user.username}")
            return 201, user

        except ValidationError as e:
            messages = e.messages if hasattr(e, 'messages') else [str(e)]
            error_msg = "; ".join(messages)
            logger.warning(f"用戶註冊驗證失敗: {error_msg}")
            raise HttpError(400, error_msg)

    @http_post("/logout", auth=None)
    def logout(self, payload: LogoutSchema):
        """
        用戶登出：將 refresh token 加入黑名單，使其立即失效

        不要求 access token 認證——登出當下 access token 可能已過期，
        而持有 refresh token 本身即足以證明身分（撤銷的也只是該 token）。

        Args:
            payload: 包含 refresh token 的請求數據

        Returns:
            dict: 包含成功標誌的響應
        """
        try:
            token = RefreshToken(payload.refresh)
            token.blacklist()
            logger.info(f"用戶 {token.payload.get('user_id', '?')} 登出，refresh token 已加入黑名單")
        except TokenError:
            # token 無效、過期或已在黑名單：登出視為冪等操作，不回報錯誤
            logger.info("登出時收到無效或已列入黑名單的 refresh token")
        return {"success": True}

    @http_get("/me", response=UserSchema, auth=JWTAuth())
    def me(self, request):
        """
        獲取當前用戶信息

        Args:
            request: HTTP請求對象，包含認證用戶信息

        Returns:
            UserSchema: 當前用戶的信息
        """
        user = request.user
        logger.debug(f"用戶 {user.username} 獲取個人信息")
        return user
