import json
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()

# 測試資料常數
TEST_USERNAME = "testuser"
TEST_PASSWORD = "a-very-strong-password123"
WRONG_PASSWORD = "wrongpassword"

@pytest.fixture
def user_data():
    """提供標準測試使用者資料"""
    return {
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD
    }

@pytest.mark.django_db
def test_user_registration(client, user_data):
    """
    測試新使用者能否成功註冊。
    """
    response = client.post(
        "/api/auth/register",
        data=json.dumps(user_data),
        content_type="application/json"
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["username"] == user_data["username"]
    assert "password" not in response_data

    assert User.objects.count() == 1
    created_user = User.objects.first()
    assert created_user.username == user_data["username"]
    assert created_user.check_password(user_data["password"])

@pytest.mark.django_db
def test_user_login(client, user_data):
    """
    測試已註冊使用者能否用正確憑證登入並取得 Token。
    """
    # 1. 先註冊使用者
    User.objects.create_user(username=user_data["username"], password=user_data["password"])

    # 2. 嘗試登入
    login_data = {
        "username": user_data["username"],
        "password": user_data["password"]
    }
    response = client.post(
        "/api/token/pair",
        data=json.dumps(login_data),
        content_type="application/json"
    )
    assert response.status_code == 200
    response_data = response.json()
    assert "access" in response_data
    assert "refresh" in response_data

@pytest.mark.django_db
def test_user_login_fails_with_wrong_password(client, user_data):
    """
    測試錯誤密碼無法登入。
    """
    # 1. 先註冊使用者
    User.objects.create_user(username=user_data["username"], password=user_data["password"])

    # 2. 嘗試用錯誤密碼登入
    login_data = {
        "username": user_data["username"],
        "password": WRONG_PASSWORD
    }
    response = client.post(
        "/api/token/pair",
        data=json.dumps(login_data),
        content_type="application/json"
    )
    assert response.status_code == 401  # Unauthorized

@pytest.mark.django_db
def test_authenticated_user_can_access_protected_route(client, user_data):
    """
    測試 Token 能否成功驗證並存取受保護的 API。
    """
    # 1. 註冊並登入以獲取 token
    User.objects.create_user(username=user_data["username"], password=user_data["password"])
    login_data = {
        "username": user_data["username"],
        "password": user_data["password"]
    }
    response = client.post(
        "/api/token/pair",
        data=json.dumps(login_data),
        content_type="application/json"
    )
    token = response.json()["access"]

    # 2. 使用 token 存取受保護的路由 (修正：使用 HTTP_AUTHORIZATION 而非 headers)
    response = client.get(
        "/api/auth/me",
        HTTP_AUTHORIZATION=f"Bearer {token}"
    )

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["username"] == user_data["username"]


@pytest.mark.django_db
def test_user_registration_with_duplicate_username(client, user_data):
    """
    測試重複用戶名註冊失敗。
    """
    # 1. 先註冊一個用戶
    response1 = client.post(
        "/api/auth/register",
        data=json.dumps(user_data),
        content_type="application/json"
    )
    assert response1.status_code == 200

    # 2. 嘗試用相同用戶名再次註冊
    with pytest.raises(Exception):  # ValidationError會導致異常
        client.post(
            "/api/auth/register",
            data=json.dumps(user_data),
            content_type="application/json"
        )

    # 確保只有一個用戶被創建
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_user_registration_with_weak_password(client):
    """
    測試弱密碼註冊失敗。
    """
    weak_password_data = {
        "username": "testuser",
        "password": "123"  # 太短的密碼
    }

    with pytest.raises(Exception):  # ValidationError會導致異常
        client.post(
            "/api/auth/register",
            data=json.dumps(weak_password_data),
            content_type="application/json"
        )

    # 確保用戶沒有被創建
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_user_registration_with_common_password(client):
    """
    測試常見密碼註冊可能失敗。
    """
    common_password_data = {
        "username": "testuser",
        "password": "password123"  # 常見密碼
    }

    try:
        response = client.post(
            "/api/auth/register",
            data=json.dumps(common_password_data),
            content_type="application/json"
        )
        # 如果沒有拋出異常，則註冊成功
        assert response.status_code == 200
        assert User.objects.count() == 1
    except Exception:
        # 如果拋出異常，則密碼驗證失敗
        assert User.objects.count() == 0


@pytest.mark.django_db
def test_user_login_with_nonexistent_user(client):
    """
    測試不存在的用戶無法登入。
    """
    login_data = {
        "username": "nonexistent",
        "password": "somepassword"
    }
    response = client.post(
        "/api/token/pair",
        data=json.dumps(login_data),
        content_type="application/json"
    )
    assert response.status_code == 401  # Unauthorized


@pytest.mark.django_db
def test_access_protected_route_without_token(client):
    """
    測試沒有token無法存取受保護的路由。
    """
    response = client.get("/api/auth/me")
    assert response.status_code == 401  # Unauthorized


@pytest.mark.django_db
def test_access_protected_route_with_invalid_token(client):
    """
    測試無效token無法存取受保護的路由。
    """
    response = client.get(
        "/api/auth/me",
        HTTP_AUTHORIZATION="Bearer invalid_token"
    )
    assert response.status_code == 401  # Unauthorized


@pytest.mark.django_db
def test_token_refresh(client, user_data):
    """
    測試token刷新功能。
    """
    # 1. 註冊並登入以獲取 tokens
    User.objects.create_user(username=user_data["username"], password=user_data["password"])
    login_data = {
        "username": user_data["username"],
        "password": user_data["password"]
    }
    response = client.post(
        "/api/token/pair",
        data=json.dumps(login_data),
        content_type="application/json"
    )
    tokens = response.json()
    refresh_token = tokens["refresh"]

    # 2. 使用refresh token獲取新的access token
    refresh_data = {"refresh": refresh_token}
    response = client.post(
        "/api/token/refresh",
        data=json.dumps(refresh_data),
        content_type="application/json"
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert "access" in new_tokens


@pytest.mark.django_db
def test_token_refresh_with_invalid_token(client):
    """
    測試無效refresh token無法刷新。
    """
    refresh_data = {"refresh": "invalid_refresh_token"}
    response = client.post(
        "/api/token/refresh",
        data=json.dumps(refresh_data),
        content_type="application/json"
    )
    assert response.status_code == 401  # Unauthorized


@pytest.mark.django_db
def test_user_registration_missing_fields(client):
    """
    測試缺少必要字段的註冊請求。
    """
    # 缺少密碼
    incomplete_data = {"username": "testuser"}
    response = client.post(
        "/api/auth/register",
        data=json.dumps(incomplete_data),
        content_type="application/json"
    )
    assert response.status_code == 422  # Pydantic驗證錯誤

    # 缺少用戶名
    incomplete_data = {"password": "testpassword"}
    response = client.post(
        "/api/auth/register",
        data=json.dumps(incomplete_data),
        content_type="application/json"
    )
    assert response.status_code == 422  # Pydantic驗證錯誤


@pytest.mark.django_db
def test_user_login_missing_fields(client):
    """
    測試缺少必要字段的登入請求。
    """
    # 缺少密碼
    incomplete_data = {"username": "testuser"}
    response = client.post(
        "/api/token/pair",
        data=json.dumps(incomplete_data),
        content_type="application/json"
    )
    assert response.status_code == 400  # Bad Request

    # 缺少用戶名
    incomplete_data = {"password": "testpassword"}
    response = client.post(
        "/api/token/pair",
        data=json.dumps(incomplete_data),
        content_type="application/json"
    )
    assert response.status_code == 400  # Bad Request
