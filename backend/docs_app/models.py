"""
文檔應用的數據模型定義
包含文檔實體及其相關的數據結構
"""

import uuid
from django.db import models
from django.contrib.auth.models import User


class Document(models.Model):
    """
    文檔模型

    表示系統中的一個協作文檔，包含標題、內容、擁有者和協作者信息

    Attributes:
        id (UUIDField): 文檔的唯一標識符，使用UUID4格式
        title (CharField): 文檔標題，最大長度255字符
        owner (ForeignKey): 文檔擁有者，關聯到User模型
        shared_with (ManyToManyField): 與此文檔共享的用戶列表
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

    shared_with = models.ManyToManyField(
        User,
        related_name='shared_documents',
        blank=True,
        help_text="與此文檔共享的用戶"
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
        return self.shared_with.count()

    def is_shared_with_user(self, user):
        """檢查文檔是否與指定用戶共享"""
        return self.shared_with.filter(id=user.id).exists()

    def can_user_access(self, user):
        """檢查用戶是否可以訪問此文檔"""
        return self.owner == user or self.is_shared_with_user(user)
