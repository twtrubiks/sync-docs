"""
測試配置檔案
提供共用的測試fixtures和配置
"""

import pytest
from django.contrib.auth.models import User
from docs_app.models import Document


@pytest.fixture
def test_user():
    """創建測試用戶的fixture"""
    return User.objects.create_user(
        username="testuser",
        password="testpassword123",
        email="test@example.com"
    )


@pytest.fixture
def another_user():
    """創建另一個測試用戶的fixture"""
    return User.objects.create_user(
        username="anotheruser",
        password="testpassword123",
        email="another@example.com"
    )


@pytest.fixture
def test_document(test_user):
    """創建測試文檔的fixture"""
    return Document.objects.create(
        title="Test Document",
        content={"type": "doc", "content": []},
        owner=test_user
    )


@pytest.fixture
def shared_document(test_user, another_user):
    """創建共享文檔的fixture"""
    doc = Document.objects.create(
        title="Shared Document",
        content={"type": "doc", "content": []},
        owner=test_user
    )
    doc.shared_with.add(another_user)
    return doc
