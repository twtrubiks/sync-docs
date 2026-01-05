"""
版本歷史功能測試
測試 DocumentVersion 模型和版本 API 端點
"""

import uuid
import pytest
from ninja_jwt.tokens import AccessToken
from docs_app.models import DocumentVersion, DocumentCollaborator, PermissionLevel


# ===== 版本相關 Fixtures =====

@pytest.fixture
def test_version(test_document, test_user):
    """創建測試版本"""
    return DocumentVersion.create_version(test_document, test_user)


@pytest.fixture
def auth_client(client, test_user):
    """已認證的測試客戶端"""
    token = AccessToken.for_user(test_user)
    client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    return client


@pytest.fixture
def read_only_collaborator(test_document, another_user):
    """只讀權限的協作者"""
    DocumentCollaborator.objects.create(
        document=test_document,
        user=another_user,
        permission=PermissionLevel.READ
    )
    return another_user


@pytest.fixture
def readonly_auth_client(client, read_only_collaborator):
    """只讀權限的測試客戶端"""
    token = AccessToken.for_user(read_only_collaborator)
    client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    return client


@pytest.fixture
def another_auth_client(client, another_user):
    """另一個用戶的測試客戶端（無權限）"""
    token = AccessToken.for_user(another_user)
    client.defaults['HTTP_AUTHORIZATION'] = f'Bearer {token}'
    return client


# ===== DocumentVersion 模型測試 =====

@pytest.mark.django_db
class TestDocumentVersionModel:
    """DocumentVersion 模型測試"""

    def test_create_version(self, test_user, test_document):
        """測試創建版本"""
        version = DocumentVersion.create_version(test_document, test_user)
        assert version.version_number == 1
        assert version.content == test_document.content
        assert version.created_by == test_user

    def test_version_number_increment(self, test_user, test_document):
        """測試版本號遞增"""
        v1 = DocumentVersion.create_version(test_document, test_user)
        v2 = DocumentVersion.create_version(test_document, test_user)
        assert v1.version_number == 1
        assert v2.version_number == 2

    def test_cleanup_old_versions(self, test_user, test_document):
        """測試清理舊版本"""
        for _ in range(60):
            DocumentVersion.create_version(test_document, test_user)

        DocumentVersion.cleanup_old_versions(test_document, keep_count=50)
        assert DocumentVersion.objects.filter(document=test_document).count() == 50

    def test_cleanup_keeps_newest(self, test_user, test_document):
        """測試清理保留最新版本"""
        for _ in range(60):
            DocumentVersion.create_version(test_document, test_user)

        DocumentVersion.cleanup_old_versions(test_document, keep_count=50)
        remaining = DocumentVersion.objects.filter(document=test_document)
        version_numbers = list(remaining.values_list('version_number', flat=True))
        # 應該保留 11-60（最新的 50 個）
        assert min(version_numbers) == 11
        assert max(version_numbers) == 60

    def test_created_by_username_property(self, test_user, test_document):
        """測試 created_by_username 屬性"""
        version = DocumentVersion.create_version(test_document, test_user)
        assert version.created_by_username == test_user.username

    def test_created_by_username_when_null(self, test_document):
        """測試當 created_by 為空時的 username"""
        version = DocumentVersion.objects.create(
            document=test_document,
            content=test_document.content,
            created_by=None,
            version_number=1
        )
        assert version.created_by_username is None

    def test_str_representation(self, test_user, test_document):
        """測試字符串表示"""
        version = DocumentVersion.create_version(test_document, test_user)
        expected = f"{test_document.title} - v{version.version_number}"
        assert str(version) == expected


# ===== 版本 API 端點測試 =====

@pytest.mark.django_db
class TestVersionAPI:
    """版本 API 端點測試"""

    def test_list_versions(self, auth_client, test_document, test_version):
        """測試列出版本"""
        response = auth_client.get(f'/api/documents/{test_document.id}/versions/')
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]['version_number'] == 1

    def test_list_versions_empty(self, auth_client, test_document):
        """測試列出空版本列表"""
        response = auth_client.get(f'/api/documents/{test_document.id}/versions/')
        assert response.status_code == 200
        assert response.json() == []

    def test_list_versions_order(self, auth_client, test_document, test_user):
        """測試版本列表按版本號降序排列"""
        for i in range(5):
            DocumentVersion.create_version(test_document, test_user)

        response = auth_client.get(f'/api/documents/{test_document.id}/versions/')
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5
        # 確認是降序
        version_numbers = [v['version_number'] for v in data]
        assert version_numbers == [5, 4, 3, 2, 1]

    def test_get_version_detail(self, auth_client, test_document, test_version):
        """測試獲取版本詳情"""
        response = auth_client.get(
            f'/api/documents/{test_document.id}/versions/{test_version.id}/'
        )
        assert response.status_code == 200
        data = response.json()
        assert 'content' in data
        assert data['version_number'] == 1

    def test_get_version_not_found(self, auth_client, test_document):
        """測試獲取不存在的版本"""
        fake_id = uuid.uuid4()
        response = auth_client.get(
            f'/api/documents/{test_document.id}/versions/{fake_id}/'
        )
        assert response.status_code == 404

    def test_restore_version(self, auth_client, test_document, test_version):
        """測試還原版本"""
        # 修改文件內容
        original_content = test_document.content.copy()
        test_document.content = {'ops': [{'insert': 'Modified content\n'}]}
        test_document.save()

        # 還原到舊版本
        response = auth_client.post(
            f'/api/documents/{test_document.id}/versions/{test_version.id}/restore/'
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

        # 驗證文件內容已還原
        test_document.refresh_from_db()
        assert test_document.content == original_content

    def test_restore_creates_new_version(self, auth_client, test_document, test_version):
        """測試還原會創建新版本"""
        initial_count = DocumentVersion.objects.filter(document=test_document).count()
        auth_client.post(
            f'/api/documents/{test_document.id}/versions/{test_version.id}/restore/'
        )
        new_count = DocumentVersion.objects.filter(document=test_document).count()
        assert new_count == initial_count + 1

    def test_restore_returns_new_version_number(self, auth_client, test_document, test_version):
        """測試還原返回新版本號"""
        response = auth_client.post(
            f'/api/documents/{test_document.id}/versions/{test_version.id}/restore/'
        )
        assert response.status_code == 200
        data = response.json()
        assert data['new_version_number'] == 2

    def test_readonly_user_cannot_restore(self, readonly_auth_client, test_document, test_version):
        """測試只讀用戶無法還原"""
        response = readonly_auth_client.post(
            f'/api/documents/{test_document.id}/versions/{test_version.id}/restore/'
        )
        assert response.status_code == 403

    def test_readonly_user_can_list_versions(self, readonly_auth_client, test_document, test_version):
        """測試只讀用戶可以查看版本列表"""
        response = readonly_auth_client.get(
            f'/api/documents/{test_document.id}/versions/'
        )
        assert response.status_code == 200

    def test_readonly_user_can_view_version_detail(self, readonly_auth_client, test_document, test_version):
        """測試只讀用戶可以查看版本詳情"""
        response = readonly_auth_client.get(
            f'/api/documents/{test_document.id}/versions/{test_version.id}/'
        )
        assert response.status_code == 200

    def test_unauthorized_user_cannot_access(self, client, test_document, test_version):
        """測試未認證用戶無法存取"""
        response = client.get(f'/api/documents/{test_document.id}/versions/')
        assert response.status_code == 401

    def test_non_collaborator_cannot_access(self, another_auth_client, test_document, test_version):
        """測試非協作者無法存取版本列表"""
        response = another_auth_client.get(
            f'/api/documents/{test_document.id}/versions/'
        )
        # 應該返回 404（隱藏文檔存在狀態）
        assert response.status_code == 404


# ===== 文件更新時自動創建版本測試 =====

@pytest.mark.django_db
class TestAutoVersionCreation:
    """測試文件更新時自動創建版本"""

    def test_update_document_creates_version(self, auth_client, test_document):
        """測試更新文件內容會創建版本"""
        initial_count = DocumentVersion.objects.filter(document=test_document).count()

        new_content = {'ops': [{'insert': 'New content\n'}]}
        response = auth_client.put(
            f'/api/documents/{test_document.id}/',
            data={'content': new_content},
            content_type='application/json'
        )
        assert response.status_code == 200

        new_count = DocumentVersion.objects.filter(document=test_document).count()
        assert new_count == initial_count + 1

    def test_update_title_only_no_version(self, auth_client, test_document):
        """測試只更新標題不會創建版本"""
        initial_count = DocumentVersion.objects.filter(document=test_document).count()

        response = auth_client.put(
            f'/api/documents/{test_document.id}/',
            data={'title': 'New Title'},
            content_type='application/json'
        )
        assert response.status_code == 200

        new_count = DocumentVersion.objects.filter(document=test_document).count()
        assert new_count == initial_count  # 沒有變化

    def test_update_same_content_no_version(self, auth_client, test_document):
        """測試更新相同內容不會創建版本"""
        initial_count = DocumentVersion.objects.filter(document=test_document).count()

        # 發送相同的內容
        response = auth_client.put(
            f'/api/documents/{test_document.id}/',
            data={'content': test_document.content},
            content_type='application/json'
        )
        assert response.status_code == 200

        new_count = DocumentVersion.objects.filter(document=test_document).count()
        assert new_count == initial_count  # 沒有變化
