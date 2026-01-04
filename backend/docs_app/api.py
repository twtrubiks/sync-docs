import uuid
import logging
from ninja_extra import api_controller, http_get, http_post, http_put, http_delete
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.http import Http404
from .models import Document
from typing import List
from ninja_jwt.authentication import JWTAuth
from ninja_extra.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Q
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .schemas import (
    UserSchema,
    ShareRequestSchema,
    DocumentListSchema,
    DocumentSchema,
    DocumentCreateSchema,
    DocumentUpdateSchema,
)

# 獲取日誌記錄器
logger = logging.getLogger('docs_app')

@api_controller("/documents", tags=["documents"], auth=JWTAuth(), permissions=[IsAuthenticated])
class DocumentController:

    def _get_user_accessible_documents_query(self, user):
        """
        返回用戶可以訪問的文檔查詢條件（擁有或被分享的文檔）
        """
        return Q(owner=user) | Q(shared_with=user)

    def _get_document_with_permission_check(self, document_id, user, owner_only=False):
        """
        獲取文檔並檢查權限，如果沒有權限則拋出404

        Args:
            document_id: 文檔ID
            user: 當前用戶
            owner_only: 是否只允許擁有者訪問

        Returns:
            Document: 文檔對象，已設置is_owner屬性
        """
        try:
            if owner_only:
                query = Q(owner=user)
                logger.debug(f"用戶 {user.username} 嘗試以擁有者身份訪問文檔 {document_id}")
            else:
                query = self._get_user_accessible_documents_query(user)
                logger.debug(f"用戶 {user.username} 嘗試訪問文檔 {document_id}")

            document = Document.objects.select_related('owner').filter(
                Q(id=document_id) & query
            ).distinct().first()

            if document is None:
                raise Http404("Document not found")

            # 動態設置is_owner標誌
            document.is_owner = (document.owner == user)
            logger.info(f"用戶 {user.username} 成功訪問文檔 {document_id}")
            return document

        except Exception as e:
            logger.warning(f"用戶 {user.username} 訪問文檔 {document_id} 失敗: {str(e)}")
            raise

    def _set_is_owner_flag(self, documents, user):
        """
        為文檔列表設置is_owner標誌

        Args:
            documents: 文檔查詢集或列表
            user: 當前用戶
        """
        for doc in documents:
            doc.is_owner = (doc.owner == user)

    @http_post("/", response=DocumentSchema)
    def create_document(self, payload: DocumentCreateSchema):
        """
        創建新文檔

        Args:
            payload: 包含文檔標題和內容的創建請求

        Returns:
            DocumentSchema: 創建的文檔信息
        """
        user = self.context.request.auth
        try:
            logger.info(f"用戶 {user.username} 嘗試創建新文檔: {payload.title}")
            document = Document.objects.create(
                **payload.dict(exclude_none=True),
                owner=user
            )
            document.is_owner = True  # 創建者始終是擁有者
            logger.info(f"用戶 {user.username} 成功創建文檔 {document.id}: {document.title}")
            return document
        except Exception as e:
            logger.error(f"用戶 {user.username} 創建文檔失敗: {str(e)}")
            raise

    @http_get("/", response=List[DocumentListSchema])
    def list_documents(self):
        """
        獲取用戶擁有或被分享的文檔列表

        Returns:
            List[DocumentListSchema]: 文檔列表，包含基本信息和擁有者標誌
        """
        user = self.context.request.auth
        query = self._get_user_accessible_documents_query(user)
        documents = Document.objects.select_related('owner').filter(query).distinct()

        # 為每個文檔設置is_owner標誌
        self._set_is_owner_flag(documents, user)

        return documents

    @http_get("/{document_id}/", response=DocumentSchema)
    def get_document(self, document_id: uuid.UUID):
        """
        根據ID獲取特定文檔（如果用戶有訪問權限）

        Args:
            document_id: 文檔的UUID

        Returns:
            DocumentSchema: 文檔詳細信息
        """
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user)
        return document

    @http_put("/{document_id}/", response=DocumentSchema)
    def update_document(self, document_id: uuid.UUID, payload: DocumentUpdateSchema):
        """
        更新特定文檔（如果用戶有訪問權限）
        同時向協作者廣播更新事件

        Args:
            document_id: 文檔的UUID
            payload: 包含更新內容的請求數據

        Returns:
            DocumentSchema: 更新後的文檔信息
        """
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user)

        # 更新文檔屬性
        for attr, value in payload.dict(exclude_unset=True).items():
            setattr(document, attr, value)
        document.save()

        # 向文檔的頻道組廣播保存事件
        self._broadcast_document_saved(document)

        return document

    def _broadcast_document_saved(self, document):
        """
        向文檔的協作者廣播文檔已保存的事件

        Args:
            document: 已保存的文檔對象
        """
        try:
            channel_layer = get_channel_layer()
            room_group_name = f'doc_{document.id}'

            logger.debug(f"廣播文檔 {document.id} 保存事件到頻道組 {room_group_name}")

            # 在同步上下文中運行異步的channel_layer.group_send
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    "type": "doc_saved",
                    "updated_at": document.updated_at.isoformat(),
                },
            )
            logger.debug(f"成功廣播文檔 {document.id} 保存事件")
        except Exception as e:
            logger.error(f"廣播文檔 {document.id} 保存事件失敗: {str(e)}")

    @http_delete("/{document_id}/")
    def delete_document(self, document_id: uuid.UUID):
        """
        刪除特定文檔（僅擁有者可以刪除）

        Args:
            document_id: 要刪除的文檔UUID

        Returns:
            dict: 包含成功標誌的響應
        """
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user, owner_only=True)
        document.delete()
        return {"success": True}

    @http_get("/{document_id}/collaborators/", response=List[UserSchema])
    def get_collaborators(self, document_id: uuid.UUID):
        """
        獲取文檔的協作者列表（僅擁有者可以訪問）

        Args:
            document_id: 文檔的UUID

        Returns:
            List[UserSchema]: 協作者用戶列表
        """
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user, owner_only=True)
        return document.shared_with.all()

    @http_post("/{document_id}/collaborators/", response=UserSchema)
    def add_collaborator(self, document_id: uuid.UUID, payload: ShareRequestSchema):
        """
        為文檔添加協作者（僅擁有者可以添加）

        Args:
            document_id: 文檔的UUID
            payload: 包含要添加用戶名的請求數據

        Returns:
            UserSchema: 被添加的用戶信息
        """
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user, owner_only=True)
        user_to_add = get_object_or_404(User, username=payload.username)

        # 檢查是否分享給自己
        if user_to_add.id == user.id:
            raise HttpError(400, "You cannot share a document with yourself.")

        document.shared_with.add(user_to_add)
        return user_to_add

    @http_delete("/{document_id}/collaborators/{user_id}/")
    def remove_collaborator(self, document_id: uuid.UUID, user_id: int):
        """
        從文檔中移除協作者（僅擁有者可以移除）

        Args:
            document_id: 文檔的UUID
            user_id: 要移除的用戶ID

        Returns:
            dict: 包含成功標誌的響應
        """
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user, owner_only=True)
        user_to_remove = get_object_or_404(User, id=user_id)
        document.shared_with.remove(user_to_remove)
        return {"success": True}
