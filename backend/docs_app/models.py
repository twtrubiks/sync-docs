"""
文檔應用的數據模型定義
包含文檔實體及其相關的數據結構
"""

import uuid
from django.db import models
from django.contrib.auth.models import User


class PermissionLevel(models.TextChoices):
    """
    權限級別選項

    定義協作者對文檔的訪問權限級別
    """
    READ = 'read', '只讀'
    WRITE = 'write', '編輯'


class Document(models.Model):
    """
    文檔模型

    表示系統中的一個協作文檔，包含標題、內容、擁有者信息

    Attributes:
        id (UUIDField): 文檔的唯一標識符，使用UUID4格式
        title (CharField): 文檔標題，最大長度255字符
        owner (ForeignKey): 文檔擁有者，關聯到User模型
        content (JSONField): 文檔內容，以JSON格式存儲
        created_at (DateTimeField): 文檔創建時間，自動設置
        updated_at (DateTimeField): 文檔最後更新時間，自動更新
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="文檔的唯一標識符"
    )

    title = models.CharField(
        max_length=255,
        help_text="文檔標題"
    )

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='owned_documents',
        help_text="文檔擁有者"
    )

    content = models.JSONField(
        default=dict,
        help_text="文檔內容，以JSON格式存儲"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="文檔創建時間"
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="文檔最後更新時間"
    )

    class Meta:
        """模型元數據"""
        verbose_name = "文檔"
        verbose_name_plural = "文檔"
        ordering = ['-updated_at']  # 按更新時間倒序排列
        indexes = [
            models.Index(fields=['owner', '-updated_at']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        """返回文檔的字符串表示"""
        return f"{self.title} (by {self.owner.username})"

    def get_collaborators_count(self):
        """獲取協作者數量"""
        return self.collaborators.count()

    def is_shared_with_user(self, user):
        """檢查文檔是否與指定用戶共享"""
        return self.collaborators.filter(user=user).exists()

    def can_user_access(self, user):
        """檢查用戶是否可以訪問此文檔（讀取權限）"""
        return self.owner == user or self.is_shared_with_user(user)

    def can_user_write(self, user):
        """檢查用戶是否可以編輯此文檔"""
        if self.owner == user:
            return True
        return self.collaborators.filter(
            user=user,
            permission=PermissionLevel.WRITE
        ).exists()

    def get_user_permission(self, user):
        """
        獲取用戶對此文檔的權限級別

        Returns:
            str: 'owner' | 'read' | 'write' | None
        """
        if self.owner == user:
            return 'owner'
        collab = self.collaborators.filter(user=user).first()
        if collab:
            return collab.permission
        return None


class DocumentCollaborator(models.Model):
    """
    文檔協作者中間模型

    用於存儲協作者的權限級別，替代簡單的 ManyToMany 關係

    Attributes:
        document: 關聯的文檔
        user: 協作者用戶
        permission: 權限級別（read/write）
        created_at: 協作關係創建時間
    """

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='collaborators',
        help_text="關聯的文檔"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='document_collaborations',
        help_text="協作者用戶"
    )

    permission = models.CharField(
        max_length=10,
        choices=PermissionLevel.choices,
        default=PermissionLevel.WRITE,
        help_text="權限級別"
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="協作關係創建時間"
    )

    class Meta:
        """模型元數據"""
        verbose_name = "文檔協作者"
        verbose_name_plural = "文檔協作者"
        unique_together = ['document', 'user']  # 確保唯一性
        indexes = [
            models.Index(fields=['document', 'user']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        """返回協作關係的字符串表示"""
        return f"{self.user.username} - {self.document.title} ({self.permission})"
