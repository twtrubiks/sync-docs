"""
評論 API 控制器

提供評論的 CRUD 操作，支持即時同步廣播
"""
import uuid
import logging
from typing import List
from ninja_extra import api_controller, http_get, http_post, http_put, http_delete
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from django.http import Http404
from ninja_jwt.authentication import JWTAuth
from ninja_extra.permissions import IsAuthenticated
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Document, Comment
from .schemas import (
    CommentCreateSchema,
    CommentUpdateSchema,
    CommentSchema,
    CommentListSchema,
)

logger = logging.getLogger('docs_app')


@api_controller("/documents", tags=["comments"], auth=JWTAuth(), permissions=[IsAuthenticated])
class CommentController:
    """評論 API 控制器"""

    def _get_document_with_permission_check(self, document_id, user, require_write=False):
        """
        獲取文檔並檢查權限（複用現有模式）

        Args:
            document_id: 文檔ID
            user: 當前用戶
            require_write: 是否要求寫入權限

        Returns:
            Document: 文檔對象
        """
        try:
            document = Document.objects.select_related('owner').get(id=document_id)
        except Document.DoesNotExist:
            logger.warning(f"用戶 {user.username} 訪問不存在的文檔 {document_id}")
            raise Http404("Document not found")

        # 檢查訪問權限
        if not document.can_user_access(user):
            logger.warning(f"用戶 {user.username} 無權限訪問文檔 {document_id}")
            raise Http404("Document not found")

        # 檢查寫入權限
        if require_write and not document.can_user_write(user):
            logger.warning(f"只讀用戶 {user.username} 嘗試寫入文檔 {document_id}")
            raise HttpError(403, "沒有編輯權限")

        return document

    def _broadcast_comment_event(self, document_id, action, comment_data):
        """
        廣播評論事件到 WebSocket（參考 _broadcast_document_saved 模式）

        Args:
            document_id: 文檔ID
            action: 操作類型（add/update/delete）
            comment_data: 評論數據
        """
        try:
            channel_layer = get_channel_layer()
            room_group_name = f'doc_{document_id}'

            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'comment_notification',
                    'action': action,
                    **comment_data
                }
            )
            logger.debug(f"廣播評論事件 {action} 到 {room_group_name}")
        except Exception as e:
            logger.error(f"廣播評論事件失敗: {e}")

    @http_get("/{document_id}/comments/", response=CommentListSchema)
    def list_comments(self, document_id: uuid.UUID):
        """列出文件的所有評論"""
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user)

        # 只取頂層評論（非回覆），使用 select_related 避免 N+1
        # 按建立時間降序排列（最新的在前面）
        comments = Comment.objects.filter(
            document=document,
            parent__isnull=True
        ).select_related('author').prefetch_related('replies').order_by('-created_at')

        # 判斷當前用戶是否是文件擁有者
        is_doc_owner = (document.owner == user)

        # 轉換為 Schema，標記當前用戶是否為作者和是否可刪除
        result = []
        for comment in comments:
            is_author = (comment.author == user)
            result.append(CommentSchema(
                id=comment.id,
                content=comment.content,
                author_username=comment.author_username,
                created_at=comment.created_at,
                updated_at=comment.updated_at,
                parent_id=comment.parent_id,
                reply_count=comment.reply_count,
                is_author=is_author,
                can_delete=(is_author or is_doc_owner)
            ))

        return CommentListSchema(comments=result, total=len(result))

    @http_get("/{document_id}/comments/{comment_id}/replies/", response=List[CommentSchema])
    def list_replies(self, document_id: uuid.UUID, comment_id: uuid.UUID):
        """列出特定評論的回覆"""
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user)

        # 驗證父評論存在
        parent_comment = get_object_or_404(Comment, id=comment_id, document=document)

        # 取得回覆
        replies = Comment.objects.filter(
            document=document,
            parent=parent_comment
        ).select_related('author').order_by('created_at')

        # 判斷當前用戶是否是文件擁有者
        is_doc_owner = (document.owner == user)

        result = []
        for reply in replies:
            is_author = (reply.author == user)
            result.append(CommentSchema(
                id=reply.id,
                content=reply.content,
                author_username=reply.author_username,
                created_at=reply.created_at,
                updated_at=reply.updated_at,
                parent_id=reply.parent_id,
                reply_count=0,  # 回覆不再有子回覆
                is_author=is_author,
                can_delete=(is_author or is_doc_owner)
            ))

        return result

    @http_post("/{document_id}/comments/", response=CommentSchema)
    def create_comment(self, document_id: uuid.UUID, payload: CommentCreateSchema):
        """創建評論（需要寫入權限）"""
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user, require_write=True)

        # 驗證父評論存在（如果是回覆）
        parent = None
        if payload.parent_id:
            parent = get_object_or_404(Comment, id=payload.parent_id, document=document)

        comment = Comment.objects.create(
            document=document,
            author=user,
            content=payload.content,
            parent=parent
        )

        logger.info(f"用戶 {user.username} 創建評論 {comment.id} 在文檔 {document_id}")

        # 廣播評論事件（只傳基本數據，is_author/can_delete 由前端根據當前用戶計算）
        self._broadcast_comment_event(document_id, 'add', {
            'comment': {
                'id': str(comment.id),
                'content': comment.content,
                'author_username': comment.author_username,
                'author_id': str(comment.author.id),  # 轉為字串，與前端一致
                'created_at': comment.created_at.isoformat(),
                'updated_at': comment.updated_at.isoformat(),
                'parent_id': str(comment.parent_id) if comment.parent_id else None,
                'reply_count': 0
            }
        })

        return CommentSchema(
            id=comment.id,
            content=comment.content,
            author_username=comment.author_username,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            parent_id=comment.parent_id,
            reply_count=0,
            is_author=True,
            can_delete=True  # 創建者自己一定可以刪除
        )

    @http_put("/{document_id}/comments/{comment_id}/", response=CommentSchema)
    def update_comment(self, document_id: uuid.UUID, comment_id: uuid.UUID, payload: CommentUpdateSchema):
        """編輯評論（僅作者可編輯）"""
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user)

        comment = get_object_or_404(Comment, id=comment_id, document=document)

        # 檢查是否為作者
        if comment.author != user:
            logger.warning(f"用戶 {user.username} 嘗試編輯他人評論 {comment_id}")
            raise HttpError(403, "只能編輯自己的評論")

        comment.content = payload.content
        comment.save()

        logger.info(f"用戶 {user.username} 更新評論 {comment_id}")

        # 廣播評論更新事件
        self._broadcast_comment_event(document_id, 'update', {
            'comment_id': str(comment.id),
            'content': comment.content,
            'updated_at': comment.updated_at.isoformat()
        })

        return CommentSchema(
            id=comment.id,
            content=comment.content,
            author_username=comment.author_username,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
            parent_id=comment.parent_id,
            reply_count=comment.reply_count,
            is_author=True,
            can_delete=True  # 編輯者就是作者，一定可以刪除
        )

    @http_delete("/{document_id}/comments/{comment_id}/")
    def delete_comment(self, document_id: uuid.UUID, comment_id: uuid.UUID):
        """刪除評論（作者或文件擁有者可刪除）"""
        user = self.context.request.auth
        document = self._get_document_with_permission_check(document_id, user)

        comment = get_object_or_404(Comment, id=comment_id, document=document)

        # 檢查刪除權限：作者或文件擁有者
        if comment.author != user and document.owner != user:
            logger.warning(f"用戶 {user.username} 嘗試刪除他人評論 {comment_id}")
            raise HttpError(403, "沒有刪除權限")

        comment_id_str = str(comment.id)
        comment.delete()

        logger.info(f"用戶 {user.username} 刪除評論 {comment_id_str}")

        # 廣播評論刪除事件
        self._broadcast_comment_event(document_id, 'delete', {
            'comment_id': comment_id_str
        })

        return {"success": True, "message": "評論已刪除"}
