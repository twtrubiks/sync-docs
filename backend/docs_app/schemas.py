"""
Schema 模組
定義所有 API 請求和響應的 Pydantic Schema
"""

import uuid
from datetime import datetime
from typing import Optional, Union, Dict, Any, List
from ninja import Schema
from pydantic import field_validator, model_validator


# ============ 用戶相關 Schema ============

class UserSchema(Schema):
    """用戶信息響應模式"""
    id: int
    username: str
    email: Optional[str] = None


class RegisterSchema(Schema):
    """用戶註冊請求模式"""
    username: str
    password: str
    email: Optional[str] = None


# ============ 文檔相關 Schema ============

class ShareRequestSchema(Schema):
    """分享請求模式"""
    username: str
    permission: str = 'write'  # 預設編輯權限

    @field_validator('permission')
    @classmethod
    def validate_permission(cls, v):
        """驗證權限級別"""
        allowed = ['read', 'write']
        if v not in allowed:
            raise ValueError(f"Permission must be one of: {allowed}")
        return v


class CollaboratorSchema(Schema):
    """協作者信息響應模式"""
    id: int
    username: str
    email: Optional[str] = None
    permission: str  # 'read' 或 'write'


class UpdateCollaboratorPermissionSchema(Schema):
    """更新協作者權限請求模式"""
    permission: str

    @field_validator('permission')
    @classmethod
    def validate_permission(cls, v):
        """驗證權限級別"""
        allowed = ['read', 'write']
        if v not in allowed:
            raise ValueError(f"Permission must be one of: {allowed}")
        return v


class DocumentListSchema(Schema):
    """文檔列表響應模式"""
    id: uuid.UUID
    title: str
    owner: UserSchema
    created_at: datetime
    updated_at: datetime
    is_owner: bool = False
    permission: Optional[str] = None  # 用戶對該文檔的權限級別
    can_write: bool = True  # 用戶是否可以編輯


class DocumentSchema(Schema):
    """文檔詳細響應模式"""
    id: uuid.UUID
    title: str
    content: dict
    owner: UserSchema
    created_at: datetime
    updated_at: datetime
    is_owner: bool = False
    permission: Optional[str] = None  # 用戶對該文檔的權限級別
    can_write: bool = True  # 用戶是否可以編輯


class DocumentCreateSchema(Schema):
    """文檔創建請求模式"""
    title: str
    content: Optional[dict] = None


class DocumentUpdateSchema(Schema):
    """文檔更新請求模式"""
    title: Optional[str] = None
    content: Optional[dict] = None


# ============ WebSocket Delta Schema ============

class DeltaOperationSchema(Schema):
    """
    Quill Delta 單一操作的 Schema

    每個操作必須有且僅有 insert、retain 或 delete 之一
    - insert: 插入文字或嵌入對象（如圖片）
    - retain: 保留指定長度的內容（可選擇性地應用格式）
    - delete: 刪除指定長度的內容
    - attributes: 可選的格式化屬性
    """
    insert: Union[str, Dict[str, Any], None] = None
    retain: Optional[int] = None
    delete: Optional[int] = None
    attributes: Optional[Dict[str, Any]] = None

    @model_validator(mode='after')
    def validate_operation_type(self):
        """確保每個操作有且僅有一個操作類型"""
        ops_present = sum([
            self.insert is not None,
            self.retain is not None,
            self.delete is not None
        ])

        if ops_present != 1:
            raise ValueError(
                "Each delta operation must have exactly one of: insert, retain, or delete"
            )

        # retain 和 delete 必須是正整數
        if self.retain is not None and self.retain <= 0:
            raise ValueError("retain must be a positive integer")

        if self.delete is not None and self.delete <= 0:
            raise ValueError("delete must be a positive integer")

        return self


class DeltaSchema(Schema):
    """
    Quill Delta 格式 Schema

    Delta 必須有 ops 陣列，包含一個或多個操作
    """
    ops: List[DeltaOperationSchema]

    @field_validator('ops')
    @classmethod
    def validate_ops_not_empty(cls, v):
        """確保 ops 陣列不為空"""
        if not v:
            raise ValueError("ops array cannot be empty")
        return v


class WebSocketMessageSchema(Schema):
    """
    WebSocket 消息 Schema

    用於驗證從客戶端接收的 WebSocket 消息
    """
    delta: DeltaSchema


# ============ 游標與在線狀態 Schema ============

class CursorPosition(Schema):
    """游標位置"""
    index: int        # Quill 游標位置（字符索引）
    length: int = 0   # 選取長度（0 = 只有游標）


class CursorMoveMessage(Schema):
    """WebSocket cursor_move 消息驗證"""
    type: str = "cursor_move"
    index: int
    length: int = 0


class PresenceUser(Schema):
    """在線用戶資訊"""
    user_id: str
    username: str
    color: str
    cursor: Optional[CursorPosition] = None


# ============ 版本歷史 Schema ============

class VersionListItemSchema(Schema):
    """版本列表項目"""
    id: uuid.UUID
    version_number: int
    created_at: datetime
    created_by_username: Optional[str] = None


class VersionDetailSchema(Schema):
    """版本詳情（含內容）"""
    id: uuid.UUID
    version_number: int
    content: dict
    created_at: datetime
    created_by_username: Optional[str] = None


class RestoreVersionResponseSchema(Schema):
    """還原版本回應"""
    success: bool
    message: str
    new_version_number: int
