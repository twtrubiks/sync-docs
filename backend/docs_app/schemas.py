"""
Schema 模組
定義所有 API 請求和響應的 Pydantic Schema
"""

import uuid
from datetime import datetime
from typing import Optional
from ninja import Schema


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
