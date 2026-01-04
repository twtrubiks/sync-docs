from django.contrib import admin
from .models import Document, DocumentCollaborator


class DocumentCollaboratorInline(admin.TabularInline):
    """協作者內聯編輯"""
    model = DocumentCollaborator
    extra = 1
    raw_id_fields = ['user']
    readonly_fields = ['created_at']


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """文檔管理"""
    list_display = ['title', 'owner', 'get_collaborators_count', 'created_at', 'updated_at']
    list_filter = ['created_at', 'owner']
    search_fields = ['title', 'owner__username']
    readonly_fields = ['id', 'created_at', 'updated_at']
    inlines = [DocumentCollaboratorInline]

    def get_collaborators_count(self, obj):
        return obj.collaborators.count()
    get_collaborators_count.short_description = '協作者數量'


@admin.register(DocumentCollaborator)
class DocumentCollaboratorAdmin(admin.ModelAdmin):
    """協作者管理"""
    list_display = ['document', 'user', 'permission', 'created_at']
    list_filter = ['permission', 'created_at']
    search_fields = ['document__title', 'user__username']
    raw_id_fields = ['document', 'user']
    readonly_fields = ['created_at']
