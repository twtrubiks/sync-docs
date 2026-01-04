"""
模型測試模組
測試Document模型的方法和功能
"""

import time

import pytest
from django.contrib.auth.models import User
from docs_app.models import Document, DocumentCollaborator, PermissionLevel

pytestmark = pytest.mark.django_db


@pytest.fixture
def third_user():
    """創建第三個測試用戶"""
    return User.objects.create_user(
        username="thirduser",
        password="testpassword",
        email="third@example.com"
    )


class TestDocumentModel:
    """Document模型測試類"""

    def test_document_creation(self, test_user):
        """測試文檔創建"""
        document = Document.objects.create(
            title="New Document",
            content={"type": "doc", "content": []},
            owner=test_user
        )

        assert document.title == "New Document"
        assert document.owner == test_user
        assert document.content == {"type": "doc", "content": []}
        assert document.created_at is not None
        assert document.updated_at is not None
        assert str(document.id) is not None  # UUID應該被生成

    def test_document_str_method(self, test_document):
        """測試文檔的字符串表示方法"""
        expected_str = f"{test_document.title} (by {test_document.owner.username})"
        assert str(test_document) == expected_str

    def test_get_collaborators_count_no_collaborators(self, test_document):
        """測試沒有協作者時的協作者數量"""
        count = test_document.get_collaborators_count()
        assert count == 0

    def test_get_collaborators_count_with_collaborators(self, test_document, another_user, third_user):
        """測試有協作者時的協作者數量"""
        # 添加協作者
        DocumentCollaborator.objects.create(
            document=test_document,
            user=another_user,
            permission=PermissionLevel.WRITE
        )
        DocumentCollaborator.objects.create(
            document=test_document,
            user=third_user,
            permission=PermissionLevel.READ
        )

        count = test_document.get_collaborators_count()
        assert count == 2

    def test_get_collaborators_count_after_removing_collaborator(self, test_document, another_user, third_user):
        """測試移除協作者後的協作者數量"""
        # 添加協作者
        collab1 = DocumentCollaborator.objects.create(
            document=test_document,
            user=another_user,
            permission=PermissionLevel.WRITE
        )
        DocumentCollaborator.objects.create(
            document=test_document,
            user=third_user,
            permission=PermissionLevel.READ
        )
        assert test_document.get_collaborators_count() == 2

        # 移除一個協作者
        collab1.delete()
        assert test_document.get_collaborators_count() == 1

    def test_is_shared_with_user_true(self, test_document, another_user):
        """測試文檔與用戶共享時返回True"""
        DocumentCollaborator.objects.create(
            document=test_document,
            user=another_user,
            permission=PermissionLevel.READ
        )

        assert test_document.is_shared_with_user(another_user) is True

    def test_is_shared_with_user_false(self, test_document, another_user):
        """測試文檔未與用戶共享時返回False"""
        assert test_document.is_shared_with_user(another_user) is False

    def test_is_shared_with_user_owner(self, test_document):
        """測試文檔擁有者不在collaborators中時返回False"""
        # 擁有者不應該在collaborators中，這個方法只檢查collaborators
        assert test_document.is_shared_with_user(test_document.owner) is False

    def test_can_user_access_owner(self, test_document):
        """測試文檔擁有者可以訪問文檔"""
        assert test_document.can_user_access(test_document.owner) is True

    def test_can_user_access_collaborator(self, test_document, another_user):
        """測試協作者可以訪問文檔"""
        DocumentCollaborator.objects.create(
            document=test_document,
            user=another_user,
            permission=PermissionLevel.READ
        )

        assert test_document.can_user_access(another_user) is True

    def test_can_user_access_non_collaborator(self, test_document, another_user):
        """測試非協作者不能訪問文檔"""
        assert test_document.can_user_access(another_user) is False

    def test_can_user_access_multiple_collaborators(self, test_document, another_user, third_user):
        """測試多個協作者都可以訪問文檔"""
        DocumentCollaborator.objects.create(
            document=test_document,
            user=another_user,
            permission=PermissionLevel.WRITE
        )
        DocumentCollaborator.objects.create(
            document=test_document,
            user=third_user,
            permission=PermissionLevel.READ
        )

        assert test_document.can_user_access(test_document.owner) is True
        assert test_document.can_user_access(another_user) is True
        assert test_document.can_user_access(third_user) is True

    def test_document_ordering(self, test_user):
        """測試文檔按更新時間倒序排列"""
        # 創建第一個文檔
        doc1 = Document.objects.create(
            title="First Document",
            content={"data": "first"},
            owner=test_user
        )

        # 等待一小段時間確保時間戳不同
        time.sleep(0.01)

        # 創建第二個文檔
        doc2 = Document.objects.create(
            title="Second Document",
            content={"data": "second"},
            owner=test_user
        )

        # 獲取所有文檔，應該按updated_at倒序排列
        documents = list(Document.objects.all())

        assert documents[0] == doc2  # 最新的文檔應該在前面
        assert documents[1] == doc1

    def test_document_meta_verbose_names(self):
        """測試模型的verbose name設置"""
        assert Document._meta.verbose_name == "文檔"
        assert Document._meta.verbose_name_plural == "文檔"

    def test_document_indexes(self):
        """測試模型的索引設置"""
        indexes = Document._meta.indexes
        assert len(indexes) == 2

        # 檢查索引字段
        index_fields = [index.fields for index in indexes]
        assert ['owner', '-updated_at'] in index_fields
        assert ['-created_at'] in index_fields

    def test_document_collaborator_relationship(self, test_document, another_user, third_user):
        """測試DocumentCollaborator關係"""
        # 測試添加協作者
        collab1 = DocumentCollaborator.objects.create(
            document=test_document,
            user=another_user,
            permission=PermissionLevel.WRITE
        )
        assert test_document.collaborators.filter(user=another_user).exists()

        # 測試添加多個協作者
        collab2 = DocumentCollaborator.objects.create(
            document=test_document,
            user=third_user,
            permission=PermissionLevel.READ
        )
        collaborators = test_document.collaborators.all()
        assert collaborators.filter(user=another_user).exists()
        assert collaborators.filter(user=third_user).exists()
        assert collaborators.count() == 2

        # 測試權限級別
        assert collab1.permission == PermissionLevel.WRITE
        assert collab2.permission == PermissionLevel.READ

        # 測試反向關係
        shared_docs = another_user.document_collaborations.all()
        assert shared_docs.filter(document=test_document).exists()

    def test_document_owner_relationship(self, test_user):
        """測試owner外鍵關係"""
        document = Document.objects.create(
            title="Owner Test Document",
            content={"data": "test"},
            owner=test_user
        )

        # 測試正向關係
        assert document.owner == test_user

        # 測試反向關係
        owned_docs = test_user.owned_documents.all()
        assert document in owned_docs

    def test_document_cascade_delete(self, test_user):
        """測試當用戶被刪除時文檔也被刪除（CASCADE）"""
        document = Document.objects.create(
            title="Cascade Test Document",
            content={"data": "test"},
            owner=test_user
        )

        document_id = document.id
        assert Document.objects.filter(id=document_id).exists()

        # 刪除用戶
        test_user.delete()

        # 文檔應該也被刪除
        assert not Document.objects.filter(id=document_id).exists()

    def test_document_content_default(self, test_user):
        """測試文檔內容的默認值"""
        document = Document.objects.create(
            title="Default Content Test",
            owner=test_user
            # 不提供content，應該使用默認值
        )

        assert document.content == {}  # 默認值是空字典

    def test_document_uuid_uniqueness(self, test_user):
        """測試文檔UUID的唯一性"""
        doc1 = Document.objects.create(
            title="Document 1",
            owner=test_user
        )

        doc2 = Document.objects.create(
            title="Document 2",
            owner=test_user
        )

        # UUID應該是唯一的
        assert doc1.id != doc2.id
        assert str(doc1.id) != str(doc2.id)

    def test_document_timestamps(self, test_user):
        """測試文檔時間戳的自動設置和更新"""
        document = Document.objects.create(
            title="Timestamp Test",
            owner=test_user
        )

        created_at = document.created_at
        updated_at = document.updated_at

        # 創建時間和更新時間應該被設置
        assert created_at is not None
        assert updated_at is not None

        # 更新文檔
        time.sleep(0.01)  # 確保時間差異
        document.title = "Updated Title"
        document.save()

        document.refresh_from_db()

        # 創建時間不應該改變，更新時間應該改變
        assert document.created_at == created_at
        assert document.updated_at > updated_at

    def test_can_user_write_owner(self, test_document):
        """測試文檔擁有者可以編輯文檔"""
        assert test_document.can_user_write(test_document.owner) is True

    def test_can_user_write_write_collaborator(self, test_document, another_user):
        """測試編輯權限協作者可以編輯文檔"""
        DocumentCollaborator.objects.create(
            document=test_document,
            user=another_user,
            permission=PermissionLevel.WRITE
        )
        assert test_document.can_user_write(another_user) is True

    def test_can_user_write_read_collaborator(self, test_document, another_user):
        """測試只讀權限協作者不能編輯文檔"""
        DocumentCollaborator.objects.create(
            document=test_document,
            user=another_user,
            permission=PermissionLevel.READ
        )
        assert test_document.can_user_write(another_user) is False

    def test_can_user_write_non_collaborator(self, test_document, another_user):
        """測試非協作者不能編輯文檔"""
        assert test_document.can_user_write(another_user) is False

    def test_get_user_permission_owner(self, test_document):
        """測試獲取擁有者權限返回'owner'"""
        permission = test_document.get_user_permission(test_document.owner)
        assert permission == 'owner'

    def test_get_user_permission_write_collaborator(self, test_document, another_user):
        """測試獲取編輯協作者權限返回'write'"""
        DocumentCollaborator.objects.create(
            document=test_document,
            user=another_user,
            permission=PermissionLevel.WRITE
        )
        permission = test_document.get_user_permission(another_user)
        assert permission == PermissionLevel.WRITE

    def test_get_user_permission_read_collaborator(self, test_document, another_user):
        """測試獲取只讀協作者權限返回'read'"""
        DocumentCollaborator.objects.create(
            document=test_document,
            user=another_user,
            permission=PermissionLevel.READ
        )
        permission = test_document.get_user_permission(another_user)
        assert permission == PermissionLevel.READ

    def test_get_user_permission_non_collaborator(self, test_document, another_user):
        """測試獲取非協作者權限返回None"""
        permission = test_document.get_user_permission(another_user)
        assert permission is None
