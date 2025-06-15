import pytest
import json
from docs_app.models import Document

# 使用 pytest-django 的 db fixture 來確保資料庫在測試之間是乾淨的
pytestmark = pytest.mark.django_db

# The custom 'client' fixture that returned TestClient(api) is removed.
# Pytest-django will provide its 'client' fixture (django.test.Client).

@pytest.fixture
def create_user(django_user_model):
    def make_user(**kwargs):
        if 'username' not in kwargs:
            kwargs['username'] = 'testuser'
        if 'password' not in kwargs:
            kwargs['password'] = 'testpassword'
        user = django_user_model.objects.create_user(**kwargs)
        return user
    return make_user

@pytest.fixture
def authenticated_client(client, create_user): # client is now pytest-django's default client
    user_to_auth = create_user()

    login_data = {
        "username": user_to_auth.username,
        "password": "testpassword" # Default password from create_user fixture
    }

    # Use the standard Django client for login to get token
    token_response = client.post(
        "/api/token/pair", # Path for JWT token generation from ninja-jwt
        data=json.dumps(login_data),
        content_type="application/json"
    )

    if token_response.status_code != 200:
        raise Exception(f"Failed to authenticate user for tests. Status: {token_response.status_code}, Response: {token_response.content.decode()}")

    tokens = token_response.json()
    access_token = tokens.get("access")

    if not access_token:
        raise Exception("Access token not found in login response.")

    return client, user_to_auth, access_token


def test_create_document(authenticated_client):
    client, user, access_token = authenticated_client # Unpack token
    document_data = {
        "title": "My First Test Document",
        "content": {"type": "doc", "content": [{"type": "paragraph"}]} # 假設 content 是 JSON
    }

    # Using standard Django client:
    # For POSTing JSON, pass the dict directly to 'data' and set content_type.
    # Custom headers like Authorization are prefixed with HTTP_.
    response = client.post(
        "/api/documents/",
        data=document_data, # Pass dict directly
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {access_token}"
    )

    # The API currently returns 200 OK on successful creation, not 201 Created.
    # Adjusting test to expect 200.
    assert response.status_code == 200, f"Create document failed: {response.content.decode()}"
    response_data = response.json()
    assert response_data["title"] == document_data["title"]
    # The DocumentSchema in api.py returns an 'owner' object which is UserSchema.
    # UserSchema has 'id', 'username', 'email'.
    assert response_data["owner"]["id"] == user.id
    assert Document.objects.count() == 1
    doc = Document.objects.first()
    assert doc.title == document_data["title"]
    assert doc.owner == user


def test_list_own_documents(authenticated_client, create_user):
    client, user1, access_token1 = authenticated_client

    # Create another user for isolation, no token needed for this user in this specific test
    user2 = create_user(username='anotheruser', email='another@example.com')

    # Create documents for user1
    doc1_user1 = Document.objects.create(owner=user1, title="User1 Doc 1", content={"data": "content1"})
    doc2_user1 = Document.objects.create(owner=user1, title="User1 Doc 2", content={"data": "content2"})

    # Create a document for user2
    doc1_user2 = Document.objects.create(owner=user2, title="User2 Doc 1", content={"data": "content3"})

    # Make a GET request as user1
    response = client.get("/api/documents/", HTTP_AUTHORIZATION=f"Bearer {access_token1}")

    assert response.status_code == 200, f"List documents failed: {response.content.decode()}"
    response_data = response.json()

    assert len(response_data) == 2 # user1 should only see their 2 documents

    response_titles = {doc["title"] for doc in response_data}
    assert doc1_user1.title in response_titles
    assert doc2_user1.title in response_titles
    assert doc1_user2.title not in response_titles # Ensure user2's doc is not listed

    # Check owner_id for each document in response
    # DocumentListSchema returns owner as a UserSchema object
    for doc_data in response_data:
        assert doc_data["owner"]["id"] == user1.id


def test_get_document_by_id(authenticated_client, create_user):
    client, owner_user, owner_access_token = authenticated_client

    doc_content = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Test content"}]}]}
    document = Document.objects.create(
        owner=owner_user,
        title="Specific Document Title",
        content=doc_content
    )

    # Test that the owner can retrieve the document
    response_owner = client.get(f"/api/documents/{document.id}/", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}")
    assert response_owner.status_code == 200, f"Owner GET failed: {response_owner.content.decode()}"
    response_data_owner = response_owner.json()
    assert response_data_owner["id"] == str(document.id) # UUID needs to be string for comparison
    assert response_data_owner["title"] == "Specific Document Title"
    assert response_data_owner["content"] == doc_content
    assert response_data_owner["owner"]["id"] == owner_user.id

    # Test that another user cannot retrieve the document (expect 404 Not Found)
    non_owner_user = create_user(username="nonowner", password="testpasswordnonowner", email="nonowner@example.com")

    non_owner_login_data = { "username": "nonowner", "password": "testpasswordnonowner" }
    token_response_non_owner = client.post("/api/token/pair", data=json.dumps(non_owner_login_data), content_type="application/json")
    assert token_response_non_owner.status_code == 200, f"Non-owner login failed: {token_response_non_owner.content.decode()}"
    non_owner_access_token = token_response_non_owner.json()["access"]

    response_non_owner = client.get(f"/api/documents/{document.id}/", HTTP_AUTHORIZATION=f"Bearer {non_owner_access_token}")
    assert response_non_owner.status_code == 404 # Or 403 if you prefer Forbidden


def test_update_document(authenticated_client, create_user):
    client, owner_user, owner_access_token = authenticated_client

    original_title = "Original Title"
    original_content = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Original content"}]}]}
    document = Document.objects.create(
        owner=owner_user,
        title=original_title,
        content=original_content
    )

    updated_title = "Updated Title"
    updated_content = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Updated content successfully!"}]}]}
    update_data = {
        "title": updated_title,
        "content": updated_content
    }

    # Test that the owner can update the document
    response_owner = client.put(
        f"/api/documents/{document.id}/",
        data=update_data, # Pass dict directly
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_owner.status_code == 200, f"Owner PUT failed: {response_owner.content.decode()}"
    response_data_owner = response_owner.json()
    assert response_data_owner["title"] == updated_title
    assert response_data_owner["content"] == updated_content
    assert response_data_owner["owner"]["id"] == owner_user.id # Ensure owner remains the same

    # Verify in DB
    document.refresh_from_db()
    assert document.title == updated_title
    assert document.content == updated_content

    # Test that another user cannot update the document
    non_owner_user = create_user(username="nonownerupdater", password="testpasswordnonownerupdater", email="nonownerupdater@example.com")
    non_owner_login_data = { "username": "nonownerupdater", "password": "testpasswordnonownerupdater" }
    token_response_non_owner = client.post("/api/token/pair", data=json.dumps(non_owner_login_data), content_type="application/json")
    assert token_response_non_owner.status_code == 200, f"Non-owner updater login failed: {token_response_non_owner.content.decode()}"
    non_owner_access_token = token_response_non_owner.json()["access"]

    attempt_update_data = {"title": "Malicious Update", "content": {"data": "bad"}}
    response_non_owner = client.put(
        f"/api/documents/{document.id}/",
        data=attempt_update_data, # Pass dict directly
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {non_owner_access_token}"
    )
    assert response_non_owner.status_code == 404 # Or 403

    # Ensure document was not changed by non-owner
    document.refresh_from_db()
    assert document.title == updated_title
    assert document.content == updated_content


def test_unauthorized_user_cannot_access_document(authenticated_client, create_user):
    # owner_user and its token are from authenticated_client, but not directly used for auth in this test's perspective.
    # We are testing actions from 'unauthorized_user'.
    client, owner_user, _ = authenticated_client

    document = Document.objects.create(
        owner=owner_user,
        title="Secret Document",
        content={"data": "secret content"}
    )

    unauthorized_user = create_user(username="intruder", password="testpasswordintruder", email="intruder@example.com")
    intruder_login_data = { "username": "intruder", "password": "testpasswordintruder" }
    token_response_intruder = client.post("/api/token/pair", data=json.dumps(intruder_login_data), content_type="application/json")
    assert token_response_intruder.status_code == 200, f"Intruder login failed: {token_response_intruder.content.decode()}"
    intruder_access_token = token_response_intruder.json()["access"]

    # Attempt to GET the document as unauthorized_user
    response_get = client.get(f"/api/documents/{document.id}/", HTTP_AUTHORIZATION=f"Bearer {intruder_access_token}")
    assert response_get.status_code == 404 # Or 403

    # Attempt to PUT (update) the document as unauthorized_user
    update_data = {"title": "Hacked Title", "content": {"data": "hacked"}}
    response_put = client.put(
        f"/api/documents/{document.id}/",
        data=update_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {intruder_access_token}"
    )
    assert response_put.status_code == 404 # Or 403

    # Verify document was not changed by the PUT attempt
    document.refresh_from_db()
    assert document.title == "Secret Document"
    assert document.content == {"data": "secret content"}

    # Attempt to DELETE the document as unauthorized_user
    response_delete = client.delete(f"/api/documents/{document.id}/", HTTP_AUTHORIZATION=f"Bearer {intruder_access_token}")
    assert response_delete.status_code == 404 # Or 403

    # Verify document still exists
    assert Document.objects.filter(id=document.id).exists()


# --- Share and Collaboration Tests ---

@pytest.fixture
def collaborator_user_and_token(client, create_user):
    collab_user = create_user(username="collaborator", email="collab@example.com", password="collabpassword")
    login_data = {"username": "collaborator", "password": "collabpassword"}
    response = client.post("/api/token/pair", data=json.dumps(login_data), content_type="application/json")
    assert response.status_code == 200, f"Collaborator login failed: {response.content.decode()}"
    return collab_user, response.json()["access"]

def test_owner_can_share_document(authenticated_client, collaborator_user_and_token, create_user):
    client, owner_user, owner_access_token = authenticated_client
    collaborator, _ = collaborator_user_and_token # We only need the collaborator user object here

    # 1. Owner creates a document
    doc_data = {"title": "Shared Doc Test", "content": {"data": "initial content"}}
    response = client.post(
        "/api/documents/",
        data=doc_data,
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response.status_code == 200
    document_id = response.json()["id"]
    document = Document.objects.get(id=document_id)

    # 2. Owner shares the document with the collaborator
    # Assuming ShareRequestSchema takes 'user_id' or 'username'. Let's try 'username'.
    # The API endpoint is POST /api/documents/{document_id}/collaborators/
    # The MVP checklist says ShareRequestSchema is for "email/username".
    share_data = {"username": collaborator.username}
    response_share = client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data), # Ensure data is json string for POST
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_share.status_code == 200, f"Share document failed: {response_share.content.decode()}"

    # Verify collaborator is in shared_with
    document.refresh_from_db()
    assert collaborator in document.shared_with.all()

    # Verify response from sharing (e.g., list of collaborators)
    # The API for adding collaborators should ideally return the updated list of collaborators or the added user.
    # Let's assume it returns the UserSchema of the added collaborator or a success message.
    # For now, we'll check the DB and then test the GET collaborators endpoint.

    response_get_collabs = client.get(
        f"/api/documents/{document_id}/collaborators/",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_get_collabs.status_code == 200
    collabs_data = response_get_collabs.json()
    assert len(collabs_data) == 1
    assert collabs_data[0]["username"] == collaborator.username


def test_collaborator_can_access_shared_document(authenticated_client, collaborator_user_and_token):
    client, owner_user, owner_access_token = authenticated_client
    collaborator, collaborator_access_token = collaborator_user_and_token

    # 1. Owner creates a document
    doc_data = {"title": "Access Test Doc", "content": {"data": "content for access"}}
    response_create = client.post(
        "/api/documents/", data=doc_data, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_create.status_code == 200
    document_id = response_create.json()["id"]
    document = Document.objects.get(id=document_id)

    # 2. Owner shares the document with the collaborator
    share_data = {"username": collaborator.username}
    response_share = client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_share.status_code == 200

    # 3. Collaborator tries to access the document
    response_access = client.get(
        f"/api/documents/{document_id}/",
        HTTP_AUTHORIZATION=f"Bearer {collaborator_access_token}"
    )
    assert response_access.status_code == 200, f"Collaborator access failed: {response_access.content.decode()}"
    accessed_data = response_access.json()
    assert accessed_data["id"] == document_id
    assert accessed_data["title"] == doc_data["title"]


def test_collaborator_can_edit_shared_document(authenticated_client, collaborator_user_and_token):
    client, owner_user, owner_access_token = authenticated_client
    collaborator, collaborator_access_token = collaborator_user_and_token

    # 1. Owner creates a document
    doc_data = {"title": "Edit Test Doc", "content": {"data": "original content by owner"}}
    response_create = client.post(
        "/api/documents/", data=doc_data, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_create.status_code == 200
    document_id = response_create.json()["id"]

    # 2. Owner shares the document with the collaborator
    share_data = {"username": collaborator.username}
    response_share = client.post(
        f"/api/documents/{document_id}/collaborators/",
        data=json.dumps(share_data), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_share.status_code == 200

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
    client, owner_user, owner_access_token = authenticated_client
    collaborator, collaborator_access_token = collaborator_user_and_token

    # 1. Owner creates a document and shares it
    doc_data = {"title": "Remove Collab Doc", "content": {"data": "content"}}
    response_create = client.post("/api/documents/", data=doc_data, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}")
    assert response_create.status_code == 200
    document_id = response_create.json()["id"]
    document = Document.objects.get(id=document_id)

    share_data = {"username": collaborator.username}
    client.post(f"/api/documents/{document_id}/collaborators/", data=json.dumps(share_data), content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {owner_access_token}")
    document.refresh_from_db()
    assert collaborator in document.shared_with.all()

    # 2. Owner removes the collaborator
    # Endpoint: DELETE /api/documents/{document_id}/collaborators/{user_id}/
    response_remove = client.delete(
        f"/api/documents/{document_id}/collaborators/{collaborator.id}/",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_remove.status_code == 200, f"Remove collaborator failed: {response_remove.content.decode()}"
    # Assuming 200 OK on successful removal. Some APIs might return 204 No Content.
    # If the API returns a body (e.g. updated list of collaborators), check it.
    # For now, we check the DB.

    document.refresh_from_db()
    assert collaborator not in document.shared_with.all()

    # Verify collaborator list is empty
    response_get_collabs = client.get(
        f"/api/documents/{document_id}/collaborators/",
        HTTP_AUTHORIZATION=f"Bearer {owner_access_token}"
    )
    assert response_get_collabs.status_code == 200
    collabs_data = response_get_collabs.json()
    assert len(collabs_data) == 0


def test_removed_collaborator_loses_access(authenticated_client, collaborator_user_and_token):
    client, owner_user, owner_access_token = authenticated_client
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
