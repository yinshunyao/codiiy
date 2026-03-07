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

    # API
    path("api/llm-providers/", views.llm_provider_list, name="llm_provider_list"),
    path("api/llm-providers/<int:provider_id>/models/", views.llm_model_list, name="llm_model_list"),
    path("api/projects/<int:project_id>/set-llm/", views.project_set_llm, name="project_set_llm"),
]
