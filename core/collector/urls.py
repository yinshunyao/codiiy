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
    path("sessions/<int:session_id>/send-async/", views.session_send_async, name="session_send_async"),
    path(
        "sessions/<int:session_id>/reply-task/<int:task_id>/status/",
        views.chat_reply_task_status,
        name="chat_reply_task_status",
    ),
    path(
        "sessions/<int:session_id>/reply-task/<int:task_id>/stop/",
        views.chat_reply_task_stop,
        name="chat_reply_task_stop",
    ),
    path(
        "sessions/<int:session_id>/reply-task/<int:task_id>/interaction-submit/",
        views.chat_reply_task_interaction_submit,
        name="chat_reply_task_interaction_submit",
    ),
    path(
        "sessions/<int:session_id>/extract-summary/<int:message_id>/",
        views.session_extract_summary,
        name="session_extract_summary",
    ),
    path(
        "sessions/<int:session_id>/messages/<int:message_id>/delete/",
        views.session_message_delete,
        name="session_message_delete",
    ),
    path("sessions/<int:session_id>/rollback/<int:message_id>/", views.session_rollback, name="session_rollback"),
    path("sessions/<int:session_id>/delete/", views.session_delete, name="session_delete"),
    path("companions/", views.companion_list, name="companion_list"),
    path("companions/new/", views.companion_create, name="companion_create"),
    path("companions/<int:companion_id>/edit/", views.companion_edit, name="companion_edit"),
    path("companions/<int:companion_id>/chat/", views.companion_chat, name="companion_chat"),
    # 项目管理相关
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:project_id>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:project_id>/delete/", views.project_delete, name="project_delete"),
    path("projects/<int:project_id>/switch/", views.project_switch, name="project_switch"),
    path("projects/<int:project_id>/set_default/", views.project_set_default, name="project_set_default"),
    path("settings/profile/", views.profile_settings, name="profile_settings"),
    path("settings/system/", views.system_settings, name="system_settings"),
    path("models/api/", views.llm_api_config_list, name="llm_api_config_list"),
    path("models/api/new/", views.llm_api_config_create, name="llm_api_config_create"),
    path("models/api/<int:config_id>/edit/", views.llm_api_config_edit, name="llm_api_config_edit"),
    path("models/api/<int:config_id>/delete/", views.llm_api_config_delete, name="llm_api_config_delete"),
    path("models/local/", views.local_llm_config_list, name="local_llm_config_list"),
    path("models/local/runtime-status/", views.local_llm_runtime_status, name="local_llm_runtime_status"),
    path("models/local/new/", views.local_llm_config_create, name="local_llm_config_create"),
    path("models/local/<int:config_id>/edit/", views.local_llm_config_edit, name="local_llm_config_edit"),
    path("models/local/<int:config_id>/delete/", views.local_llm_config_delete, name="local_llm_config_delete"),
    path("models/local/<int:config_id>/runtime/", views.local_llm_runtime_action, name="local_llm_runtime_action"),
    path("search/", views.capability_search, name="capability_search"),
    path("tools/sets/", views.toolset_list, name="toolset_list"),
    path("agents/<str:module_name>/", views.agent_item_list, name="agent_item_list"),
    path(
        "agents/<str:module_name>/upload/",
        views.agent_item_upload,
        name="agent_item_upload",
    ),
    path(
        "agents/<str:module_name>/<str:item_name>/download/",
        views.agent_item_download,
        name="agent_item_download",
    ),
    path(
        "agents/<str:module_name>/<str:item_name>/delete/",
        views.agent_item_delete,
        name="agent_item_delete",
    ),
    path("system/skills/", views.system_skill_list, name="system_skill_list"),
    path("system/skills/upload/", views.system_skill_upload, name="system_skill_upload"),
    path("system/skills/<str:skill_name>/download/", views.system_skill_download, name="system_skill_download"),
    path("system/rules/", views.system_rule_list, name="system_rule_list"),
    path("system/rules/detail/", views.system_rule_detail, name="system_rule_detail"),
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
        "component/functions/<str:module_name>/<str:component_key>/delete/",
        views.control_component_delete,
        name="control_component_delete",
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
    path(
        "api/companions/<int:companion_id>/set-mindforge-strategy/",
        views.companion_set_mindforge_strategy,
        name="companion_set_mindforge_strategy",
    ),
]
