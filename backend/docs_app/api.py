import uuid
import logging
from ninja_extra import api_controller, http_get, http_post, http_put, http_delete
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.http import Http404
from .models import Document, DocumentCollaborator, DocumentVersion, PermissionLevel
from typing import List
from ninja_jwt.authentication import JWTAuth
from ninja_extra.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Q
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .schemas import (
    ShareRequestSchema,
    CollaboratorSchema,
    UpdateCollaboratorPermissionSchema,
    DocumentListSchema,
    DocumentSchema,
    DocumentCreateSchema,
    DocumentUpdateSchema,
    VersionListItemSchema,
    VersionDetailSchema,
    RestoreVersionResponseSchema,
)

# 獲取日誌記錄器
logger = logging.getLogger('docs_app')

@api_controller("/documents", tags=["documents"], auth=JWTAuth(), permissions=[IsAuthenticated])
class DocumentController:

    def _get_user_accessible_documents_query(self, user):
        """
        返回用戶可以訪問的文檔查詢條件（擁有或被分享的文檔）
        """
        return Q(owner=user) | Q(collaborators__user=user)

    def _get_document_with_permission_check(self, document_id, user, require_write=False, owner_only=False):
        """
        獲取文檔並檢查權限，如果沒有權限則拋出404或403

        Args:
            document_id: 文檔ID
            user: 當前用戶
            require_write: 是否要求寫入權限
            owner_only: 是否只允許擁有者訪問

        Returns:
            Document: 文檔對象，已設置 is_owner、permission、can_write 屬性
        """
        try:
            document = Document.objects.select_related('owner').get(id=document_id)
        except Document.DoesNotExist:
            logger.warning(f"用戶 {user.username} 訪問不存在的文檔 {document_id}")
            raise Http404("Document not found")

        # 檢查是否是擁有者
        if document.owner == user:
            document.is_owner = True
            document.permission = 'owner'
            document.can_write = True
            logger.info(f"用戶 {user.username} 以擁有者身份訪問文檔 {document_id}")
            return document

        # owner_only 模式：非擁有者不能訪問
        if owner_only:
            logger.warning(f"用戶 {user.username} 嘗試以擁有者身份訪問文檔 {document_id} 但不是擁有者")
            raise Http404("Document not found")

        # 檢查協作者權限
        collab = document.collaborators.filter(user=user).first()
        if not collab:
            logger.warning(f"用戶 {user.username} 無權限訪問文檔 {document_id}")
            raise Http404("Document not found")

        # 需要寫入權限但只有讀取權限
        if require_write and collab.permission != PermissionLevel.WRITE:
            logger.warning(f"只讀用戶 {user.username} 嘗試編輯文檔 {document_id}")
            raise HttpError(403, "You do not have permission to edit this document")

        document.is_owner = False
        document.permission = collab.permission
        document.can_write = (collab.permission == PermissionLevel.WRITE)
        logger.info(f"用戶 {user.username} 以協作者身份訪問文檔 {document_id} (權限: {collab.permission})")
        return document

    def _set_document_permissions(self, documents, user):
        """
        為文檔列表設置權限標誌

        Args:
            documents: 文檔查詢集或列表
            user: 當前用戶
        """
        # 預先獲取用戶的所有協作關係
        user_collaborations = {
            collab.document_id: collab.permission
            for collab in DocumentCollaborator.objects.filter(
                user=user,
                document__in=documents
            )
        }

        for doc in documents:
            doc.is_owner = (doc.owner == user)
            if doc.is_owner:
                doc.permission = 'owner'
                doc.can_write = True
            else:
                permission = user_collaborations.get(doc.id)
                doc.permission = permission
                doc.can_write = (permission == PermissionLevel.WRITE)

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
            document.permission = 'owner'
            document.can_write = True
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
            List[DocumentListSchema]: 文檔列表，包含基本信息和權限標誌
        """
        user = self.context.request.auth
        query = self._get_user_accessible_documents_query(user)
        documents = Document.objects.select_related('owner').filter(query).distinct()

        # 為每個文檔設置權限標誌
        self._set_document_permissions(documents, user)

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
        更新特定文檔（需要編輯權限）
        同時向協作者廣播更新事件，內容變化時自動創建版本

        Args:
            document_id: 文檔的UUID
            payload: 包含更新內容的請求數據

        Returns:
            DocumentSchema: 更新後的文檔信息
        """
        user = self.context.request.auth
        # 關鍵修改：require_write=True
        document = self._get_document_with_permission_check(
            document_id, user, require_write=True
        )

        # 檢查內容是否有變化
        content_changed = payload.content is not None and document.content != payload.content

        # 更新文檔屬性
        for attr, value in payload.dict(exclude_unset=True).items():
            setattr(document, attr, value)
        document.save()

        # 內容變化時創建版本
        if content_changed:
            DocumentVersion.create_version(document, user)
            # 清理舊版本
            DocumentVersion.cleanup_old_versions(document, keep_count=50)
            logger.info(f"用戶 {user.username} 更新文檔 {document_id} 並創建新版本")

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

    @http_get("/{document_id}/collaborators/", response=List[CollaboratorSchema])
    def get_collaborators(self, document_id: uuid.UUID):
        """
        獲取文檔的協作者列表（僅擁有者可以訪問）

        Args:
            document_id: 文檔的UUID

        Returns:
            List[CollaboratorSchema]: 協作者列表，包含權限信息
        """
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user, owner_only=True)

        collaborators = []
        for collab in document.collaborators.select_related('user').all():
            collaborators.append({
                'id': collab.user.id,
                'username': collab.user.username,
                'email': collab.user.email,
                'permission': collab.permission,
            })
        return collaborators

    @http_post("/{document_id}/collaborators/", response=CollaboratorSchema)
    def add_collaborator(self, document_id: uuid.UUID, payload: ShareRequestSchema):
        """
        為文檔添加協作者（僅擁有者可以添加）

        Args:
            document_id: 文檔的UUID
            payload: 包含要添加用戶名和權限的請求數據

        Returns:
            CollaboratorSchema: 被添加的協作者信息
        """
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user, owner_only=True)
        user_to_add = get_object_or_404(User, username=payload.username)

        # 檢查是否分享給自己
        if user_to_add.id == user.id:
            raise HttpError(400, "You cannot share a document with yourself.")

        # 檢查是否已存在，如果存在則更新權限
        existing = document.collaborators.filter(user=user_to_add).first()
        if existing:
            existing.permission = payload.permission
            existing.save()
            collab = existing
            logger.info(f"用戶 {user.username} 更新協作者 {user_to_add.username} 的權限為 {payload.permission}")
        else:
            collab = DocumentCollaborator.objects.create(
                document=document,
                user=user_to_add,
                permission=payload.permission
            )
            logger.info(f"用戶 {user.username} 添加協作者 {user_to_add.username} (權限: {payload.permission})")

        return {
            'id': user_to_add.id,
            'username': user_to_add.username,
            'email': user_to_add.email,
            'permission': collab.permission,
        }

    @http_put("/{document_id}/collaborators/{user_id}/", response=CollaboratorSchema)
    def update_collaborator_permission(
        self,
        document_id: uuid.UUID,
        user_id: int,
        payload: UpdateCollaboratorPermissionSchema
    ):
        """
        更新協作者的權限級別（僅擁有者可以更新）

        Args:
            document_id: 文檔的UUID
            user_id: 要更新的用戶ID
            payload: 包含新權限級別的請求數據

        Returns:
            CollaboratorSchema: 更新後的協作者信息
        """
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user, owner_only=True)

        collab = get_object_or_404(DocumentCollaborator, document=document, user_id=user_id)
        collab.permission = payload.permission
        collab.save()

        logger.info(f"用戶 {user.username} 更新協作者 {collab.user.username} 的權限為 {payload.permission}")

        return {
            'id': collab.user.id,
            'username': collab.user.username,
            'email': collab.user.email,
            'permission': collab.permission,
        }

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

        collab = get_object_or_404(DocumentCollaborator, document=document, user_id=user_id)
        username = collab.user.username
        collab.delete()

        logger.info(f"用戶 {user.username} 移除協作者 {username}")
        return {"success": True}

    # ============ 版本歷史相關 API ============

    @http_get("/{document_id}/versions/", response=List[VersionListItemSchema])
    def list_versions(self, document_id: uuid.UUID):
        """
        列出文件的所有版本

        Args:
            document_id: 文檔的UUID

        Returns:
            List[VersionListItemSchema]: 版本列表（最多50個，按版本號降序排列）
        """
        user = self.context.request.auth
        # 使用現有的權限檢查方法
        document = self._get_document_with_permission_check(document_id, user)

        versions = DocumentVersion.objects.filter(
            document=document
        ).select_related('created_by').order_by('-version_number')[:50]

        return versions

    @http_get("/{document_id}/versions/{version_id}/", response=VersionDetailSchema)
    def get_version(self, document_id: uuid.UUID, version_id: uuid.UUID):
        """
        獲取特定版本的詳細內容

        Args:
            document_id: 文檔的UUID
            version_id: 版本的UUID

        Returns:
            VersionDetailSchema: 版本詳情（含完整內容）
        """
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user)

        version = get_object_or_404(
            DocumentVersion,
            id=version_id,
            document=document
        )

        return version

    @http_post("/{document_id}/versions/{version_id}/restore/", response=RestoreVersionResponseSchema)
    def restore_version(self, document_id: uuid.UUID, version_id: uuid.UUID):
        """
        還原到指定版本

        Args:
            document_id: 文檔的UUID
            version_id: 版本的UUID

        Returns:
            RestoreVersionResponseSchema: 還原結果
        """
        user = self.context.request.auth
        # 需要寫入權限
        document = self._get_document_with_permission_check(
            document_id, user, require_write=True
        )

        version = get_object_or_404(
            DocumentVersion,
            id=version_id,
            document=document
        )

        # 還原 = 用舊版本覆蓋 + 創建新版本
        document.content = version.content
        document.save()

        # 創建新版本記錄
        new_version = DocumentVersion.create_version(document, user)

        logger.info(f"用戶 {user.username} 將文檔 {document_id} 還原到版本 {version.version_number}，創建新版本 {new_version.version_number}")

        return RestoreVersionResponseSchema(
            success=True,
            message=f"已還原到版本 {version.version_number}",
            new_version_number=new_version.version_number
        )
