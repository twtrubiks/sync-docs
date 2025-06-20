"""
WebSocket消費者測試模組
測試文檔協作的WebSocket功能
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from docs_app.consumers import DocConsumer

pytestmark = pytest.mark.django_db


class TestDocConsumer:
    """DocConsumer測試類"""

    def test_has_permission_authenticated_user(self, test_user):
        """測試已認證用戶的基本權限檢查"""
        # 測試用戶是否已認證
        assert test_user.is_authenticated

        # 測試匿名用戶
        anonymous_user = AnonymousUser()
        assert not anonymous_user.is_authenticated

    def test_document_creation_and_ownership(self, test_user, test_document):
        """測試文檔創建和擁有權"""
        # 確保文檔擁有者是測試用戶
        assert test_document.owner == test_user
        assert test_document.title == "Test Document"

        # 測試文檔的can_user_access方法
        assert test_document.can_user_access(test_user) is True

    def test_shared_document_access(self, test_user, another_user, shared_document):
        """測試共享文檔訪問權限"""
        # 確保文檔擁有者是test_user
        assert shared_document.owner == test_user

        # 確保another_user在shared_with中
        assert another_user in shared_document.shared_with.all()

        # 測試擁有者和協作者都能訪問
        assert shared_document.can_user_access(test_user) is True
        assert shared_document.can_user_access(another_user) is True

    def test_anonymous_user_properties(self):
        """測試匿名用戶的屬性"""
        anonymous_user = AnonymousUser()
        assert not anonymous_user.is_authenticated
        assert anonymous_user.id is None

    def test_consumer_initialization(self):
        """測試消費者初始化"""
        consumer = DocConsumer()
        assert consumer is not None


