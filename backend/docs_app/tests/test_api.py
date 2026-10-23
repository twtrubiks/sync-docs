import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from docs_app.models import Document, DocumentCollaborator, DocumentVersion, PermissionLevel

# 使用 pytest-django 的 db fixture 來確保資料庫在測試之間是乾淨的
pytestmark = pytest.mark.django_db

# 測試資料常數
DEFAULT_USERNAME = "testuser"
DEFAULT_PASSWORD = "testpassword"
DEFAULT_EMAIL = "test@example.com"

# 測試文檔資料
SAMPLE_DOCUMENT_CONTENT = {
    "type": "doc",
    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Test content"}]}]
}

SIMPLE_DOCUMENT_CONTENT = {
    "type": "doc",
    "content": [{"type": "paragraph"}]
}

# API 端點常數
TOKEN_ENDPOINT = "/api/token/pair"
DOCUMENTS_ENDPOINT = "/api/documents/"

@pytest.fixture
def create_user(django_user_model):
    """建立測試使用者的 fixture"""
    def make_user(**kwargs):
        if 'username' not in kwargs:
            kwargs['username'] = DEFAULT_USERNAME
        if 'password' not in kwargs:
            kwargs['password'] = DEFAULT_PASSWORD
        if 'email' not in kwargs:
            kwargs['email'] = DEFAULT_EMAIL
        user = django_user_model.objects.create_user(**kwargs)
        return user
    return make_user

def get_user_token(client, user):
    """輔助函數：為指定使用者取得 access token"""
    login_data = {
        "username": user.username,
        "password": DEFAULT_PASSWORD  # 假設所有測試使用者都使用預設密碼
    }

    token_response = client.post(
        TOKEN_ENDPOINT,
        data=json.dumps(login_data),
        content_type="application/json"
    )

    if token_response.status_code != 200:
        raise Exception(f"Failed to authenticate user. Status: {token_response.status_code}, Response: {token_response.content.decode()}")

    tokens = token_response.json()
    access_token = tokens.get("access")

    if not access_token:
        raise Exception("Access token not found in login response.")

    return access_token


@pytest.fixture
def authenticated_client(client, create_user):
    """提供已認證的客戶端、使用者和 access token"""
    user_to_auth = create_user()
    access_token = get_user_token(client, user_to_auth)
    return client, user_to_auth, access_token


def test_create_document(authenticated_client):
    """測試建立文檔功能"""
    client, user, access_token = authenticated_client
    document_data = {
        "title": "My First Test Document",
        "content": SIMPLE_DOCUMENT_CONTENT
    }

    response = client.post(
        DOCUMENTS_ENDPOINT,
        data=document_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access_token}"
    )

    assert response.status_code == 201, f"Create document failed: {response.content.decode()}"
    response_data = response.json()
    assert response_data["title"] == document_data["title"]
    assert response_data["owner"]["id"] == user.id
    assert Document.objects.count() == 1

    # 驗證資料庫中的文檔
    doc = Document.objects.first()
    assert doc.title == document_data["title"]
    assert doc.owner == user


def test_list_own_documents(authenticated_client, create_user):
    """測試使用者只能列出自己的文檔"""
    client, user1, access_token1 = authenticated_client

    # 建立另一個使用者用於隔離測試
    user2 = create_user(username='another_user', email='another@example.com')

    # 為 user1 建立文檔
    doc1_user1 = Document.objects.create(owner=user1, title="User1 Doc 1", content={"data": "content1"})
    doc2_user1 = Document.objects.create(owner=user1, title="User1 Doc 2", content={"data": "content2"})

    # 為 user2 建立文檔
    doc1_user2 = Document.objects.create(owner=user2, title="User2 Doc 1", content={"data": "content3"})

    # 以 user1 身份發出 GET 請求
    response = client.get(DOCUMENTS_ENDPOINT, HTTP_AUTHORIZATION=f"Bearer {access_token1}")

    assert response.status_code == 200, f"List documents failed: {response.content.decode()}"
    response_data = response.json()

    # 分頁回應格式
    assert response_data["total"] == 2  # user1 應該只能看到自己的 2 個文檔
    assert "items" in response_data
    assert "page" in response_data
    assert "page_size" in response_data
    assert "total_pages" in response_data

    items = response_data["items"]
    assert len(items) == 2

    response_titles = {doc["title"] for doc in items}
    assert doc1_user1.title in response_titles
    assert doc2_user1.title in response_titles
    assert doc1_user2.title not in response_titles  # 確保 user2 的文檔不在清單中

    # 檢查回應中每個文檔的擁有者 ID
    for doc_data in items:
        assert doc_data["owner"]["id"] == user1.id


def test_get_document_by_id(authenticated_client, create_user):
    """測試根據 ID 取得文檔功能"""
    client, owner_user, owner_access_token = authenticated_client

    document = Document.objects.create(
        owner=owner_user,
        title="Specific Document Title",
        content=SAMPLE_DOCUMENT_CONTENT
    )

    # 測試擁有者可以取得文檔
    response_owner = client.get(
        f"{DOCUMENTS_ENDPOINT}{document.id}/",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_owner.status_code == 200, f"Owner GET failed: {response_owner.content.decode()}"
    response_data_owner = response_owner.json()
    assert response_data_owner["id"] == str(document.id)  # UUID 需要轉為字串比較
    assert response_data_owner["title"] == "Specific Document Title"
    assert response_data_owner["content"] == SAMPLE_DOCUMENT_CONTENT
    assert response_data_owner["owner"]["id"] == owner_user.id

    # 測試其他使用者無法取得文檔 (預期 404 Not Found)
    non_owner_user = create_user(username="nonowner", email="nonowner@example.com")
    non_owner_access_token = get_user_token(client, non_owner_user)

    response_non_owner = client.get(
        f"{DOCUMENTS_ENDPOINT}{document.id}/",
        HTTP_AUTHORIZATION=f"Bearer {non_owner_access_token}"
    )
    assert response_non_owner.status_code == 404  # 或 403 Forbidden


def test_update_document(authenticated_client, create_user):
    """測試更新文檔功能"""
    client, owner_user, owner_access_token = authenticated_client

    # 建立原始文檔
    original_title = "Original Title"
    original_content = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Original content"}]}]}
    document = Document.objects.create(
        owner=owner_user,
        title=original_title,
        content=original_content
    )

    # 準備更新資料
    updated_title = "Updated Title"
    updated_content = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Updated content successfully!"}]}]}
    update_data = {
        "title": updated_title,
        "content": updated_content
    }

    # 測試擁有者可以更新文檔
    response_owner = client.put(
        f"{DOCUMENTS_ENDPOINT}{document.id}/",
        data=update_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_owner.status_code == 200, f"Owner PUT failed: {response_owner.content.decode()}"
    response_data_owner = response_owner.json()
    assert response_data_owner["title"] == updated_title
    assert response_data_owner["content"] == updated_content
    assert response_data_owner["owner"]["id"] == owner_user.id  # 確保擁有者不變

    # 驗證資料庫中的變更
    document.refresh_from_db()
    assert document.title == updated_title
    assert document.content == updated_content

    # 測試其他使用者無法更新文檔
    non_owner_user = create_user(username="nonowner_updater", email="nonowner_updater@example.com")
    non_owner_access_token = get_user_token(client, non_owner_user)

    attempt_update_data = {"title": "Malicious Update", "content": {"data": "bad"}}
    response_non_owner = client.put(
        f"{DOCUMENTS_ENDPOINT}{document.id}/",
        data=attempt_update_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {non_owner_access_token}"
    )
    assert response_non_owner.status_code == 404  # 或 403

    # 確保文檔未被非擁有者修改
    document.refresh_from_db()
    assert document.title == updated_title
    assert document.content == updated_content


def test_update_document_broadcasts_doc_saved(authenticated_client):
    """測試更新文檔時會廣播 doc_saved 事件到 WebSocket 頻道組"""
    client, user, access_token = authenticated_client

    # 建立測試文檔
    document = Document.objects.create(
        owner=user,
        title="Broadcast Test Doc",
        content={"data": "original content"}
    )

    with patch('docs_app.api.get_channel_layer') as mock_get_channel_layer:
        mock_channel_layer = MagicMock()
        # 使用 AsyncMock 正確模擬 async 方法，避免 async_to_sync 警告
        mock_channel_layer.group_send = AsyncMock()
        mock_get_channel_layer.return_value = mock_channel_layer

        # 更新文檔
        update_data = {"title": "Updated Title"}
        response = client.put(
            f"{DOCUMENTS_ENDPOINT}{document.id}/",
            data=update_data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}"
        )

        assert response.status_code == 200, f"Update failed: {response.content.decode()}"

        # 驗證 channel_layer.group_send 被調用
        mock_channel_layer.group_send.assert_called_once()
        call_args = mock_channel_layer.group_send.call_args[0]

        # 驗證頻道組名稱正確
        assert call_args[0] == f"doc_{document.id}"

        # 驗證事件類型和內容
        event = call_args[1]
        assert event["type"] == "doc_saved"
        assert "updated_at" in event


def test_unauthorized_user_cannot_access_document(authenticated_client, create_user):
    """測試未授權使用者無法存取文檔"""
    client, owner_user, _ = authenticated_client

    document = Document.objects.create(
        owner=owner_user,
        title="Secret Document",
        content={"data": "secret content"}
    )

    # 建立未授權使用者
    unauthorized_user = create_user(username="intruder", email="intruder@example.com")
    intruder_access_token = get_user_token(client, unauthorized_user)

    # 嘗試 GET 文檔
    response_get = client.get(
        f"{DOCUMENTS_ENDPOINT}{document.id}/",
        HTTP_AUTHORIZATION=f"Bearer {intruder_access_token}"
    )
    assert response_get.status_code == 404  # 或 403

    # 嘗試 PUT (更新) 文檔
    update_data = {"title": "Hacked Title", "content": {"data": "hacked"}}
    response_put = client.put(
        f"{DOCUMENTS_ENDPOINT}{document.id}/",
        data=update_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {intruder_access_token}"
    )
    assert response_put.status_code == 404  # 或 403

    # 驗證文檔未被 PUT 嘗試修改
    document.refresh_from_db()
    assert document.title == "Secret Document"
    assert document.content == {"data": "secret content"}

    # 嘗試 DELETE 文檔
    response_delete = client.delete(
        f"{DOCUMENTS_ENDPOINT}{document.id}/",
        HTTP_AUTHORIZATION=f"Bearer {intruder_access_token}"
    )
    assert response_delete.status_code == 404  # 或 403

    # 驗證文檔仍然存在
    assert Document.objects.filter(id=document.id).exists()


# --- 分享和協作測試 ---

@pytest.fixture
def collaborator_user_and_token(client, create_user):
    """建立協作者使用者和 token 的 fixture"""
    collaborator_user = create_user(username="collaborator", email="collaborator@example.com")
    access_token = get_user_token(client, collaborator_user)
    return collaborator_user, access_token

def test_owner_can_share_document(authenticated_client, collaborator_user_and_token):
    """測試文檔擁有者可以分享文檔給協作者"""
    client, _, owner_access_token = authenticated_client
    collaborator, _ = collaborator_user_and_token

    # 1. 擁有者建立文檔
    doc_data = {"title": "Shared Doc Test", "content": {"data": "initial content"}}
    response = client.post(
        DOCUMENTS_ENDPOINT,
        data=doc_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response.status_code == 201
    document_id = response.json()["id"]
    document = Document.objects.get(id=document_id)

    # 2. 擁有者與協作者分享文檔
    share_data = {"username": collaborator.username}
    response_share = client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_share.status_code == 201, f"Share document failed: {response_share.content.decode()}"

    # 驗證協作者已加入 collaborators
    document.refresh_from_db()
    assert document.collaborators.filter(user=collaborator).exists()

    # 驗證協作者清單 API
    response_get_collaborators = client.get(
        f"/api/documents/{document_id}/collaborators/",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_get_collaborators.status_code == 200
    collaborators_data = response_get_collaborators.json()
    assert len(collaborators_data) == 1
    assert collaborators_data[0]["username"] == collaborator.username
    assert collaborators_data[0]["permission"] == "write"  # 預設編輯權限


def test_collaborator_can_access_shared_document(authenticated_client, collaborator_user_and_token):
    """測試協作者可以存取被分享的文檔"""
    client, _, owner_access_token = authenticated_client
    collaborator, collaborator_access_token = collaborator_user_and_token

    # 1. 擁有者建立文檔
    doc_data = {"title": "Access Test Doc", "content": {"data": "content for access"}}
    response_create = client.post(
        DOCUMENTS_ENDPOINT,
        data=doc_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_create.status_code == 201
    document_id = response_create.json()["id"]

    # 2. 擁有者與協作者分享文檔
    share_data = {"username": collaborator.username}
    response_share = client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_share.status_code == 201

    # 3. 協作者嘗試存取文檔
    response_access = client.get(
        f"{DOCUMENTS_ENDPOINT}{document_id}/",
        HTTP_AUTHORIZATION=f"Bearer {collaborator_access_token}"
    )
    assert response_access.status_code == 200, f"Collaborator access failed: {response_access.content.decode()}"
    accessed_data = response_access.json()
    assert accessed_data["id"] == document_id
    assert accessed_data["title"] == doc_data["title"]


def test_collaborator_can_edit_shared_document(authenticated_client, collaborator_user_and_token):
    """測試編輯權限協作者可以編輯被分享的文檔"""
    client, _, owner_access_token = authenticated_client
    collaborator, collaborator_access_token = collaborator_user_and_token

    # 1. Owner creates a document
    doc_data = {"title": "Edit Test Doc", "content": {"data": "original content by owner"}}
    response_create = client.post(
        "/api/documents/", data=doc_data, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_create.status_code == 201
    document_id = response_create.json()["id"]

    # 2. Owner shares the document with the collaborator (default write permission)
    share_data = {"username": collaborator.username}
    response_share = client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_share.status_code == 201

    # 3. Collaborator tries to edit the document
    edit_data = {"title": "Edited by Collaborator", "content": {"data": "collaborator's new content"}}
    response_edit = client.put(
        f"/api/documents/{document_id}/",
        data=edit_data, # PUT data can be dict for django test client
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {collaborator_access_token}"
    )
    assert response_edit.status_code == 200, f"Collaborator edit failed: {response_edit.content.decode()}"
    edited_data = response_edit.json()
    assert edited_data["title"] == edit_data["title"]
    assert edited_data["content"] == edit_data["content"]

    # Verify in DB
    document = Document.objects.get(id=document_id)
    assert document.title == edit_data["title"]
    assert document.content == edit_data["content"]


def test_owner_can_remove_collaborator(authenticated_client, collaborator_user_and_token):
    """測試文檔擁有者可以移除協作者"""
    client, _, owner_access_token = authenticated_client
    collaborator, _ = collaborator_user_and_token

    # 1. Owner creates a document and shares it
    doc_data = {"title": "Remove Collaborator Doc", "content": {"data": "content"}}
    response_create = client.post("/api/documents/", data=doc_data, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}")
    assert response_create.status_code == 201
    document_id = response_create.json()["id"]
    document = Document.objects.get(id=document_id)

    share_data = {"username": collaborator.username}
    client.post(f"/api/documents/{document_id}/collaborators/", data=json.dumps(share_data), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}")
    document.refresh_from_db()
    assert document.collaborators.filter(user=collaborator).exists()

    # 2. Owner removes the collaborator
    # Endpoint: DELETE /api/documents/{document_id}/collaborators/{user_id}/
    response_remove = client.delete(
        f"/api/documents/{document_id}/collaborators/{collaborator.id}/",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_remove.status_code == 200, f"Remove collaborator failed: {response_remove.content.decode()}"

    document.refresh_from_db()
    assert not document.collaborators.filter(user=collaborator).exists()

    # 驗證協作者清單為空
    response_get_collaborators = client.get(
        f"/api/documents/{document_id}/collaborators/",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_get_collaborators.status_code == 200
    collaborators_data = response_get_collaborators.json()
    assert len(collaborators_data) == 0


def test_removed_collaborator_loses_access(authenticated_client, collaborator_user_and_token):
    """測試被移除的協作者失去存取權限"""
    client, _, owner_access_token = authenticated_client
    collaborator, collaborator_access_token = collaborator_user_and_token

    # 1. Owner creates, shares, then removes collaborator
    doc_data = {"title": "Lost Access Doc", "content": {"data": "data"}}
    response_create = client.post("/api/documents/", data=doc_data, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}")
    document_id = response_create.json()["id"]

    share_data = {"username": collaborator.username}
    client.post(f"/api/documents/{document_id}/collaborators/", data=json.dumps(share_data), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}")

    client.delete(f"/api/documents/{document_id}/collaborators/{collaborator.id}/", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}")

    # 2. Removed collaborator tries to access the document
    response_access = client.get(
        f"/api/documents/{document_id}/",
        HTTP_AUTHORIZATION=f"Bearer {collaborator_access_token}"
    )
    assert response_access.status_code == 404, f"Removed collaborator still has GET access: {response_access.content.decode()}" # Or 403

    # 3. Removed collaborator tries to edit the document
    edit_data = {"title": "Attempted Edit After Removal", "content": {"data": "should fail"}}
    response_edit = client.put(
        f"/api/documents/{document_id}/",
        data=edit_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {collaborator_access_token}"
    )
    assert response_edit.status_code == 404, f"Removed collaborator can still PUT: {response_edit.content.decode()}" # Or 403

    # Verify document content hasn't changed by the failed edit attempt
    document = Document.objects.get(id=document_id)
    assert document.title == doc_data["title"] # Should be original title
    assert document.content == doc_data["content"]


def test_owner_cannot_share_document_with_self(authenticated_client):
    """測試擁有者不能將自己添加為協作者"""
    client, owner_user, owner_access_token = authenticated_client

    # 1. 擁有者建立文檔
    doc_data = {"title": "Self Share Test Doc", "content": {"data": "content"}}
    response_create = client.post(
        DOCUMENTS_ENDPOINT,
        data=doc_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_create.status_code == 201
    document_id = response_create.json()["id"]
    document = Document.objects.get(id=document_id)

    # 2. 擁有者嘗試將自己添加為協作者
    share_data = {"username": owner_user.username}
    response_share = client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )

    # 3. 預期返回 400 錯誤
    assert response_share.status_code == 400, f"Expected 400, got {response_share.status_code}: {response_share.content.decode()}"
    response_data = response_share.json()
    assert "detail" in response_data
    assert "yourself" in response_data["detail"].lower()

    # 4. 驗證擁有者未被添加到 collaborators
    document.refresh_from_db()
    assert not document.collaborators.filter(user=owner_user).exists()
    assert document.collaborators.count() == 0


# --- 權限區分測試 ---

def test_read_only_collaborator_cannot_edit(authenticated_client, create_user):
    """測試只讀協作者不能編輯文檔"""
    client, owner_user, owner_access_token = authenticated_client

    # 創建只讀協作者
    read_only_user = create_user(username="readonly", email="readonly@example.com")
    read_only_token = get_user_token(client, read_only_user)

    # 擁有者創建文檔
    doc_data = {"title": "Read Only Test", "content": {"data": "original"}}
    response = client.post(
        DOCUMENTS_ENDPOINT,
        data=doc_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    document_id = response.json()["id"]

    # 以只讀權限添加協作者
    share_data = {"username": read_only_user.username, "permission": "read"}
    client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )

    # 只讀用戶嘗試讀取 - 應該成功
    response_get = client.get(
        f"{DOCUMENTS_ENDPOINT}{document_id}/",
        HTTP_AUTHORIZATION=f"Bearer {read_only_token}"
    )
    assert response_get.status_code == 200
    assert response_get.json()["can_write"] == False
    assert response_get.json()["permission"] == "read"

    # 只讀用戶嘗試編輯 - 應該失敗 (403)
    edit_data = {"title": "Hacked by readonly"}
    response_edit = client.put(
        f"{DOCUMENTS_ENDPOINT}{document_id}/",
        data=edit_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {read_only_token}"
    )
    assert response_edit.status_code == 403

    # 驗證文檔未被修改
    document = Document.objects.get(id=document_id)
    assert document.title == doc_data["title"]


def test_write_collaborator_can_edit(authenticated_client, create_user):
    """測試編輯權限協作者可以編輯文檔"""
    client, owner_user, owner_access_token = authenticated_client

    write_user = create_user(username="writer", email="writer@example.com")
    write_token = get_user_token(client, write_user)

    # 擁有者創建文檔
    doc_data = {"title": "Write Test", "content": {"data": "original"}}
    response = client.post(
        DOCUMENTS_ENDPOINT,
        data=doc_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    document_id = response.json()["id"]

    # 以編輯權限添加協作者
    share_data = {"username": write_user.username, "permission": "write"}
    client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )

    # 驗證權限信息
    response_get = client.get(
        f"{DOCUMENTS_ENDPOINT}{document_id}/",
        HTTP_AUTHORIZATION=f"Bearer {write_token}"
    )
    assert response_get.status_code == 200
    assert response_get.json()["can_write"] == True
    assert response_get.json()["permission"] == "write"

    # 編輯用戶嘗試編輯 - 應該成功
    edit_data = {"title": "Edited by writer"}
    response_edit = client.put(
        f"{DOCUMENTS_ENDPOINT}{document_id}/",
        data=edit_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {write_token}"
    )
    assert response_edit.status_code == 200
    assert response_edit.json()["title"] == "Edited by writer"


def test_update_collaborator_permission(authenticated_client, create_user):
    """測試更新協作者權限"""
    client, owner_user, owner_access_token = authenticated_client

    collab_user = create_user(username="collab", email="collab@example.com")
    collab_token = get_user_token(client, collab_user)

    # 創建文檔
    doc_data = {"title": "Permission Update Test", "content": {}}
    response = client.post(
        DOCUMENTS_ENDPOINT,
        data=doc_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    document_id = response.json()["id"]

    # 以只讀權限添加
    share_data = {"username": collab_user.username, "permission": "read"}
    client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )

    # 確認只讀權限不能編輯
    edit_data = {"title": "Should fail"}
    response_edit = client.put(
        f"{DOCUMENTS_ENDPOINT}{document_id}/",
        data=edit_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {collab_token}"
    )
    assert response_edit.status_code == 403

    # 更新為編輯權限
    update_data = {"permission": "write"}
    response_update = client.put(
        f"/api/documents/{document_id}/collaborators/{collab_user.id}/",
        data=json.dumps(update_data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_update.status_code == 200
    assert response_update.json()["permission"] == "write"

    # 確認現在可以編輯
    edit_data = {"title": "Now can edit"}
    response_edit = client.put(
        f"{DOCUMENTS_ENDPOINT}{document_id}/",
        data=edit_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {collab_token}"
    )
    assert response_edit.status_code == 200
    assert response_edit.json()["title"] == "Now can edit"


@pytest.fixture
def shared_doc_for_broadcast(authenticated_client, create_user):
    """建立已分享（write）的文檔，回傳 (client, owner_token, document_id, collab_user)"""
    client, _, owner_access_token = authenticated_client
    collab_user = create_user(username="wscollab", email="wscollab@example.com")

    doc_data = {"title": "Permission Broadcast Doc", "content": {}}
    response = client.post(
        DOCUMENTS_ENDPOINT,
        data=doc_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    document_id = response.json()["id"]

    share_data = {"username": collab_user.username, "permission": "write"}
    client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    return client, owner_access_token, document_id, collab_user


def test_remove_collaborator_broadcasts_permission_changed(shared_doc_for_broadcast):
    """測試移除協作者時廣播 permission_changed（removed=True）到 WebSocket 頻道組"""
    client, owner_access_token, document_id, collab_user = shared_doc_for_broadcast

    with patch('docs_app.api.get_channel_layer') as mock_get_channel_layer:
        mock_channel_layer = MagicMock()
        mock_channel_layer.group_send = AsyncMock()
        mock_get_channel_layer.return_value = mock_channel_layer

        response = client.delete(
            f"/api/documents/{document_id}/collaborators/{collab_user.id}/",
            HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
        )
        assert response.status_code == 200

        mock_channel_layer.group_send.assert_called_once()
        group_name, event = mock_channel_layer.group_send.call_args[0]
        assert group_name == f"doc_{document_id}"
        assert event["type"] == "permission_changed"
        assert event["user_id"] == str(collab_user.id)
        assert event["removed"] is True


def test_update_permission_broadcasts_permission_changed(shared_doc_for_broadcast):
    """測試更新協作者權限時廣播 permission_changed（帶新的 can_write）"""
    client, owner_access_token, document_id, collab_user = shared_doc_for_broadcast

    with patch('docs_app.api.get_channel_layer') as mock_get_channel_layer:
        mock_channel_layer = MagicMock()
        mock_channel_layer.group_send = AsyncMock()
        mock_get_channel_layer.return_value = mock_channel_layer

        # write 降為 read
        response = client.put(
            f"/api/documents/{document_id}/collaborators/{collab_user.id}/",
            data=json.dumps({"permission": "read"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
        )
        assert response.status_code == 200

        mock_channel_layer.group_send.assert_called_once()
        group_name, event = mock_channel_layer.group_send.call_args[0]
        assert group_name == f"doc_{document_id}"
        assert event["type"] == "permission_changed"
        assert event["user_id"] == str(collab_user.id)
        assert event["removed"] is False
        assert event["can_write"] is False


def test_reshare_existing_collaborator_broadcasts_permission_changed(shared_doc_for_broadcast):
    """測試對既有協作者重複 POST（變更權限）也會廣播 permission_changed"""
    client, owner_access_token, document_id, collab_user = shared_doc_for_broadcast

    with patch('docs_app.api.get_channel_layer') as mock_get_channel_layer:
        mock_channel_layer = MagicMock()
        mock_channel_layer.group_send = AsyncMock()
        mock_get_channel_layer.return_value = mock_channel_layer

        # 用 POST 把既有 write 協作者改成 read
        response = client.post(
            f"/api/documents/{document_id}/collaborators/",
            data=json.dumps({"username": collab_user.username, "permission": "read"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
        )
        assert response.status_code == 200  # 更新既有協作者回 200

        mock_channel_layer.group_send.assert_called_once()
        _, event = mock_channel_layer.group_send.call_args[0]
        assert event["type"] == "permission_changed"
        assert event["user_id"] == str(collab_user.id)
        assert event["can_write"] is False


def test_document_response_includes_permission_fields(authenticated_client, create_user):
    """測試文檔響應包含權限欄位"""
    client, owner_user, owner_access_token = authenticated_client

    # 創建文檔
    doc_data = {"title": "Permission Fields Test", "content": {}}
    response = client.post(
        DOCUMENTS_ENDPOINT,
        data=doc_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response.status_code == 201
    response_data = response.json()

    # 驗證擁有者的權限欄位
    assert "permission" in response_data
    assert "can_write" in response_data
    assert response_data["permission"] == "owner"
    assert response_data["can_write"] == True
    assert response_data["is_owner"] == True


# --- 權限旗標、擁有者專屬端點與回應格式（補強變異測試發現的缺口）---

@pytest.fixture
def owner_doc_with_collaborators(client, create_user):
    """
    擁有者文檔 + 一位 write 協作者 + 一位 read 協作者

    回傳 dict：client、各角色 user 與 token、document
    """
    owner = create_user(username="docowner", email="docowner@example.com")
    writer = create_user(username="docwriter", email="docwriter@example.com")
    reader = create_user(username="docreader", email="docreader@example.com")
    document = Document.objects.create(owner=owner, title="Owner Only Doc", content={"ops": [{"insert": "hi\n"}]})
    DocumentCollaborator.objects.create(document=document, user=writer, permission=PermissionLevel.WRITE)
    DocumentCollaborator.objects.create(document=document, user=reader, permission=PermissionLevel.READ)
    return {
        "client": client,
        "document": document,
        "owner": owner, "owner_token": get_user_token(client, owner),
        "writer": writer, "writer_token": get_user_token(client, writer),
        "reader": reader, "reader_token": get_user_token(client, reader),
    }


def test_get_document_permission_flags_per_role(owner_doc_with_collaborators):
    """GET 單一文檔：is_owner / permission / can_write 依角色正確設定（前端據此顯示分享、刪除與編輯 UI）"""
    ctx = owner_doc_with_collaborators
    url = f"{DOCUMENTS_ENDPOINT}{ctx['document'].id}/"
    expected = {
        "owner_token": (True, "owner", True),
        "writer_token": (False, "write", True),
        "reader_token": (False, "read", False),
    }
    for token_key, (is_owner, permission, can_write) in expected.items():
        data = ctx["client"].get(url, HTTP_AUTHORIZATION=f"Bearer {ctx[token_key]}").json()
        assert (data["is_owner"], data["permission"], data["can_write"]) == (is_owner, permission, can_write), token_key


def test_list_documents_permission_flags_mixed(owner_doc_with_collaborators):
    """列表：自己擁有的與被分享的文檔各自帶正確的權限旗標"""
    ctx = owner_doc_with_collaborators
    client = ctx["client"]
    own_doc = Document.objects.create(owner=ctx["reader"], title="Reader Own Doc", content={})

    response = client.get(DOCUMENTS_ENDPOINT, HTTP_AUTHORIZATION=f"Bearer {ctx['reader_token']}")

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()["items"]}
    assert len(items) == 2
    own = items[str(own_doc.id)]
    shared = items[str(ctx["document"].id)]
    assert (own["is_owner"], own["permission"], own["can_write"]) == (True, "owner", True)
    assert (shared["is_owner"], shared["permission"], shared["can_write"]) == (False, "read", False)


def test_list_documents_write_collaborator_can_write(owner_doc_with_collaborators):
    """列表：write 協作者看到被分享文檔 can_write=True、permission='write'"""
    ctx = owner_doc_with_collaborators

    response = ctx["client"].get(DOCUMENTS_ENDPOINT, HTTP_AUTHORIZATION=f"Bearer {ctx['writer_token']}")

    [item] = response.json()["items"]
    assert (item["is_owner"], item["permission"], item["can_write"]) == (False, "write", True)


@pytest.mark.parametrize("method, path, payload", [
    ("delete", "", None),
    ("get", "collaborators/", None),
    ("post", "collaborators/", {"username": "docreader", "permission": "write"}),
    ("put", "collaborators/{reader_id}/", {"permission": "write"}),
    ("delete", "collaborators/{reader_id}/", None),
], ids=["delete-document", "list-collaborators", "add-collaborator", "update-permission", "remove-collaborator"])
def test_write_collaborator_cannot_use_owner_only_endpoints(owner_doc_with_collaborators, method, path, payload):
    """擁有者專屬端點：即使是 write 協作者也一律 404，且不得產生任何副作用"""
    ctx = owner_doc_with_collaborators
    document = ctx["document"]
    url = f"{DOCUMENTS_ENDPOINT}{document.id}/" + path.format(reader_id=ctx["reader"].id)
    kwargs = {"HTTP_AUTHORIZATION": f"Bearer {ctx['writer_token']}"}
    if payload is not None:
        kwargs.update(data=json.dumps(payload), content_type="application/json")

    response = getattr(ctx["client"], method)(url, **kwargs)

    assert response.status_code == 404, response.content.decode()
    assert Document.objects.filter(id=document.id).exists()
    reader_collab = DocumentCollaborator.objects.get(document=document, user=ctx["reader"])
    assert reader_collab.permission == PermissionLevel.READ


def test_owner_can_delete_document(owner_doc_with_collaborators):
    """擁有者刪除文檔：回 success 且文檔（含協作關係）被刪除"""
    ctx = owner_doc_with_collaborators
    document_id = ctx["document"].id

    response = ctx["client"].delete(f"{DOCUMENTS_ENDPOINT}{document_id}/",
                                    HTTP_AUTHORIZATION=f"Bearer {ctx['owner_token']}")

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert not Document.objects.filter(id=document_id).exists()
    assert not DocumentCollaborator.objects.filter(document_id=document_id).exists()


def test_get_nonexistent_document_returns_404(authenticated_client):
    client, _, access_token = authenticated_client

    response = client.get(f"{DOCUMENTS_ENDPOINT}00000000-0000-0000-0000-000000000000/",
                          HTTP_AUTHORIZATION=f"Bearer {access_token}")

    assert response.status_code == 404


def test_create_document_without_content_defaults_to_empty_dict(authenticated_client):
    """未帶 content 建立文檔：使用模型預設 {}，而不是寫入 null"""
    client, _, access_token = authenticated_client

    response = client.post(DOCUMENTS_ENDPOINT, data={"title": "No Content"},
                           content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {access_token}")

    assert response.status_code == 201, response.content.decode()
    assert response.json()["content"] == {}
    assert Document.objects.get(id=response.json()["id"]).content == {}


def test_collaborator_endpoints_include_email(owner_doc_with_collaborators, create_user):
    """協作者相關回應都帶 email（分享對話框顯示用）"""
    ctx = owner_doc_with_collaborators
    client = ctx["client"]
    auth = {"HTTP_AUTHORIZATION": f"Bearer {ctx['owner_token']}"}
    base = f"{DOCUMENTS_ENDPOINT}{ctx['document'].id}/collaborators/"
    newcomer = create_user(username="newcomer", email="newcomer@example.com")

    listed = client.get(base, **auth).json()
    assert {c["username"]: c["email"] for c in listed} == {
        "docwriter": "docwriter@example.com",
        "docreader": "docreader@example.com",
    }

    added = client.post(base, data=json.dumps({"username": "newcomer", "permission": "read"}),
                        content_type="application/json", **auth)
    assert added.status_code == 201
    assert added.json() == {"id": newcomer.id, "username": "newcomer",
                            "email": "newcomer@example.com", "permission": "read"}

    updated = client.put(f"{base}{ctx['reader'].id}/", data=json.dumps({"permission": "write"}),
                         content_type="application/json", **auth)
    assert updated.json() == {"id": ctx["reader"].id, "username": "docreader",
                              "email": "docreader@example.com", "permission": "write"}


def test_reshare_existing_collaborator_persists_new_permission(owner_doc_with_collaborators):
    """對既有協作者重新 POST：新權限必須寫入資料庫，而不只是出現在回應裡"""
    ctx = owner_doc_with_collaborators

    response = ctx["client"].post(
        f"{DOCUMENTS_ENDPOINT}{ctx['document'].id}/collaborators/",
        data=json.dumps({"username": "docreader", "permission": "write"}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {ctx['owner_token']}",
    )

    assert response.status_code == 200
    collab = DocumentCollaborator.objects.get(document=ctx["document"], user=ctx["reader"])
    assert collab.permission == PermissionLevel.WRITE
    assert DocumentCollaborator.objects.filter(document=ctx["document"]).count() == 2


def test_remove_collaborator_returns_success(owner_doc_with_collaborators):
    ctx = owner_doc_with_collaborators

    response = ctx["client"].delete(
        f"{DOCUMENTS_ENDPOINT}{ctx['document'].id}/collaborators/{ctx['reader'].id}/",
        HTTP_AUTHORIZATION=f"Bearer {ctx['owner_token']}",
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}


def test_error_details_shown_to_users(owner_doc_with_collaborators):
    """前端直接顯示 detail：自己分享給自己 / 只讀編輯的錯誤訊息須維持"""
    ctx = owner_doc_with_collaborators
    client = ctx["client"]
    doc_url = f"{DOCUMENTS_ENDPOINT}{ctx['document'].id}/"

    self_share = client.post(f"{doc_url}collaborators/", data=json.dumps({"username": "docowner"}),
                             content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {ctx['owner_token']}")
    assert self_share.status_code == 400
    assert self_share.json()["detail"] == "You cannot share a document with yourself."

    read_only_edit = client.put(doc_url, data={"title": "x"}, content_type="application/json",
                                HTTP_AUTHORIZATION=f"Bearer {ctx['reader_token']}")
    assert read_only_edit.status_code == 403
    assert read_only_edit.json()["detail"] == "You do not have permission to edit this document"


def test_update_document_keeps_at_most_50_versions(owner_doc_with_collaborators):
    """內容變更自動建立版本後，只保留最新 50 個版本"""
    ctx = owner_doc_with_collaborators
    document = ctx["document"]
    for _ in range(50):
        DocumentVersion.create_version(document, ctx["owner"])

    response = ctx["client"].put(f"{DOCUMENTS_ENDPOINT}{document.id}/",
                                 data={"content": {"ops": [{"insert": "new\n"}]}},
                                 content_type="application/json",
                                 HTTP_AUTHORIZATION=f"Bearer {ctx['owner_token']}")

    assert response.status_code == 200
    numbers = list(DocumentVersion.objects.filter(document=document).values_list("version_number", flat=True))
    assert len(numbers) == 50
    assert min(numbers) == 2 and max(numbers) == 51


@pytest.mark.parametrize("method, path", [
    ("post", "collaborators/"),
    ("put", "collaborators/{reader_id}/"),
], ids=["share", "update-permission"])
def test_invalid_permission_value_rejected(owner_doc_with_collaborators, method, path):
    """權限只能是 read / write，其他值（如 admin）一律 422 且不寫入"""
    ctx = owner_doc_with_collaborators
    url = f"{DOCUMENTS_ENDPOINT}{ctx['document'].id}/" + path.format(reader_id=ctx["reader"].id)

    response = getattr(ctx["client"], method)(
        url,
        data=json.dumps({"username": "docreader", "permission": "admin"}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {ctx['owner_token']}",
    )

    assert response.status_code == 422
    assert "Permission must be one of: ['read', 'write']" in response.content.decode()
    assert DocumentCollaborator.objects.get(document=ctx["document"], user=ctx["reader"]).permission == "read"
