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
from .models import Document
from .schemas import WebSocketMessageSchema
from django.db.models import Q

# 獲取日誌記錄器
logger = logging.getLogger('docs_app')

# WebSocket 安全配置
MAX_MESSAGE_SIZE = getattr(settings, 'WEBSOCKET_MAX_MESSAGE_SIZE', 256 * 1024)  # 256KB
MAX_OPS_COUNT = getattr(settings, 'WEBSOCKET_MAX_OPS_COUNT', 1000)

class DocConsumer(AsyncWebsocketConsumer):
    """
    文檔WebSocket消費者

    處理文檔的實時協作功能，包括：
    - 用戶連接和權限驗證
    - 實時編輯內容同步
    - 文檔保存事件廣播
    """

    @database_sync_to_async
    def has_permission(self, user, document_id):
        """
        檢查用戶是否有權限訪問指定文檔

        Args:
            user: 要檢查的用戶對象
            document_id: 文檔ID

        Returns:
            bool: 如果用戶有權限則返回True，否則返回False
        """
        if not user.is_authenticated:
            logger.warning(f"未認證用戶嘗試訪問文檔 {document_id}")
            return False

        try:
            # 檢查用戶是否是文檔擁有者或協作者
            document = Document.objects.filter(id=document_id).first()
            if not document:
                logger.warning(f"文檔 {document_id} 不存在")
                return False

            # 檢查是否是擁有者
            if document.owner == user:
                logger.info(f"用戶 {user.username} 是文檔 {document_id} 的擁有者")
                return True

            # 檢查是否是協作者
            if document.shared_with.filter(id=user.id).exists():
                logger.info(f"用戶 {user.username} 是文檔 {document_id} 的協作者")
                return True

            logger.warning(f"用戶 {user.username} 無權限訪問文檔 {document_id}")
            return False
        except Exception as e:
            logger.error(f"檢查用戶 {user.username} 對文檔 {document_id} 的權限時發生錯誤: {str(e)}")
            return False

    async def connect(self):
        """
        處理WebSocket連接請求
        驗證用戶權限並將用戶加入文檔的頻道組
        """
        self.document_id = self.scope['url_route']['kwargs']['document_id']
        self.room_group_name = f'doc_{self.document_id}'
        self.user = self.scope.get('user')

        logger.info(f"用戶 {self.user.username if self.user else 'Anonymous'} 嘗試連接到文檔 {self.document_id}")

        # 檢查權限
        if self.user and await self.has_permission(self.user, self.document_id):
            # 加入房間組
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            logger.info(f"用戶 {self.user.username} 成功連接到文檔 {self.document_id}")
        else:
            # 拒絕連接
            logger.warning(f"拒絕用戶 {self.user.username if self.user else 'Anonymous'} 連接到文檔 {self.document_id}")
            await self.close()

    async def disconnect(self, close_code):
        """
        處理WebSocket斷開連接
        將用戶從文檔的頻道組中移除

        Args:
            close_code: 連接關閉代碼
        """
        logger.info(f"用戶 {self.user.username if hasattr(self, 'user') and self.user else 'Unknown'} 斷開與文檔 {getattr(self, 'document_id', 'Unknown')} 的連接")

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
        1. 檢查消息大小限制
        2. JSON 解析
        3. Pydantic Schema 驗證
        4. 操作數量限制檢查
        5. 廣播有效的 delta

        Args:
            text_data: 接收到的JSON格式文本數據
        """
        username = getattr(self.user, 'username', 'Unknown')

        # Step 1: 檢查消息大小
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

        # Step 2: JSON 解析
        try:
            text_data_json = json.loads(text_data)
        except json.JSONDecodeError as e:
            logger.error(f"用戶 {username} 發送了無效的JSON數據: {str(e)}")
            await self._send_error("INVALID_JSON", "Invalid JSON format")
            return

        # Step 3: Pydantic Schema 驗證
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

        # Step 4: 檢查操作數量限制
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

        # Step 5: 驗證通過，廣播 delta
        logger.debug(f"用戶 {username} 在文檔 {self.document_id} 中發送增量更新")

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'doc_update',
                'delta': delta,
                'sender_channel': self.channel_name
            }
        )

    async def _send_error(self, error_code: str, error_message: str):
        """
        向客戶端發送錯誤消息

        Args:
            error_code: 錯誤代碼 (e.g., "INVALID_JSON", "MESSAGE_TOO_LARGE")
            error_message: 人類可讀的錯誤描述
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error_code': error_code,
                'message': error_message
            }))
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
