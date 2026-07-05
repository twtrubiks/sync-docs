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
    assert response.status_code == 201
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
    assert response1.status_code == 201

    # 2. 嘗試用相同用戶名再次註冊
    response2 = client.post(
        "/api/auth/register",
        data=json.dumps(user_data),
        content_type="application/json"
    )
    assert response2.status_code == 400

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

    response = client.post(
        "/api/auth/register",
        data=json.dumps(weak_password_data),
        content_type="application/json"
    )
    assert response.status_code == 400

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

    response = client.post(
        "/api/auth/register",
        data=json.dumps(common_password_data),
        content_type="application/json"
    )

    if response.status_code == 201:
        # 密碼驗證通過，註冊成功
        assert User.objects.count() == 1
    else:
        # 密碼驗證失敗（常見密碼被拒絕）
        assert response.status_code == 400
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


@pytest.mark.django_db
def test_user_registration_with_email(client):
    """
    測試註冊時可以帶入 email。
    """
    user_data_with_email = {
        "username": "emailuser",
        "password": "a-very-strong-password123",
        "email": "user@example.com"
    }

    response = client.post(
        "/api/auth/register",
        data=json.dumps(user_data_with_email),
        content_type="application/json"
    )

    assert response.status_code == 201
    response_data = response.json()
    assert response_data["username"] == "emailuser"
    assert response_data["email"] == "user@example.com"

    # 驗證資料庫中的 email
    created_user = User.objects.get(username="emailuser")
    assert created_user.email == "user@example.com"


@pytest.mark.django_db
def test_user_registration_without_email(client, user_data):
    """
    測試註冊時不帶 email 仍然成功（向後相容）。
    """
    response = client.post(
        "/api/auth/register",
        data=json.dumps(user_data),  # 只有 username 和 password
        content_type="application/json"
    )

    assert response.status_code == 201
    response_data = response.json()
    assert response_data["username"] == user_data["username"]
    # email 應該是 None 或空字串
    assert response_data["email"] in [None, ""]


# ===== 登出黑名單與 refresh token 輪換 =====

def login(client, user_data):
    """輔助函數：登入並回傳 tokens dict"""
    User.objects.create_user(username=user_data["username"], password=user_data["password"])
    response = client.post(
        "/api/token/pair",
        data=json.dumps({"username": user_data["username"], "password": user_data["password"]}),
        content_type="application/json"
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.django_db
def test_logout_blacklists_refresh_token(client, user_data):
    """
    測試登出後 refresh token 被加入黑名單，無法再換發 access token。
    """
    tokens = login(client, user_data)

    # 登出（不需要 access token 認證，refresh token 本身證明身分）
    response = client.post(
        "/api/auth/logout",
        data=json.dumps({"refresh": tokens["refresh"]}),
        content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True

    # 已列入黑名單的 refresh token 無法再刷新
    response = client.post(
        "/api/token/refresh",
        data=json.dumps({"refresh": tokens["refresh"]}),
        content_type="application/json"
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_logout_with_invalid_refresh_token_is_idempotent(client):
    """
    測試用無效 refresh token 登出仍回 200（登出為冪等操作）。
    """
    response = client.post(
        "/api/auth/logout",
        data=json.dumps({"refresh": "invalid_refresh_token"}),
        content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.django_db
def test_token_refresh_rotates_and_blacklists_old_token(client, user_data):
    """
    測試 refresh 時輪換 refresh token：回傳新的 refresh token，
    舊的 refresh token 立即失效（BLACKLIST_AFTER_ROTATION）。
    """
    tokens = login(client, user_data)
    old_refresh = tokens["refresh"]

    # 第一次 refresh：取得新的 access + 新的 refresh
    response = client.post(
        "/api/token/refresh",
        data=json.dumps({"refresh": old_refresh}),
        content_type="application/json"
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert "access" in new_tokens
    assert new_tokens["refresh"] != old_refresh

    # 舊 refresh token 已被輪換進黑名單，再用即失敗
    response = client.post(
        "/api/token/refresh",
        data=json.dumps({"refresh": old_refresh}),
        content_type="application/json"
    )
    assert response.status_code == 401

    # 新 refresh token 可以正常使用
    response = client.post(
        "/api/token/refresh",
        data=json.dumps({"refresh": new_tokens["refresh"]}),
        content_type="application/json"
    )
    assert response.status_code == 200


# ===== 登入/註冊限流 =====

@pytest.mark.django_db
def test_login_rate_limited_returns_429(client, settings, monkeypatch):
    """
    測試登入限流：限流器拒絕時回 429（throttle 在密碼驗證前執行）。
    """
    settings.AUTH_RATE_LIMIT_ENABLED = True
    monkeypatch.setattr(
        "docs_app.throttling.ai_rate_limiter.is_allowed",
        lambda key, max_requests, window_seconds: False
    )

    response = client.post(
        "/api/token/pair",
        data=json.dumps({"username": "any", "password": "any"}),
        content_type="application/json"
    )
    assert response.status_code == 429


@pytest.mark.django_db
def test_register_rate_limited_returns_429(client, settings, monkeypatch):
    """
    測試註冊限流：限流器拒絕時回 429。
    """
    settings.AUTH_RATE_LIMIT_ENABLED = True
    monkeypatch.setattr(
        "docs_app.throttling.ai_rate_limiter.is_allowed",
        lambda key, max_requests, window_seconds: False
    )

    response = client.post(
        "/api/auth/register",
        data=json.dumps({"username": "newuser", "password": "a-very-strong-password123"}),
        content_type="application/json"
    )
    assert response.status_code == 429
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_login_rate_limit_uses_ip_scoped_key(client, settings, monkeypatch, user_data):
    """
    測試登入限流以 login:{ip} 為 key 計數，允許時登入正常。
    """
    settings.AUTH_RATE_LIMIT_ENABLED = True
    recorded_keys = []

    def fake_is_allowed(key, max_requests, window_seconds):
        recorded_keys.append(key)
        return True

    monkeypatch.setattr("docs_app.throttling.ai_rate_limiter.is_allowed", fake_is_allowed)

    tokens = login(client, user_data)
    assert "access" in tokens
    assert recorded_keys == ["login:127.0.0.1"]
