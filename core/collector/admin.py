from django.contrib import admin

from .models import (
    CommunicationChannelConfig,
    ComponentSystemPermissionGrant,
    ComponentSystemParamConfig,
    Project,
    RequirementMessage,
    RequirementSession,
    SystemRuntimeSetting,
)


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


@admin.register(CommunicationChannelConfig)
class CommunicationChannelConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "provider", "name", "display_name", "is_enabled", "updated_at")
    search_fields = ("name", "display_name", "description")
    list_filter = ("provider", "is_enabled", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ComponentSystemParamConfig)
class ComponentSystemParamConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "module_name", "component_key", "config_name", "is_enabled", "updated_at")
    search_fields = ("module_name", "component_key", "config_name", "display_name", "description")
    list_filter = ("module_name", "is_enabled", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ComponentSystemPermissionGrant)
class ComponentSystemPermissionGrantAdmin(admin.ModelAdmin):
    list_display = ("id", "module_name", "component_key", "permission_key", "is_granted", "updated_at")
    search_fields = ("module_name", "component_key", "permission_key", "permission_name", "grant_note")
    list_filter = ("module_name", "is_granted", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SystemRuntimeSetting)
class SystemRuntimeSettingAdmin(admin.ModelAdmin):
    list_display = ("id", "key", "value_text", "updated_at")
    search_fields = ("key", "value_text", "description")
    list_filter = ("updated_at",)
    readonly_fields = ("created_at", "updated_at")
