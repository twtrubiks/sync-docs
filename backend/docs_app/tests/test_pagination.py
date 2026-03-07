"""
分頁功能測試

測試文檔列表、版本列表、評論列表的分頁行為
"""
import pytest
from django.test import Client
from ninja_jwt.tokens import AccessToken

from docs_app.models import Document, DocumentVersion, Comment


pytestmark = pytest.mark.django_db


# ===== Fixtures =====

@pytest.fixture
def auth_client(test_user):
    """已認證的測試客戶端"""
    token = AccessToken.for_user(test_user)
    client = Client()
    client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    return client


@pytest.fixture
def many_documents(test_user):
    """建立 25 個文檔"""
    docs = []
    for i in range(25):
        doc = Document.objects.create(
            owner=test_user,
            title=f"Document {i+1:02d}",
            content={"ops": [{"insert": f"Content {i+1}\n"}]}
        )
        docs.append(doc)
    return docs


@pytest.fixture
def many_versions(test_document, test_user):
    """建立 25 個版本"""
    versions = []
    for i in range(25):
        test_document.content = {"ops": [{"insert": f"Version {i+1}\n"}]}
        test_document.save()
        v = DocumentVersion.create_version(test_document, test_user)
        versions.append(v)
    return versions


@pytest.fixture
def many_comments(test_document, test_user):
    """建立 25 個頂層評論"""
    comments = []
    for i in range(25):
        c = Comment.objects.create(
            document=test_document,
            author=test_user,
            content=f"Comment {i+1:02d}"
        )
        comments.append(c)
    return comments


# ===== 文檔列表分頁測試 =====

class TestDocumentListPagination:
    """文檔列表分頁測試"""

    def test_default_pagination(self, auth_client, many_documents):
        """測試預設分頁（page=1, page_size=20）"""
        response = auth_client.get('/api/documents/')
        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 25
        assert len(data['items']) == 20
        assert data['page'] == 1
        assert data['page_size'] == 20
        assert data['total_pages'] == 2

    def test_second_page(self, auth_client, many_documents):
        """測試第二頁"""
        response = auth_client.get('/api/documents/?page=2')
        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 25
        assert len(data['items']) == 5  # 剩餘 5 筆
        assert data['page'] == 2

    def test_custom_page_size(self, auth_client, many_documents):
        """測試自訂每頁筆數"""
        response = auth_client.get('/api/documents/?page_size=10')
        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 25
        assert len(data['items']) == 10
        assert data['page_size'] == 10
        assert data['total_pages'] == 3

    def test_page_size_capped_at_max(self, auth_client, many_documents):
        """測試 page_size 超過上限會被限制"""
        response = auth_client.get('/api/documents/?page_size=200')
        assert response.status_code == 200
        data = response.json()

        assert data['page_size'] == 100  # MAX_PAGE_SIZE

    def test_page_beyond_range_returns_last_page(self, auth_client, many_documents):
        """測試超出範圍的頁碼回傳最後一頁"""
        response = auth_client.get('/api/documents/?page=999')
        assert response.status_code == 200
        data = response.json()

        # Django Paginator.get_page() 會回傳最後一頁
        assert data['page'] == data['total_pages']

    def test_negative_page_returns_first_page(self, auth_client, many_documents):
        """測試負數頁碼回傳第一頁"""
        response = auth_client.get('/api/documents/?page=-1')
        assert response.status_code == 200
        data = response.json()

        assert data['page'] == 1

    def test_empty_list_pagination(self, auth_client):
        """測試空列表的分頁"""
        response = auth_client.get('/api/documents/')
        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 0
        assert data['items'] == []
        assert data['page'] == 1
        assert data['total_pages'] == 1

    def test_permission_fields_in_paginated_response(self, auth_client, many_documents):
        """測試分頁回應中包含權限欄位"""
        response = auth_client.get('/api/documents/?page_size=5')
        assert response.status_code == 200
        data = response.json()

        for item in data['items']:
            assert 'is_owner' in item
            assert 'permission' in item
            assert 'can_write' in item
            assert item['is_owner'] is True


# ===== 版本列表分頁測試 =====

class TestVersionListPagination:
    """版本列表分頁測試"""

    def test_default_pagination(self, auth_client, test_document, many_versions):
        """測試預設分頁"""
        response = auth_client.get(f'/api/documents/{test_document.id}/versions/')
        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 25
        assert len(data['items']) == 20
        assert data['page'] == 1
        assert data['total_pages'] == 2

    def test_second_page(self, auth_client, test_document, many_versions):
        """測試版本列表第二頁"""
        response = auth_client.get(f'/api/documents/{test_document.id}/versions/?page=2')
        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 25
        assert len(data['items']) == 5
        assert data['page'] == 2

    def test_versions_ordered_descending(self, auth_client, test_document, many_versions):
        """測試版本按版本號降序排列"""
        response = auth_client.get(f'/api/documents/{test_document.id}/versions/?page_size=5')
        assert response.status_code == 200
        data = response.json()

        version_numbers = [v['version_number'] for v in data['items']]
        assert version_numbers == sorted(version_numbers, reverse=True)

    def test_custom_page_size(self, auth_client, test_document, many_versions):
        """測試自訂每頁筆數"""
        response = auth_client.get(f'/api/documents/{test_document.id}/versions/?page_size=10')
        assert response.status_code == 200
        data = response.json()

        assert len(data['items']) == 10
        assert data['page_size'] == 10
        assert data['total_pages'] == 3


# ===== 評論列表分頁測試 =====

class TestCommentListPagination:
    """評論列表分頁測試"""

    def test_default_pagination(self, auth_client, test_document, many_comments):
        """測試預設分頁"""
        response = auth_client.get(f'/api/documents/{test_document.id}/comments/')
        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 25
        assert len(data['comments']) == 20
        assert data['page'] == 1
        assert data['page_size'] == 20
        assert data['total_pages'] == 2

    def test_second_page(self, auth_client, test_document, many_comments):
        """測試評論列表第二頁"""
        response = auth_client.get(f'/api/documents/{test_document.id}/comments/?page=2')
        assert response.status_code == 200
        data = response.json()

        assert data['total'] == 25
        assert len(data['comments']) == 5
        assert data['page'] == 2

    def test_custom_page_size(self, auth_client, test_document, many_comments):
        """測試自訂每頁筆數"""
        response = auth_client.get(f'/api/documents/{test_document.id}/comments/?page_size=10')
        assert response.status_code == 200
        data = response.json()

        assert len(data['comments']) == 10
        assert data['page_size'] == 10
        assert data['total_pages'] == 3

    def test_replies_not_in_top_level_pagination(self, auth_client, test_document, test_user):
        """測試回覆不會出現在頂層評論的分頁中"""
        parent = Comment.objects.create(
            document=test_document, author=test_user, content="Parent"
        )
        Comment.objects.create(
            document=test_document, author=test_user, content="Reply", parent=parent
        )

        response = auth_client.get(f'/api/documents/{test_document.id}/comments/')
        assert response.status_code == 200
        data = response.json()

        # 只有頂層評論
        assert data['total'] == 1
        assert data['comments'][0]['content'] == "Parent"

    def test_page_size_capped_at_max(self, auth_client, test_document, many_comments):
        """測試 page_size 超過上限會被限制"""
        response = auth_client.get(f'/api/documents/{test_document.id}/comments/?page_size=200')
        assert response.status_code == 200
        data = response.json()

        assert data['page_size'] == 100  # MAX_PAGE_SIZE
