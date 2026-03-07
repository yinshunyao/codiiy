from django.contrib import admin

from .models import Project, RequirementMessage, RequirementSession


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "path", "is_default", "created_by", "created_at", "updated_at")
    search_fields = ("name", "path", "description", "created_by__username")
    list_filter = ("is_default", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(RequirementSession)
class RequirementSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "project", "created_by", "created_at", "updated_at")
    search_fields = ("title", "content", "created_by__username", "project__name")
    list_filter = ("created_at", "updated_at", "project")


@admin.register(RequirementMessage)
class RequirementMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "role", "created_at")
    search_fields = ("session__title", "content")
    list_filter = ("role", "created_at")
