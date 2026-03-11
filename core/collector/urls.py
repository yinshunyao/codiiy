from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    # 会话相关
    path("sessions/", views.session_list, name="session_list"),
    path("requirements/files/", views.requirement_file_list, name="requirement_file_list"),
    path("sessions/new/", views.session_create, name="session_create"),
    path("sessions/<int:session_id>/", views.session_detail, name="session_detail"),
    path("sessions/<int:session_id>/send/", views.session_send, name="session_send"),
    path("sessions/<int:session_id>/rollback/<int:message_id>/", views.session_rollback, name="session_rollback"),
    path("sessions/<int:session_id>/delete/", views.session_delete, name="session_delete"),
    # 项目管理相关
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:project_id>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:project_id>/delete/", views.project_delete, name="project_delete"),
    path("projects/<int:project_id>/switch/", views.project_switch, name="project_switch"),
    path("projects/<int:project_id>/set_default/", views.project_set_default, name="project_set_default"),
    path("settings/profile/", views.profile_settings, name="profile_settings"),
    path("settings/system/", views.system_settings, name="system_settings"),
    # component 功能管理
    path("component/functions/<str:module_name>/", views.control_function_list, name="control_function_list"),
    path(
        "component/functions/<str:module_name>/upload/",
        views.control_function_upload,
        name="control_function_upload",
    ),
    path(
        "component/functions/<str:module_name>/<str:component_key>/download/",
        views.control_function_download,
        name="control_function_download",
    ),
    path(
        "component/functions/<str:module_name>/<str:component_key>/toggle-enabled/",
        views.control_component_toggle_enabled,
        name="control_component_toggle_enabled",
    ),
    path(
        "component/functions/<str:module_name>/test/",
        views.control_function_test,
        name="control_function_test",
    ),
    path(
        "component/functions/test-task/<int:task_id>/status/",
        views.control_function_test_task_status,
        name="control_function_test_task_status",
    ),
    path(
        "component/system-params/<str:module_name>/<str:component_key>/",
        views.component_system_param_config,
        name="component_system_param_config",
    ),

    # API
    path("api/llm-providers/", views.llm_provider_list, name="llm_provider_list"),
    path("api/llm-providers/<int:provider_id>/models/", views.llm_model_list, name="llm_model_list"),
    path("api/projects/<int:project_id>/set-llm/", views.project_set_llm, name="project_set_llm"),
]
