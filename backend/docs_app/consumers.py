"""
WebSocket消費者模組
處理實時協作功能的WebSocket連接和消息傳遞
"""

import asyncio
import hashlib
import json
import logging
import time

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from pydantic import ValidationError as PydanticValidationError
from .models import Document, DocumentCollaborator, PermissionLevel
from .schemas import WebSocketMessageSchema, CursorMoveMessage, AIStreamMessage, AIAskStreamMessage
from .auth_middleware import AuthErrorType
from .connection_manager import connection_manager
from .rate_limiter import rate_limiter
from .ai_service import ai_service
from .ai_rate_limiter import ai_rate_limiter
from .redis_pool import get_async_redis

# 獲取日誌記錄器
logger = logging.getLogger('docs_app')

# WebSocket 安全配置
MAX_MESSAGE_SIZE = getattr(settings, 'WEBSOCKET_MAX_MESSAGE_SIZE', 256 * 1024)  # 256KB
MAX_OPS_COUNT = getattr(settings, 'WEBSOCKET_MAX_OPS_COUNT', 1000)

# 心跳間隔（秒）- 用於刷新連接 TTL
HEARTBEAT_INTERVAL = getattr(settings, 'WEBSOCKET_HEARTBEAT_INTERVAL', 120)  # 2 分鐘

# AI 串流速率限制（與 HTTP /ai/process 共用同一 Redis 額度鍵 ai:{user_id}，每次串流算一次）
AI_STREAM_RATE_LIMIT_REQUESTS = 10
AI_STREAM_RATE_LIMIT_WINDOW = 60

# Lua 腳本：原子性添加用戶到在線列表
ADD_USER_SCRIPT = """
local key = KEYS[1]
local user_id = ARGV[1]
local user_data = ARGV[2]
local ttl = tonumber(ARGV[3])

-- 舊格式殘留（TTL 掛在整個 key 上）：直接刪除重建，
-- 避免舊 key TTL 到期時把新加入的用戶一起帶走
if redis.call('TTL', key) > 0 then
    redis.call('DEL', key)
end

-- 添加/更新用戶；TTL 掛在各自的 field 上（HEXPIRE，Redis >= 7.4），
-- 避免異常斷線（server crash）殘留的 ghost user 被其他人的心跳續命而永不過期
redis.call('HSET', key, user_id, user_data)
redis.call('HEXPIRE', key, ttl, 'FIELDS', 1, user_id)

return 1
"""

# Lua 腳本：原子性移除用戶
REMOVE_USER_SCRIPT = """
local key = KEYS[1]
local user_id = ARGV[1]

redis.call('HDEL', key, user_id)
return 1
"""


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

        # Step 5: 發送連接成功消息（包含權限信息和用戶顏色）
        user_color = self.get_user_color(self.user.id)
        await self.send(text_data=json.dumps({
            'type': 'connection_success',
            'can_write': self.can_write,
            'user_id': str(self.user.id),
            'color': user_color,
            'message': 'Connected successfully'
        }))

        # Step 6: 加入 Presence 列表
        await self.add_user_to_presence()

        # Step 7: 通知其他用戶有人加入
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_join',
                'user_id': str(self.user.id),
                'username': self.user.username,
                'color': user_color
            }
        )

        # Step 8: 發送當前在線用戶列表給新加入者
        await self.send_presence_sync()

        # Step 9: 啟動心跳任務，定期刷新連接 TTL
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

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

        # 取消心跳任務
        if hasattr(self, '_heartbeat_task'):
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # 取消進行中的 AI 串流任務，避免斷線後仍嘗試送資料
        ai_stream_task = getattr(self, '_ai_stream_task', None)
        if ai_stream_task is not None and not ai_stream_task.done():
            ai_stream_task.cancel()
            try:
                await ai_stream_task
            except asyncio.CancelledError:
                pass

        # 移除連接記錄
        if hasattr(self, 'user') and self.user and self.user.is_authenticated:
            await connection_manager.remove_connection(
                self.user.id, self.channel_name
            )

            # 從 Presence 列表移除
            await self.remove_user_from_presence()

            # 通知其他用戶有人離開
            if hasattr(self, 'room_group_name'):
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_leave',
                        'user_id': str(self.user.id)
                    }
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
        0. 檢查消息大小限制（在解析前，避免大 payload 被完整解析進記憶體）
        1. 解析 JSON 確定消息類型
        1a. cursor_move 消息：不計入速率限制，單獨處理
        2. 其他消息類型：檢查寫入權限
        3. 速率限制檢查
        4. Pydantic Schema 驗證
        5. 操作數量限制檢查
        6. 廣播有效的 delta

        Args:
            text_data: 接收到的JSON格式文本數據
        """
        username = getattr(self.user, 'username', 'Unknown')

        # Step 0: 檢查消息大小（在 json.loads 之前，避免大 payload 被完整解析進記憶體；
        # 涵蓋 cursor_move / ai_stream / ai_ask_stream 等提前 return 的分支）
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

        # Step 1: 解析 JSON 確定消息類型
        try:
            text_data_json = json.loads(text_data)
        except json.JSONDecodeError as e:
            logger.error(f"用戶 {username} 發送了無效的JSON數據: {str(e)}")
            await self._send_error("INVALID_JSON", "Invalid JSON format")
            return

        msg_type = text_data_json.get('type')

        # cursor_move 消息：不計入速率限制（由前端 throttle 控制）
        if msg_type == 'cursor_move':
            await self.handle_cursor_move(text_data_json)
            return

        # AI 串流消息：摘要/潤稿/文件問答逐字回傳（只回發送者本人，不經 delta 驗證；
        # 與 HTTP /ai/process 一致，僅需認證、不要求寫入權限）
        if msg_type == 'ai_stream':
            await self.handle_ai_stream(text_data_json)
            return
        if msg_type == 'ai_ask_stream':
            await self.handle_ai_ask_stream(text_data_json)
            return
        if msg_type == 'ai_stream_cancel':
            await self.handle_ai_stream_cancel()
            return

        # Step 2: 檢查寫入權限（非 cursor_move 消息）
        if not self.can_write:
            logger.warning(f"只讀用戶 {username} 嘗試發送 delta 到文檔 {self.document_id}")
            await self._send_error(
                "READ_ONLY",
                "You have read-only access to this document and cannot make edits"
            )
            return

        # Step 3: 速率限制檢查
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

        # Step 4: Pydantic Schema 驗證（JSON 已在前面解析過）
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

    # ========== AI 串流（摘要/潤稿，逐字回傳給發送者本人） ==========

    async def _send_ai_stream_error(self, message: str):
        """向發送者回傳 AI 串流錯誤（獨立於一般 error 通道，方便前端對話框重置狀態）"""
        try:
            await self.send(text_data=json.dumps({
                'type': 'ai_stream_error',
                'message': message
            }))
        except Exception as e:
            logger.error(f"發送 AI 串流錯誤失敗: {str(e)}")

    async def _reject_if_ai_stream_busy(self) -> bool:
        """同一連線同時間只允許一個串流；若已有進行中的串流則回報錯誤並回傳 True。"""
        existing = getattr(self, '_ai_stream_task', None)
        if existing is not None and not existing.done():
            await self._send_ai_stream_error('已有 AI 串流進行中，請稍候')
            return True
        return False

    async def _reject_if_ai_rate_limited(self) -> bool:
        """檢查 AI 串流速率限制（與 HTTP /ai/process 共用額度）；超限則回報錯誤並回傳 True。

        同步限流器以 sync_to_async 包裝，避免阻塞事件迴圈。
        """
        allowed = await sync_to_async(ai_rate_limiter.is_allowed)(
            f"ai:{self.user.id}",
            AI_STREAM_RATE_LIMIT_REQUESTS,
            AI_STREAM_RATE_LIMIT_WINDOW,
        )
        if not allowed:
            logger.warning(f"AI 串流速率限制: user={self.user.id}")
            await self._send_ai_stream_error('請求過於頻繁，請稍後再試')
            return True
        return False

    async def handle_ai_stream(self, data):
        """
        處理 AI 摘要/潤稿串流請求：驗證 → 速率限制 → 啟動可取消的背景串流任務。

        chunk 只回傳給發送者本人（self.send），不經 group_send，
        複用既有連線的認證；速率限制與 HTTP /ai/process 共用同一額度。
        """
        username = getattr(self.user, 'username', 'Unknown')

        if await self._reject_if_ai_stream_busy():
            return

        # 驗證請求格式（action + text）
        try:
            message = AIStreamMessage(**data)
        except PydanticValidationError as e:
            error_messages = "; ".join([err['msg'] for err in e.errors()])
            logger.warning(f"用戶 {username} 發送了無效的 AI 串流請求: {error_messages}")
            await self._send_ai_stream_error(f"Invalid AI stream request: {error_messages}")
            return

        if await self._reject_if_ai_rate_limited():
            return

        # 啟動可取消的背景串流任務
        self._ai_stream_task = asyncio.create_task(
            self._run_ai_stream(
                message.action,
                ai_service.process_stream(message.action, message.text),
            )
        )

    async def handle_ai_ask_stream(self, data):
        """
        處理 AI 文件問答串流請求：驗證 → 速率限制 → 啟動可取消的背景串流任務。

        與 handle_ai_stream 共用串流封裝、忙碌檢查與額度，差別在輸入為
        question + document_text，底層走 deps + 工具的文件問答 agent。
        """
        username = getattr(self.user, 'username', 'Unknown')

        if await self._reject_if_ai_stream_busy():
            return

        # 驗證請求格式（question + document_text）
        try:
            message = AIAskStreamMessage(**data)
        except PydanticValidationError as e:
            error_messages = "; ".join([err['msg'] for err in e.errors()])
            logger.warning(f"用戶 {username} 發送了無效的 AI 問答串流請求: {error_messages}")
            await self._send_ai_stream_error(f"Invalid AI ask stream request: {error_messages}")
            return

        if await self._reject_if_ai_rate_limited():
            return

        # 啟動可取消的背景串流任務
        self._ai_stream_task = asyncio.create_task(
            self._run_ai_stream(
                'ask',
                ai_service.ask_stream(message.question, message.document_text),
            )
        )

    async def _run_ai_stream(self, action: str, stream):
        """實際執行串流封裝：依序送出 start → chunk(s) → end；可被 cancel 中止（使用者取消或斷線）。

        action 僅作為 start/end 事件標籤；stream 為產生文字 delta 的 async iterator
        （摘要/潤稿來自 process_stream、文件問答來自 ask_stream）。
        """
        username = getattr(self.user, 'username', 'Unknown')
        try:
            await self.send(text_data=json.dumps({
                'type': 'ai_stream_start',
                'action': action
            }))
            async for chunk in stream:
                await self.send(text_data=json.dumps({
                    'type': 'ai_stream_chunk',
                    'chunk': chunk
                }))
            await self.send(text_data=json.dumps({
                'type': 'ai_stream_end',
                'action': action
            }))
            logger.info(f"AI 串流完成: user={self.user.id}, action={action}")
        except asyncio.CancelledError:
            # 使用者取消或連線中斷：停止生成、不再送資料
            logger.info(f"AI 串流被取消: user={username}, action={action}")
            raise
        except (ValueError, RuntimeError) as e:
            await self._send_ai_stream_error(str(e))
        except Exception as e:
            logger.error(f"AI 串流未預期錯誤: user={username}, error={e}")
            await self._send_ai_stream_error('AI 串流失敗')

    async def handle_ai_stream_cancel(self):
        """取消進行中的 AI 串流任務（前端按下停止）。"""
        task = getattr(self, '_ai_stream_task', None)
        if task is not None and not task.done():
            task.cancel()
            logger.debug(f"收到取消請求，已取消用戶 {self.user.id} 的 AI 串流")

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

    async def doc_restored(self, event):
        """
        處理來自房間組的文檔還原消息（由API在還原版本時發送）
        向組中的所有用戶發送還原後的完整內容，讓 client 重置編輯器

        Args:
            event: 包含還原後內容與還原者資訊的事件字典
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'doc_restored',
                'content': event['content'],
                'updated_at': event['updated_at'],
                'restored_by': event['restored_by'],
                'restored_by_username': event['restored_by_username'],
                'restored_to_version': event['restored_to_version'],
                'new_version_number': event['new_version_number']
            }))
            logger.debug(f"向用戶 {self.user.username} 發送文檔還原通知")
        except Exception as e:
            logger.error(f"向用戶 {self.user.username} 發送文檔還原通知失敗: {str(e)}")

    # ========== 游標與 Presence 功能 ==========

    async def handle_cursor_move(self, data):
        """處理游標位置更新"""
        # 檢查寫入權限（只讀用戶不可發送游標更新）
        if not self.can_write:
            logger.debug(f"Read-only user {self.user.id} attempted cursor_move, ignoring")
            return  # 靜默忽略，不發送錯誤

        # 使用 Schema 驗證消息格式
        try:
            cursor_msg = CursorMoveMessage(**data)
        except PydanticValidationError as e:
            logger.warning(f"Invalid cursor_move message from {self.user.id}: {e}")
            await self._send_error('INVALID_CURSOR_MESSAGE', str(e))
            return

        logger.debug(f"Cursor move from user {self.user.id}: index={cursor_msg.index}, length={cursor_msg.length}")

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'cursor_update',
                'user_id': str(self.user.id),
                'username': self.user.username,
                'color': self.get_user_color(self.user.id),
                'cursor': {
                    'index': cursor_msg.index,
                    'length': cursor_msg.length
                },
                'timestamp': time.time(),
                'sender_channel': self.channel_name
            }
        )

        # 刷新 presence TTL，確保活躍用戶不會從在線列表消失
        await self.refresh_presence_ttl()

    async def cursor_update(self, event):
        """廣播游標更新（排除發送者）"""
        if self.channel_name != event.get('sender_channel'):
            await self.send(text_data=json.dumps({
                'type': 'cursor_move',
                'user_id': event['user_id'],
                'username': event['username'],
                'color': event['color'],
                'cursor': event['cursor'],
                'timestamp': event['timestamp']
            }))

    async def user_join(self, event):
        """廣播用戶加入（排除發送者自己，避免重複通知）"""
        if str(self.user.id) != event['user_id']:
            await self.send(text_data=json.dumps({
                'type': 'user_join',
                'user_id': event['user_id'],
                'username': event['username'],
                'color': event['color']
            }))

    async def user_leave(self, event):
        """廣播用戶離開"""
        await self.send(text_data=json.dumps({
            'type': 'user_leave',
            'user_id': event['user_id']
        }))

    @staticmethod
    def get_user_color(user_id) -> str:
        """根據 user_id 生成穩定的顏色"""
        colors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4',
            '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F',
            '#BB8FCE', '#85C1E9', '#F8B500', '#00CED1'
        ]
        hash_val = int(hashlib.md5(str(user_id).encode()).hexdigest(), 16)
        return colors[hash_val % len(colors)]

    # ========== Redis Presence 存儲方法 ==========

    async def add_user_to_presence(self):
        """將用戶加入 Redis 在線列表（使用 Lua 腳本確保原子性）"""
        try:
            r = await get_async_redis()
            key = f"presence:{self.document_id}"
            user_data = json.dumps({
                'user_id': str(self.user.id),
                'username': self.user.username,
                'color': self.get_user_color(self.user.id),
                'channel_name': self.channel_name
            })
            # 使用 user_id 作為 field，TTL 掛在 field 上（5 分鐘），由各自的心跳續命
            await r.eval(ADD_USER_SCRIPT, 1, key, str(self.user.id), user_data, 300)
        except Exception as e:
            logger.error(f"Failed to add user {self.user.id} to presence: {e}")
            # fail-open: 不阻止連接

    async def remove_user_from_presence(self):
        """將用戶從 Redis 在線列表移除"""
        try:
            r = await get_async_redis()
            key = f"presence:{self.document_id}"
            await r.eval(REMOVE_USER_SCRIPT, 1, key, str(self.user.id))
        except Exception as e:
            logger.error(f"Failed to remove user {self.user.id} from presence: {e}")
            # fail-open: 記錄會在 TTL 後自動清除

    async def refresh_presence_ttl(self):
        """刷新用戶自己在 presence hash 中的 field TTL，確保活躍用戶不會消失"""
        try:
            r = await get_async_redis()
            key = f"presence:{self.document_id}"
            # 只刷新自己的 field（5 分鐘），不碰整個 key，
            # 避免替異常斷線殘留的 ghost user 續命
            await r.hexpire(key, 300, str(self.user.id))
        except Exception as e:
            logger.debug(f"Failed to refresh presence TTL: {e}")
            # fail-open: TTL 刷新失敗不影響功能

    async def get_online_users(self):
        """獲取當前在線用戶列表"""
        try:
            r = await get_async_redis()
            key = f"presence:{self.document_id}"
            users = await r.hgetall(key)
            return [json.loads(v) for v in users.values()]
        except Exception as e:
            logger.error(f"Failed to get online users for document {self.document_id}: {e}")
            return []  # fail-open: 返回空列表

    async def send_presence_sync(self):
        """發送當前在線用戶列表給新加入者"""
        users = await self.get_online_users()
        await self.send(text_data=json.dumps({
            'type': 'presence_sync',
            'users': users
        }))

    # ========== 心跳機制 ==========

    async def _heartbeat_loop(self):
        """
        心跳循環：定期刷新連接與 Presence TTL

        這確保活躍的連接不會因為 TTL 過期而被誤認為斷開，
        同時保持用戶在 Presence 在線列表中的可見性。
        如果連接真的斷開，這個 task 會被取消，TTL 會自然過期。
        """
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)

                # 刷新連接 TTL
                try:
                    if hasattr(self, 'user') and self.user.is_authenticated:
                        await connection_manager.refresh_connection(
                            self.user.id, self.channel_name
                        )
                        await self.refresh_presence_ttl()
                        logger.debug(f"心跳：刷新用戶 {self.user.id} 的連接和 presence TTL")
                except Exception as e:
                    # 記錄錯誤但繼續循環，不中斷心跳
                    logger.error(f"心跳刷新發生錯誤: {str(e)}")
        except asyncio.CancelledError:
            # 正常取消，不需要記錄錯誤
            pass

    # ========== 評論通知處理 ==========

    async def comment_notification(self, event):
        """
        處理評論通知事件並發送給客戶端

        Args:
            event: 包含 action 和評論數據的事件
        """
        action = event.get('action')

        if action == 'add':
            await self.send(text_data=json.dumps({
                'type': 'comment_add',
                'comment': event.get('comment')
            }))
        elif action == 'update':
            await self.send(text_data=json.dumps({
                'type': 'comment_update',
                'comment_id': event.get('comment_id'),
                'content': event.get('content'),
                'updated_at': event.get('updated_at')
            }))
        elif action == 'delete':
            await self.send(text_data=json.dumps({
                'type': 'comment_delete',
                'comment_id': event.get('comment_id'),
                'parent_id': event.get('parent_id')
            }))
