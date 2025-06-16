import pytest
from django.contrib.auth import get_user_model
import json

User = get_user_model()

@pytest.fixture
def user_data():
    return {
        "username": "testuser",
        "password": "a-very-strong-password123"
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
        "password": "wrongpassword"
    }
    response = client.post(
        "/api/token/pair",
        data=json.dumps(login_data),
        content_type="application/json"
    )
    assert response.status_code == 401 # Unauthorized

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

    # 2. 使用 token 存取受保護的路由
    headers = {
        "Authorization": f"Bearer {token}"
    }
    response = client.get("/api/auth/me", headers=headers)

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["username"] == user_data["username"]
