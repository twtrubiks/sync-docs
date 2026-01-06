"""
評論功能測試

包含 Model、Schema、API 和 WebSocket 的完整測試
"""
import uuid

import pytest
from django.test import Client
from ninja_jwt.tokens import AccessToken
from pydantic import ValidationError

from docs_app.models import Comment, DocumentCollaborator, PermissionLevel
from docs_app.schemas import CommentCreateSchema, CommentUpdateSchema


# ========== Phase 1: Model 測試 ==========

@pytest.mark.django_db
class TestCommentModel:
    """評論模型測試"""

    def test_comment_creation(self, test_user, test_document):
        """測試評論創建"""
        comment = Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Test comment"
        )
        assert comment.id is not None
        assert comment.content == "Test comment"
        assert comment.author == test_user
        assert comment.document == test_document
        assert comment.parent is None

    def test_comment_belongs_to_document(self, test_user, test_document):
        """測試評論與文檔的關聯"""
        comment = Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Test"
        )
        assert comment.document == test_document
        assert comment in test_document.comments.all()

    def test_reply_to_comment(self, test_user, test_document):
        """測試回覆功能"""
        parent = Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Parent"
        )
        reply = Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Reply",
            parent=parent
        )
        assert reply.parent == parent
        assert reply in parent.replies.all()

    def test_cascade_delete_with_document(self, test_user, test_document):
        """測試刪除文檔時級聯刪除評論"""
        Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Test"
        )
        doc_id = test_document.id
        test_document.delete()
        assert Comment.objects.filter(document_id=doc_id).count() == 0

    def test_cascade_delete_replies(self, test_user, test_document):
        """測試刪除父評論時級聯刪除回覆"""
        parent = Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Parent"
        )
        Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Reply",
            parent=parent
        )
        parent_id = parent.id
        parent.delete()
        assert Comment.objects.filter(parent_id=parent_id).count() == 0

    def test_author_username_property(self, test_user, test_document):
        """測試 author_username 屬性"""
        comment = Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Test"
        )
        assert comment.author_username == test_user.username

    def test_reply_count_property(self, test_user, test_document):
        """測試 reply_count 屬性"""
        parent = Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Parent"
        )
        assert parent.reply_count == 0

        Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Reply 1",
            parent=parent
        )
        Comment.objects.create(
            document=test_document,
            author=test_user,
            content="Reply 2",
            parent=parent
        )

        # 刷新 parent 以獲取最新的 reply_count
        parent.refresh_from_db()
        assert parent.reply_count == 2


# ========== Phase 2: Schema 測試 ==========

class TestCommentSchemas:
    """評論 Schema 驗證測試"""

    def test_comment_create_schema_valid(self):
        """測試有效的創建請求"""
        schema = CommentCreateSchema(content="Valid comment")
        assert schema.content == "Valid comment"

    def test_comment_create_schema_strips_whitespace(self):
        """測試內容自動去除首尾空白"""
        schema = CommentCreateSchema(content="  Trimmed content  ")
        assert schema.content == "Trimmed content"

    def test_comment_create_schema_empty_content_rejected(self):
        """測試空內容被拒絕"""
        with pytest.raises(ValidationError):
            CommentCreateSchema(content="")

    def test_comment_create_schema_whitespace_only_rejected(self):
        """測試純空白被拒絕"""
        with pytest.raises(ValidationError):
            CommentCreateSchema(content="   ")

    def test_comment_create_schema_too_long_rejected(self):
        """測試超長內容被拒絕（>5000字元）"""
        with pytest.raises(ValidationError):
            CommentCreateSchema(content="x" * 5001)

    def test_comment_update_schema_valid(self):
        """測試有效的更新請求"""
        schema = CommentUpdateSchema(content="Updated content")
        assert schema.content == "Updated content"

    def test_comment_update_schema_empty_rejected(self):
        """測試空內容更新被拒絕"""
        with pytest.raises(ValidationError):
            CommentUpdateSchema(content="")


# ========== Phase 3: API 測試 ==========

@pytest.fixture
def authenticated_client(test_user):
    """創建已認證的測試客戶端"""
    token = AccessToken.for_user(test_user)
    client = Client()
    return client, test_user, str(token)


@pytest.fixture
def owner_client(test_user):
    """創建文檔擁有者的測試客戶端"""
    token = AccessToken.for_user(test_user)
    client = Client()
    return client, test_user, str(token)


@pytest.fixture
def collaborator_client(another_user):
    """創建協作者的測試客戶端"""
    token = AccessToken.for_user(another_user)
    client = Client()
    return client, another_user, str(token)


@pytest.fixture
def readonly_client(read_only_user):
    """創建只讀用戶的測試客戶端"""
    token = AccessToken.for_user(read_only_user)
    client = Client()
    return client, read_only_user, str(token)


@pytest.fixture
def own_comment(test_user, test_document):
    """創建用戶自己的評論"""
    return Comment.objects.create(
        document=test_document,
        author=test_user,
        content="My own comment"
    )


@pytest.fixture
def others_comment(another_user, shared_document):
    """創建其他用戶的評論（在共享文檔上）"""
    return Comment.objects.create(
        document=shared_document,
        author=another_user,
        content="Someone else's comment"
    )


@pytest.fixture
def collaborators_comment(another_user, test_document):
    """創建協作者的評論（在文檔擁有者的文檔上）"""
    # 先將 another_user 加為協作者
    DocumentCollaborator.objects.create(
        document=test_document,
        user=another_user,
        permission=PermissionLevel.WRITE
    )
    return Comment.objects.create(
        document=test_document,
        author=another_user,
        content="Collaborator's comment"
    )


@pytest.mark.django_db
class TestCommentAPI:
    """評論 API 測試"""

    # === CRUD 測試 ===

    def test_list_comments_empty(self, authenticated_client, test_document):
        """測試空評論列表"""
        client, user, token = authenticated_client
        response = client.get(
            f"/api/documents/{test_document.id}/comments/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["comments"] == []

    def test_list_comments_with_data(self, authenticated_client, test_document, own_comment):
        """測試有評論的列表"""
        client, user, token = authenticated_client
        response = client.get(
            f"/api/documents/{test_document.id}/comments/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["comments"][0]["content"] == "My own comment"

    def test_list_comments_ordered_by_newest_first(self, authenticated_client, test_document):
        """測試評論列表按最新排序（降序）"""
        client, user, token = authenticated_client

        # 創建多個評論
        Comment.objects.create(document=test_document, author=user, content="First")
        Comment.objects.create(document=test_document, author=user, content="Second")
        Comment.objects.create(document=test_document, author=user, content="Third")

        response = client.get(
            f"/api/documents/{test_document.id}/comments/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )

        assert response.status_code == 200
        comments = response.json()["comments"]
        assert len(comments) == 3
        # 最新的在前面
        assert comments[0]["content"] == "Third"
        assert comments[1]["content"] == "Second"
        assert comments[2]["content"] == "First"

    def test_create_comment_success(self, authenticated_client, test_document):
        """測試創建評論"""
        client, user, token = authenticated_client
        response = client.post(
            f"/api/documents/{test_document.id}/comments/",
            data={"content": "New comment"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "New comment"
        assert data["is_author"] is True
        assert data["can_delete"] is True

    def test_create_reply_success(self, authenticated_client, test_document, own_comment):
        """測試創建回覆"""
        client, user, token = authenticated_client
        response = client.post(
            f"/api/documents/{test_document.id}/comments/",
            data={"content": "Reply", "parent_id": str(own_comment.id)},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 200
        assert response.json()["parent_id"] == str(own_comment.id)

    def test_list_replies(self, authenticated_client, test_document, own_comment):
        """測試列出回覆"""
        client, user, token = authenticated_client
        # 創建一個回覆
        Comment.objects.create(
            document=test_document,
            author=user,
            content="A reply",
            parent=own_comment
        )
        response = client.get(
            f"/api/documents/{test_document.id}/comments/{own_comment.id}/replies/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["content"] == "A reply"

    def test_update_own_comment(self, authenticated_client, test_document, own_comment):
        """測試編輯自己的評論"""
        client, user, token = authenticated_client
        response = client.put(
            f"/api/documents/{test_document.id}/comments/{own_comment.id}/",
            data={"content": "Updated"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 200
        assert response.json()["content"] == "Updated"

    def test_delete_own_comment(self, authenticated_client, test_document, own_comment):
        """測試刪除自己的評論"""
        client, user, token = authenticated_client
        response = client.delete(
            f"/api/documents/{test_document.id}/comments/{own_comment.id}/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    # === 權限測試 ===

    def test_readonly_user_cannot_create(self, readonly_client, read_only_shared_document):
        """測試只讀用戶無法創建評論"""
        client, user, token = readonly_client
        response = client.post(
            f"/api/documents/{read_only_shared_document.id}/comments/",
            data={"content": "Test"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 403

    def test_cannot_update_others_comment(self, authenticated_client, shared_document, others_comment):
        """測試無法編輯他人評論"""
        client, user, token = authenticated_client
        response = client.put(
            f"/api/documents/{shared_document.id}/comments/{others_comment.id}/",
            data={"content": "Hacked"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 403

    def test_cannot_delete_others_comment_as_collaborator(self, collaborator_client, shared_document):
        """測試協作者無法刪除擁有者的評論"""
        client, user, token = collaborator_client
        # 創建擁有者的評論
        owners_comment = Comment.objects.create(
            document=shared_document,
            author=shared_document.owner,
            content="Owner's comment"
        )
        response = client.delete(
            f"/api/documents/{shared_document.id}/comments/{owners_comment.id}/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 403

    def test_owner_can_delete_any_comment(self, owner_client, test_document, collaborators_comment):
        """測試文件擁有者可刪除任何評論"""
        client, user, token = owner_client
        response = client.delete(
            f"/api/documents/{test_document.id}/comments/{collaborators_comment.id}/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 200

    # === 回應格式測試 ===

    def test_comment_has_is_author_flag(self, authenticated_client, test_document, own_comment):
        """測試回應包含 is_author 標誌"""
        client, user, token = authenticated_client
        response = client.get(
            f"/api/documents/{test_document.id}/comments/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        comments = response.json()["comments"]
        own = next(c for c in comments if c["id"] == str(own_comment.id))
        assert own["is_author"] is True

    def test_comment_has_can_delete_flag_for_owner(self, owner_client, test_document, collaborators_comment):
        """測試文件擁有者看到 can_delete=True"""
        client, user, token = owner_client
        response = client.get(
            f"/api/documents/{test_document.id}/comments/",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        comments = response.json()["comments"]
        other = next(c for c in comments if c["id"] == str(collaborators_comment.id))
        assert other["can_delete"] is True  # 擁有者可刪任何評論

    # === 錯誤處理測試 ===

    def test_create_comment_on_nonexistent_document(self, authenticated_client):
        """測試在不存在的文檔上創建評論"""
        client, user, token = authenticated_client
        fake_doc_id = uuid.uuid4()
        response = client.post(
            f"/api/documents/{fake_doc_id}/comments/",
            data={"content": "Test"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 404

    def test_create_reply_to_nonexistent_parent(self, authenticated_client, test_document):
        """測試回覆不存在的父評論"""
        client, user, token = authenticated_client
        fake_comment_id = uuid.uuid4()
        response = client.post(
            f"/api/documents/{test_document.id}/comments/",
            data={"content": "Reply", "parent_id": str(fake_comment_id)},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 404

    def test_unauthorized_access(self, test_document):
        """測試未認證訪問"""
        client = Client()
        response = client.get(
            f"/api/documents/{test_document.id}/comments/"
        )
        assert response.status_code == 401
