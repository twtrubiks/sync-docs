"""
WebSocket消費者模組
處理實時協作功能的WebSocket連接和消息傳遞
"""

import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.conf import settings
from pydantic import ValidationError as PydanticValidationError
from .models import Document, DocumentCollaborator, PermissionLevel
from .schemas import WebSocketMessageSchema
from .auth_middleware import AuthErrorType
from .connection_manager import connection_manager
from .rate_limiter import rate_limiter
from django.db.models import Q

# 獲取日誌記錄器
logger = logging.getLogger('docs_app')

# WebSocket 安全配置
MAX_MESSAGE_SIZE = getattr(settings, 'WEBSOCKET_MAX_MESSAGE_SIZE', 256 * 1024)  # 256KB
MAX_OPS_COUNT = getattr(settings, 'WEBSOCKET_MAX_OPS_COUNT', 1000)


# WebSocket Close Codes (Application-specific: 4000-4999)
class WSCloseCodes:
    """WebSocket 關閉代碼常量"""
    AUTH_FAILED = 4001           # 認證失敗（無效 token）
    TOKEN_EXPIRED = 4002         # Token 已過期
    PERMISSION_DENIED = 4003     # 權限不足
    DOCUMENT_NOT_FOUND = 4004    # 文檔不存在
    TOO_MANY_CONNECTIONS = 4005  # 連接數超限
    INVALID_MESSAGE = 4006       # 無效消息格式
    MESSAGE_TOO_LARGE = 4007     # 消息過大
    RATE_LIMITED = 4008          # 頻率限制
    READ_ONLY_VIOLATION = 4009   # 只讀用戶嘗試寫入


# 錯誤類型到關閉代碼的映射
AUTH_ERROR_TO_CLOSE_CODE = {
    AuthErrorType.NO_TOKEN: WSCloseCodes.AUTH_FAILED,
    AuthErrorType.TOKEN_EXPIRED: WSCloseCodes.TOKEN_EXPIRED,
    AuthErrorType.INVALID_TOKEN: WSCloseCodes.AUTH_FAILED,
    AuthErrorType.USER_NOT_FOUND: WSCloseCodes.AUTH_FAILED,
}

# 錯誤類型到錯誤消息的映射
AUTH_ERROR_MESSAGES = {
    AuthErrorType.NO_TOKEN: 'No authentication token provided',
    AuthErrorType.TOKEN_EXPIRED: 'Authentication token has expired',
    AuthErrorType.INVALID_TOKEN: 'Invalid authentication token',
    AuthErrorType.USER_NOT_FOUND: 'User not found',
}


# 權限錯誤類型
class PermissionErrorType:
    """權限錯誤類型常量"""
    NOT_AUTHENTICATED = 'NOT_AUTHENTICATED'
    DOCUMENT_NOT_FOUND = 'DOCUMENT_NOT_FOUND'
    PERMISSION_DENIED = 'PERMISSION_DENIED'
    READ_ONLY = 'READ_ONLY'  # 只讀權限

class DocConsumer(AsyncWebsocketConsumer):
    """
    文檔WebSocket消費者

    處理文檔的實時協作功能，包括：
    - 用戶連接和權限驗證
    - 實時編輯內容同步
    - 文檔保存事件廣播
    - 權限區分（只讀用戶不能發送編輯）
    """

    @database_sync_to_async
    def check_permission_detailed(self, user, document_id):
        """
        檢查用戶是否有權限訪問指定文檔，返回詳細結果

        Args:
            user: 要檢查的用戶對象
            document_id: 文檔ID

        Returns:
            dict: {
                'allowed': bool,
                'can_write': bool,  # 是否有寫入權限
                'error_type': str or None,
                'message': str or None
            }
        """
        if not user or not user.is_authenticated:
            logger.warning(f"未認證用戶嘗試訪問文檔 {document_id}")
            return {
                'allowed': False,
                'can_write': False,
                'error_type': PermissionErrorType.NOT_AUTHENTICATED,
                'message': 'User not authenticated'
            }

        try:
            # 檢查用戶是否是文檔擁有者或協作者
            document = Document.objects.filter(id=document_id).first()
            if not document:
                logger.warning(f"文檔 {document_id} 不存在")
                return {
                    'allowed': False,
                    'can_write': False,
                    'error_type': PermissionErrorType.DOCUMENT_NOT_FOUND,
                    'message': 'Document does not exist'
                }

            # 檢查是否是擁有者
            if document.owner == user:
                logger.info(f"用戶 {user.username} 是文檔 {document_id} 的擁有者")
                return {
                    'allowed': True,
                    'can_write': True,
                    'error_type': None,
                    'message': None
                }

            # 檢查是否是協作者並獲取權限級別
            collab = DocumentCollaborator.objects.filter(
                document=document,
                user=user
            ).first()

            if collab:
                can_write = (collab.permission == PermissionLevel.WRITE)
                logger.info(
                    f"用戶 {user.username} 是文檔 {document_id} 的協作者 "
                    f"(權限: {collab.permission})"
                )
                return {
                    'allowed': True,
                    'can_write': can_write,
                    'error_type': None,
                    'message': None
                }

            logger.warning(f"用戶 {user.username} 無權限訪問文檔 {document_id}")
            return {
                'allowed': False,
                'can_write': False,
                'error_type': PermissionErrorType.PERMISSION_DENIED,
                'message': 'You do not have permission to access this document'
            }
        except Exception as e:
            logger.error(f"檢查用戶 {user.username} 對文檔 {document_id} 的權限時發生錯誤: {str(e)}")
            return {
                'allowed': False,
                'can_write': False,
                'error_type': PermissionErrorType.PERMISSION_DENIED,
                'message': 'Permission check failed'
            }

    async def connect(self):
        """
        處理WebSocket連接請求
        驗證用戶權限並將用戶加入文檔的頻道組

        連接驗證流程：
        1. 檢查認證錯誤（從 middleware 獲取）
        2. 檢查文檔訪問權限
        3. 檢查連接數量限制
        4. 加入房間組並接受連接
        5. 發送連接成功消息（包含權限信息）
        """
        self.document_id = self.scope['url_route']['kwargs']['document_id']
        self.room_group_name = f'doc_{self.document_id}'
        self.user = self.scope.get('user')
        auth_error = self.scope.get('auth_error')

        # 初始化 can_write 標誌
        self.can_write = False

        logger.info(f"用戶 {self.user.username if self.user else 'Anonymous'} 嘗試連接到文檔 {self.document_id}")

        # Step 1: 檢查認證錯誤
        if auth_error:
            error_message = AUTH_ERROR_MESSAGES.get(auth_error, 'Authentication failed')
            close_code = AUTH_ERROR_TO_CLOSE_CODE.get(auth_error, WSCloseCodes.AUTH_FAILED)
            await self._reject_connection(auth_error, error_message, close_code)
            return

        # Step 2: 檢查文檔訪問權限
        permission_result = await self.check_permission_detailed(self.user, self.document_id)
        if not permission_result['allowed']:
            error_type = permission_result['error_type']
            error_message = permission_result['message']

            # 映射權限錯誤到關閉代碼
            if error_type == PermissionErrorType.DOCUMENT_NOT_FOUND:
                close_code = WSCloseCodes.DOCUMENT_NOT_FOUND
            elif error_type == PermissionErrorType.NOT_AUTHENTICATED:
                close_code = WSCloseCodes.AUTH_FAILED
            else:
                close_code = WSCloseCodes.PERMISSION_DENIED

            await self._reject_connection(error_type, error_message, close_code)
            return

        # 保存寫入權限狀態
        self.can_write = permission_result['can_write']

        # Step 3: 檢查連接數量限制
        if not await connection_manager.add_connection(
            self.user.id, self.channel_name
        ):
            await self._reject_connection(
                'TOO_MANY_CONNECTIONS',
                f'Maximum connections per user exceeded (limit: {connection_manager.max_connections})',
                WSCloseCodes.TOO_MANY_CONNECTIONS
            )
            return

        # Step 4: 驗證通過，加入房間組
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        # 獲取接受的 subprotocol（來自 JWTAuthMiddleware）
        accepted_subprotocol = self.scope.get('accepted_subprotocol')
        if accepted_subprotocol:
            await self.accept(subprotocol=accepted_subprotocol)
        else:
            await self.accept()

        # Step 5: 發送連接成功消息（包含權限信息）
        await self.send(text_data=json.dumps({
            'type': 'connection_success',
            'can_write': self.can_write,
            'message': 'Connected successfully'
        }))

        logger.info(f"用戶 {self.user.username} 成功連接到文檔 {self.document_id} (can_write: {self.can_write})")

    async def _reject_connection(self, error_code: str, error_message: str, close_code: int):
        """
        拒絕連接並發送錯誤原因

        注意：必須先 accept() 才能 send()，然後再 close()

        Args:
            error_code: 錯誤代碼
            error_message: 人類可讀的錯誤描述
            close_code: WebSocket 關閉代碼 (4000-4999)
        """
        username = self.user.username if self.user and hasattr(self.user, 'username') else 'Anonymous'
        logger.warning(f"拒絕用戶 {username} 連接到文檔 {self.document_id}: {error_code}")

        # 先接受連接以便發送錯誤消息
        await self.accept()

        # 發送錯誤消息
        try:
            await self.send(text_data=json.dumps({
                'type': 'connection_error',
                'error_code': error_code,
                'message': error_message
            }))
        except Exception as e:
            logger.error(f"發送連接錯誤消息失敗: {str(e)}")

        # 關閉連接
        await self.close(code=close_code)

    async def disconnect(self, close_code):
        """
        處理WebSocket斷開連接
        將用戶從文檔的頻道組中移除，並清理連接記錄

        Args:
            close_code: 連接關閉代碼
        """
        logger.info(f"用戶 {self.user.username if hasattr(self, 'user') and self.user else 'Unknown'} 斷開與文檔 {getattr(self, 'document_id', 'Unknown')} 的連接")

        # 移除連接記錄
        if hasattr(self, 'user') and self.user and self.user.is_authenticated:
            await connection_manager.remove_connection(
                self.user.id, self.channel_name
            )

        # 離開房間組
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        """
        接收來自WebSocket的消息
        處理實時編輯的增量更新並廣播給其他用戶

        驗證流程：
        0. 檢查寫入權限（只讀用戶不能發送編輯）
        1. 速率限制檢查
        2. 檢查消息大小限制
        3. JSON 解析
        4. Pydantic Schema 驗證
        5. 操作數量限制檢查
        6. 廣播有效的 delta

        Args:
            text_data: 接收到的JSON格式文本數據
        """
        username = getattr(self.user, 'username', 'Unknown')

        # Step 0: 檢查寫入權限
        if not self.can_write:
            logger.warning(f"只讀用戶 {username} 嘗試發送 delta 到文檔 {self.document_id}")
            await self._send_error(
                "READ_ONLY",
                "You have read-only access to this document and cannot make edits"
            )
            return

        # Step 1: 速率限制檢查（在所有其他驗證之前）
        allowed, rate_info = await rate_limiter.is_allowed(
            self.user.id, self.document_id
        )
        if not allowed:
            await self._send_error(
                "RATE_LIMITED",
                f"Too many messages. Please wait {rate_info['retry_after']:.1f} seconds.",
                extra={'retry_after': rate_info['retry_after']}
            )
            return

        # Step 2: 檢查消息大小
        message_size = len(text_data.encode('utf-8'))
        if message_size > MAX_MESSAGE_SIZE:
            logger.warning(
                f"用戶 {username} 發送的消息超過大小限制: "
                f"{message_size} bytes > {MAX_MESSAGE_SIZE} bytes"
            )
            await self._send_error(
                "MESSAGE_TOO_LARGE",
                f"Message size ({message_size} bytes) exceeds maximum allowed ({MAX_MESSAGE_SIZE} bytes)"
            )
            return

        # Step 3: JSON 解析
        try:
            text_data_json = json.loads(text_data)
        except json.JSONDecodeError as e:
            logger.error(f"用戶 {username} 發送了無效的JSON數據: {str(e)}")
            await self._send_error("INVALID_JSON", "Invalid JSON format")
            return

        # Step 4: Pydantic Schema 驗證
        try:
            validated_message = WebSocketMessageSchema(**text_data_json)
            delta = validated_message.delta.model_dump()
        except PydanticValidationError as e:
            error_messages = "; ".join([err['msg'] for err in e.errors()])
            logger.warning(
                f"用戶 {username} 發送了無效的 Delta 格式: {error_messages}"
            )
            await self._send_error("INVALID_DELTA_FORMAT", f"Invalid delta format: {error_messages}")
            return

        # Step 5: 檢查操作數量限制
        ops_count = len(delta.get('ops', []))
        if ops_count > MAX_OPS_COUNT:
            logger.warning(
                f"用戶 {username} 發送的操作數量超過限制: "
                f"{ops_count} > {MAX_OPS_COUNT}"
            )
            await self._send_error(
                "TOO_MANY_OPERATIONS",
                f"Too many operations ({ops_count}). Maximum allowed: {MAX_OPS_COUNT}"
            )
            return

        # Step 6: 驗證通過，廣播 delta
        logger.debug(f"用戶 {username} 在文檔 {self.document_id} 中發送增量更新")

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'doc_update',
                'delta': delta,
                'sender_channel': self.channel_name
            }
        )

    async def _send_error(self, error_code: str, error_message: str, extra: dict = None):
        """
        向客戶端發送錯誤消息

        Args:
            error_code: 錯誤代碼 (e.g., "INVALID_JSON", "MESSAGE_TOO_LARGE", "RATE_LIMITED", "READ_ONLY")
            error_message: 人類可讀的錯誤描述
            extra: 可選的額外數據（如 retry_after）
        """
        try:
            response = {
                'type': 'error',
                'error_code': error_code,
                'message': error_message
            }
            if extra:
                response.update(extra)
            await self.send(text_data=json.dumps(response))
        except Exception as e:
            logger.error(f"發送錯誤消息失敗: {str(e)}")

    async def doc_update(self, event):
        """
        處理來自房間組的文檔更新消息
        將增量更新發送給WebSocket客戶端（除了原始發送者）

        Args:
            event: 包含增量數據和發送者頻道的事件字典
        """
        delta = event['delta']
        sender_channel = event.get('sender_channel')

        # 發送增量更新到WebSocket，但不發送回原始發送者
        if self.channel_name != sender_channel:
            try:
                await self.send(text_data=json.dumps({
                    'type': 'doc_update',
                    'delta': delta
                }))
                logger.debug(f"向用戶 {self.user.username} 發送文檔更新")
            except Exception as e:
                logger.error(f"向用戶 {self.user.username} 發送文檔更新失敗: {str(e)}")

    async def doc_saved(self, event):
        """
        處理來自房間組的文檔保存消息（由API在保存時發送）
        向組中的所有用戶發送新的時間戳

        Args:
            event: 包含更新時間的事件字典
        """
        updated_at = event['updated_at']

        try:
            # 向組中的所有人發送新的時間戳
            await self.send(text_data=json.dumps({
                'type': 'doc_saved',
                'updated_at': updated_at
            }))
            logger.debug(f"向用戶 {self.user.username} 發送文檔保存通知")
        except Exception as e:
            logger.error(f"向用戶 {self.user.username} 發送文檔保存通知失敗: {str(e)}")
