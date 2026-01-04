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


class DocumentListSchema(Schema):
    """文檔列表響應模式"""
    id: uuid.UUID
    title: str
    owner: UserSchema
    created_at: datetime
    updated_at: datetime
    is_owner: bool = False


class DocumentSchema(Schema):
    """文檔詳細響應模式"""
    id: uuid.UUID
    title: str
    content: dict
    owner: UserSchema
    created_at: datetime
    updated_at: datetime
    is_owner: bool = False


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
