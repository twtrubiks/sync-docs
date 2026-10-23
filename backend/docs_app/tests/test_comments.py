"""
評論功能測試

包含 Model、Schema、API 和 WebSocket 的完整測試
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
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

    def test_with_reply_count_queryset(self, test_user, test_document):
        """測試 with_reply_count() 自定義 QuerySet 方法"""
        parent1 = Comment.objects.create(
            document=test_document, author=test_user, content="Parent 1"
        )
        parent2 = Comment.objects.create(
            document=test_document, author=test_user, content="Parent 2"
        )
        # parent1 有 3 個回覆, parent2 有 1 個回覆
        for i in range(3):
            Comment.objects.create(
                document=test_document, author=test_user,
                content=f"Reply {i}", parent=parent1
            )
        Comment.objects.create(
            document=test_document, author=test_user,
            content="Reply", parent=parent2
        )

        comments = Comment.objects.with_reply_count().filter(
            parent__isnull=True
        ).order_by('created_at')

        assert comments[0].annotated_reply_count == 3
        assert comments[1].annotated_reply_count == 1

    def test_with_reply_count_no_replies(self, test_user, test_document):
        """測試 with_reply_count() 在沒有回覆時返回 0"""
        Comment.objects.create(
            document=test_document, author=test_user, content="No replies"
        )
        comment = Comment.objects.with_reply_count().first()
        assert comment.annotated_reply_count == 0


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

    def test_comment_update_schema_too_long_rejected(self):
        with pytest.raises(ValidationError, match="評論內容不能超過 5000 字元"):
            CommentUpdateSchema(content="x" * 5001)

    def test_comment_schemas_accept_exactly_5000_chars(self):
        assert len(CommentCreateSchema(content="x" * 5000).content) == 5000
        assert len(CommentUpdateSchema(content="x" * 5000).content) == 5000

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

    def test_list_comments_reply_count_uses_annotate(self, authenticated_client, test_document):
        """測試 list_comments 使用 annotate 計算 reply_count，避免 N+1"""
        client, user, token = authenticated_client

        # 建立 3 個頂層評論，各有不同數量的回覆
        for i in range(3):
            parent = Comment.objects.create(
                document=test_document, author=user, content=f"Comment {i}"
            )
            for j in range(i + 1):  # 分別有 1, 2, 3 個回覆
                Comment.objects.create(
                    document=test_document, author=user,
                    content=f"Reply {j}", parent=parent
                )

        # 記錄查詢數量，確認不會隨評論數增加
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(
                f"/api/documents/{test_document.id}/comments/",
                HTTP_AUTHORIZATION=f"Bearer {token}"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

        # 驗證 reply_count 正確（最新的在前面）
        comments = data["comments"]
        assert comments[0]["reply_count"] == 3
        assert comments[1]["reply_count"] == 2
        assert comments[2]["reply_count"] == 1

        # 確認沒有 N+1：不應該有 per-comment 的 reply count 查詢
        # 過濾出 comment 相關的查詢（排除 auth/permission 查詢）
        comment_queries = [
            q['sql'] for q in ctx.captured_queries
            if 'docs_app_comment' in q['sql']
        ]
        # 應該只有 1 條 comment 查詢（帶 COUNT annotate 的主查詢）
        # 而不是 1 + N 條（主查詢 + 每個 comment 的 reply count）
        assert len(comment_queries) <= 2  # 主查詢 + 可能的 count 查詢

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
        assert response.status_code == 201
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
        assert response.status_code == 201
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

    def test_create_reply_to_reply_rejected(self, authenticated_client, test_document, own_comment):
        """回覆的回覆會被拒絕：前端只載入頂層評論的回覆，巢狀回覆永遠不會被顯示"""
        client, user, token = authenticated_client
        reply = Comment.objects.create(
            document=test_document,
            author=user,
            content="A reply",
            parent=own_comment
        )
        response = client.post(
            f"/api/documents/{test_document.id}/comments/",
            data={"content": "Nested reply", "parent_id": str(reply.id)},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert response.status_code == 400
        assert Comment.objects.filter(parent=reply).count() == 0

    def test_unauthorized_access(self, test_document):
        """測試未認證訪問"""
        client = Client()
        response = client.get(
            f"/api/documents/{test_document.id}/comments/"
        )
        assert response.status_code == 401


@pytest.fixture
def mock_channel_layer():
    """攔截評論 API 的 WebSocket 廣播"""
    with patch('docs_app.comment_api.get_channel_layer') as mock_get_channel_layer:
        layer = MagicMock()
        layer.group_send = AsyncMock()
        mock_get_channel_layer.return_value = layer
        yield layer


def _broadcast_event(layer, document):
    layer.group_send.assert_called_once()
    group_name, event = layer.group_send.call_args[0]
    assert group_name == f"doc_{document.id}"
    assert event["type"] == "comment_notification"
    return event


@pytest.mark.django_db
class TestCommentAPIContracts:
    """評論 API 的持久化、即時廣播 payload 與權限旗標（前端 CommentPanel 依賴這些欄位）"""

    def test_create_comment_broadcasts_add_event(self, authenticated_client, test_document, mock_channel_layer):
        client, user, token = authenticated_client

        response = client.post(
            f"/api/documents/{test_document.id}/comments/",
            data={"content": "Hello"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 201
        body = response.json()
        assert body["reply_count"] == 0
        comment = Comment.objects.get(id=body["id"])
        event = _broadcast_event(mock_channel_layer, test_document)
        assert event["action"] == "add"
        assert event["comment"] == {
            "id": str(comment.id),
            "content": "Hello",
            "author_username": user.username,
            "author_id": str(user.id),
            "created_at": comment.created_at.isoformat(),
            "updated_at": comment.updated_at.isoformat(),
            "parent_id": None,
            "reply_count": 0,
        }

    def test_create_reply_broadcasts_parent_id(self, authenticated_client, test_document, own_comment,
                                               mock_channel_layer):
        client, user, token = authenticated_client

        response = client.post(
            f"/api/documents/{test_document.id}/comments/",
            data={"content": "Reply", "parent_id": str(own_comment.id)},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 201
        event = _broadcast_event(mock_channel_layer, test_document)
        assert event["comment"]["parent_id"] == str(own_comment.id)

    def test_update_comment_persists_and_broadcasts(self, authenticated_client, test_document, own_comment,
                                                    mock_channel_layer):
        client, user, token = authenticated_client

        response = client.put(
            f"/api/documents/{test_document.id}/comments/{own_comment.id}/",
            data={"content": "Updated"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 200
        body = response.json()
        assert body["is_author"] is True
        assert body["can_delete"] is True
        own_comment.refresh_from_db()
        assert own_comment.content == "Updated", "編輯必須寫入資料庫"
        event = _broadcast_event(mock_channel_layer, test_document)
        assert event == {
            "type": "comment_notification",
            "action": "update",
            "comment_id": str(own_comment.id),
            "content": "Updated",
            "updated_at": own_comment.updated_at.isoformat(),
        }

    def test_delete_comment_removes_and_broadcasts(self, authenticated_client, test_document, own_comment,
                                                   mock_channel_layer):
        client, user, token = authenticated_client

        response = client.delete(
            f"/api/documents/{test_document.id}/comments/{own_comment.id}/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        assert response.status_code == 200
        assert response.json() == {"success": True, "message": "評論已刪除"}
        assert not Comment.objects.filter(id=own_comment.id).exists(), "刪除必須寫入資料庫"
        event = _broadcast_event(mock_channel_layer, test_document)
        assert event == {
            "type": "comment_notification",
            "action": "delete",
            "comment_id": str(own_comment.id),
            "parent_id": None,
        }

    def test_delete_reply_broadcasts_parent_id(self, authenticated_client, test_document, own_comment,
                                               mock_channel_layer):
        client, user, token = authenticated_client
        reply = Comment.objects.create(document=test_document, author=user, content="r", parent=own_comment)

        client.delete(
            f"/api/documents/{test_document.id}/comments/{reply.id}/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        event = _broadcast_event(mock_channel_layer, test_document)
        assert event["parent_id"] == str(own_comment.id)
        assert Comment.objects.filter(id=own_comment.id).exists(), "刪除回覆不應連帶刪除父評論"

    def test_list_replies_flags_per_viewer(self, owner_client, collaborator_client, test_document,
                                           collaborators_comment, test_user, another_user):
        """回覆的 is_author / can_delete：作者可刪、文件擁有者可刪任何回覆、其他協作者不可刪"""
        owner_reply = Comment.objects.create(document=test_document, author=test_user, content="by owner",
                                             parent=collaborators_comment)
        collab_reply = Comment.objects.create(document=test_document, author=another_user, content="by collab",
                                              parent=collaborators_comment)
        url = f"/api/documents/{test_document.id}/comments/{collaborators_comment.id}/replies/"

        def flags(client_tuple):
            client, _, token = client_tuple
            data = client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}").json()
            for item in data:
                assert item["reply_count"] == 0
                assert item["parent_id"] == str(collaborators_comment.id)
            return {item["id"]: (item["is_author"], item["can_delete"]) for item in data}

        assert flags(owner_client) == {
            str(owner_reply.id): (True, True),
            str(collab_reply.id): (False, True),
        }
        assert flags(collaborator_client) == {
            str(owner_reply.id): (False, False),
            str(collab_reply.id): (True, True),
        }

    def test_error_details_shown_to_users(self, authenticated_client, collaborator_client, readonly_client,
                                          shared_document, read_only_shared_document, others_comment, test_user):
        """前端直接顯示 detail：各種拒絕情境的錯誤訊息須維持"""
        client, _, token = authenticated_client
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        base = f"/api/documents/{shared_document.id}/comments/"

        edit_others = client.put(f"{base}{others_comment.id}/", data={"content": "x"},
                                 content_type="application/json", **auth)
        assert (edit_others.status_code, edit_others.json()["detail"]) == (403, "只能編輯自己的評論")

        owners_comment = Comment.objects.create(document=shared_document, author=test_user, content="owner")
        c_client, _, c_token = collaborator_client
        delete_others = c_client.delete(f"{base}{owners_comment.id}/", HTTP_AUTHORIZATION=f"Bearer {c_token}")
        assert (delete_others.status_code, delete_others.json()["detail"]) == (403, "沒有刪除權限")

        reply = Comment.objects.create(document=shared_document, author=test_user, content="r",
                                       parent=owners_comment)
        nested = client.post(base, data={"content": "x", "parent_id": str(reply.id)},
                             content_type="application/json", **auth)
        assert (nested.status_code, nested.json()["detail"]) == (400, "只能回覆頂層評論")

        r_client, _, r_token = readonly_client
        read_only = r_client.post(f"/api/documents/{read_only_shared_document.id}/comments/",
                                  data={"content": "x"}, content_type="application/json",
                                  HTTP_AUTHORIZATION=f"Bearer {r_token}")
        assert (read_only.status_code, read_only.json()["detail"]) == (403, "沒有編輯權限")


@pytest.mark.django_db
def test_non_collaborator_cannot_read_comments(another_user, test_document):
    """評論 API 對無權限者回 404（不洩漏文件存在與否）"""
    client = Client()
    response = client.get(
        f"/api/documents/{test_document.id}/comments/",
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(another_user)}",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_read_only_collaborator_can_read_comments_and_replies(readonly_client, read_only_shared_document, test_user):
    """唯讀協作者不能發表評論，但可以閱讀評論與回覆"""
    client, _, token = readonly_client
    parent = Comment.objects.create(document=read_only_shared_document, author=test_user, content="p")
    Comment.objects.create(document=read_only_shared_document, author=test_user, content="r", parent=parent)
    auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
    base = f"/api/documents/{read_only_shared_document.id}/comments/"

    listed = client.get(base, **auth)
    replies = client.get(f"{base}{parent.id}/replies/", **auth)

    assert listed.status_code == 200
    assert [c["content"] for c in listed.json()["comments"]] == ["p"]
    assert replies.status_code == 200
    assert [c["content"] for c in replies.json()] == ["r"]
