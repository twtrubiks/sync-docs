"""
認證API模組
處理用戶註冊、登錄、登出和用戶信息獲取
"""

import logging
from ninja_extra import api_controller, http_post, route, http_get
from ninja import Schema
from django.contrib.auth.models import User
from ninja_jwt.controller import NinjaJWTDefaultController
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.tokens import RefreshToken
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password

# 獲取日誌記錄器
logger = logging.getLogger('docs_app')


class UserSchema(Schema):
    """用戶信息響應模式"""
    username: str
    email: str = None


class RegisterSchema(Schema):
    """用戶註冊請求模式"""
    username: str
    password: str

@api_controller("/auth", tags=["auth"], permissions=[])
class AuthController(NinjaJWTDefaultController):
    """
    認證控制器

    處理用戶認證相關的API端點，包括：
    - 用戶註冊
    - 用戶登出
    - 獲取當前用戶信息

    繼承自NinjaJWTDefaultController，自動提供JWT登錄和刷新token功能
    """

    @http_post("/register", response=UserSchema, auth=None)
    def register(self, payload: RegisterSchema):
        """
        註冊新用戶

        Args:
            payload: 包含用戶名和密碼的註冊數據

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
                password=payload.password
            )

            logger.info(f"成功註冊新用戶: {user.username}")
            return user

        except ValidationError as e:
            logger.warning(f"用戶註冊驗證失敗: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"用戶註冊時發生錯誤: {str(e)}")
            raise

    @http_post("/logout", auth=JWTAuth())
    def logout(self, request):
        """
        用戶登出

        Args:
            request: HTTP請求對象，包含認證用戶信息

        Returns:
            dict: 包含成功標誌的響應

        Note:
            JWT是無狀態的，所以登出主要在客戶端處理（刪除token）
            可選地，這裡可以實現token黑名單功能
        """
        user = request.user
        logger.info(f"用戶 {user.username} 登出")

        # JWT是無狀態的，登出主要在客戶端處理
        # 可選：在這裡實現token黑名單功能
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
