import os
import sys
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect, render

from .forms import ChatMessageForm, ProjectForm
from django.http import JsonResponse
from .models import Project, RequirementMessage, RequirementSession, LLMProvider, LLMModel
from .services import analyzer

# 内置阿里模型清单（可直接用于下拉选择）
ALI_BUILTIN_MODELS = [
    ("qwen-plus", "Qwen Plus"),
    ("qwen-plus-latest", "Qwen Plus Latest"),
    ("qwen-max", "Qwen Max"),
    ("qwen-max-latest", "Qwen Max Latest"),
    ("qwen-turbo", "Qwen Turbo"),
    ("qwen-turbo-latest", "Qwen Turbo Latest"),
    ("qwen-flash", "Qwen Flash"),
    ("qwen-long", "Qwen Long"),
    ("qwen-vl-plus", "Qwen VL Plus"),
    ("qwen-vl-max", "Qwen VL Max"),
    ("qwen-coder-plus", "Qwen Coder Plus"),
    ("qwen-coder-turbo", "Qwen Coder Turbo"),
    ("qwq-plus", "QwQ Plus"),
    ("qwen-math-plus", "Qwen Math Plus"),
    ("qwen-math-turbo", "Qwen Math Turbo"),
]

# 添加 tools 路径以使用 file_reader
current_dir = os.path.dirname(os.path.abspath(__file__))
tools_path = os.path.abspath(os.path.join(current_dir, '..', '..', 'tools', 'file_reader'))
if tools_path not in sys.path:
    sys.path.insert(0, tools_path)

try:
    from file_reader import FileReader
except ImportError:
    FileReader = None

# 添加 tools 路径以使用 rule_reader
rule_reader_tools_path = os.path.abspath(os.path.join(current_dir, '..', '..', 'tools', 'rule_reader'))
if rule_reader_tools_path not in sys.path:
    sys.path.insert(0, rule_reader_tools_path)

try:
    from rule_reader import RuleReader
except ImportError:
    RuleReader = None


def home(request):
    return redirect("session_list")


def _ensure_builtin_llm_models():
    """确保内置阿里模型存在于数据库中。"""
    ali_provider, _ = LLMProvider.objects.get_or_create(
        name="阿里",
        defaults={"api_key_env": "QWEN_API_KEY"},
    )

    for model_id, model_name in ALI_BUILTIN_MODELS:
        LLMModel.objects.update_or_create(
            model_id=model_id,
            defaults={
                "provider": ali_provider,
                "name": model_name,
                "is_default": model_id == "qwen-plus",
            },
        )


def _generate_session_title(message: str) -> str:
    first_line = message.strip().splitlines()[0] if message.strip() else ""
    title = first_line[:30].strip()
    return title or "新会话"


def _serialize_message_for_llm(msg):
    attachment_path = msg.attachment.path if msg.attachment else None
    attachment_name = os.path.basename(attachment_path) if attachment_path else None
    return {
        "role": msg.role,
        "content": msg.content,
        "attachment_path": attachment_path,
        "attachment_name": attachment_name,
    }


def _get_current_project(request):
    """获取当前选中的项目"""
    project_id = request.session.get('current_project_id')
    if project_id:
        project = Project.objects.filter(id=project_id, created_by=request.user).first()
        if project:
            return project
    # 返回默认项目
    return Project.get_default_project(request.user)


def _get_rollback_draft(request, session_id):
    return request.session.get(f"rollback_draft_{session_id}")


def _set_rollback_draft(request, session_id, draft):
    request.session[f"rollback_draft_{session_id}"] = draft
    request.session.modified = True


def _clear_rollback_draft(request, session_id):
    key = f"rollback_draft_{session_id}"
    if key in request.session:
        del request.session[key]
        request.session.modified = True


def _build_chat_context(request, active_session=None, message_form=None):
    current_project = _get_current_project(request)
    # 只显示当前项目的会话
    sessions = RequirementSession.objects.filter(
        created_by=request.user,
        project=current_project
    ).order_by("-updated_at")

    # 获取用户的所有项目
    projects = Project.objects.filter(created_by=request.user).order_by("-is_default", "-updated_at")

    current_llm_name = (
        current_project.llm_model.name
        if current_project and current_project.llm_model
        else getattr(settings, "QWEN_MODEL", "未配置模型")
    )

    rollback_draft = _get_rollback_draft(request, active_session.id) if active_session else None
    if active_session and message_form is None and rollback_draft:
        message_form = ChatMessageForm(initial={"content": rollback_draft.get("content", "")})

    return {
        "sessions": sessions,
        "active_session": active_session,
        "messages": active_session.messages.all() if active_session else [],
        "message_form": message_form or ChatMessageForm(),
        "current_project": current_project,
        "projects": projects,
        "current_llm_name": current_llm_name,
        "rollback_draft": rollback_draft,
    }


@login_required
def session_list(request):
    return render(request, "collector/session_list.html", _build_chat_context(request))


@login_required
def requirement_file_list(request):
    current_project = _get_current_project(request)
    files = []
    directory = ""
    preview_name = request.GET.get("preview", "").strip()
    preview_content = ""
    preview_error = ""

    if current_project:
        directory = current_project.ensure_or_path_exists()
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.is_file():
                    continue
                stat = entry.stat()
                created_ts = getattr(stat, "st_birthtime", stat.st_ctime)
                files.append(
                    {
                        "name": entry.name,
                        "created_at": datetime.fromtimestamp(created_ts),
                        "updated_at": datetime.fromtimestamp(stat.st_mtime),
                        "size": stat.st_size,
                    }
                )
        files.sort(key=lambda item: item["created_at"], reverse=True)

        if preview_name:
            if os.path.basename(preview_name) != preview_name:
                preview_error = "文件名不合法。"
            elif not preview_name.lower().endswith(".md"):
                preview_error = "仅支持预览 .md 文件。"
            else:
                preview_path = os.path.realpath(os.path.join(directory, preview_name))
                directory_path = os.path.realpath(directory)
                if not preview_path.startswith(f"{directory_path}{os.sep}"):
                    preview_error = "文件路径不在当前目录内。"
                elif not os.path.isfile(preview_path):
                    preview_error = "文件不存在。"
                else:
                    try:
                        with open(preview_path, "r", encoding="utf-8") as fp:
                            preview_content = fp.read()
                    except OSError:
                        preview_error = "读取文件失败。"

    return render(
        request,
        "collector/requirement_file_list.html",
        {
            "current_project": current_project,
            "directory": directory,
            "files": files,
            "preview_name": preview_name,
            "preview_content": preview_content,
            "preview_error": preview_error,
        },
    )


@login_required
def session_detail(request, session_id):
    active_session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user), id=session_id
    )
    # 将会话的项目设为当前项目
    if active_session.project:
        request.session['current_project_id'] = active_session.project.id

    return render(
        request,
        "collector/session_list.html",
        _build_chat_context(request, active_session=active_session),
    )


@login_required
def session_create(request):
    if request.method != "POST":
        return redirect("session_list")

    message_form = ChatMessageForm(request.POST, request.FILES)
    if message_form.is_valid():
        user_content = message_form.cleaned_data["content"]
        user_attachment = message_form.cleaned_data["attachment"]

        # 检查是否既没有文本也没有附件
        if not user_content and not user_attachment:
            messages.error(request, "请输入消息内容或上传附件。")
            return render(
                request,
                "collector/session_list.html",
                _build_chat_context(request, message_form=message_form),
            )

        # 获取当前项目
        current_project = _get_current_project(request)

        session = RequirementSession.objects.create(
            title=_generate_session_title(user_content or "附件消息"),
            content="",
            created_by=request.user,
            project=current_project,
        )
        user_message = RequirementMessage.objects.create(
            session=session,
            role=RequirementMessage.ROLE_USER,
            content=user_content,
            attachment=user_attachment,  # 保存附件
        )

        # 使用大模型分析需求
        analysis_result = analyzer.analyze_requirement(
            user_content,
            llm_model=current_project.llm_model,
            latest_attachment_path=user_message.attachment.path if user_message.attachment else None,
        )

        RequirementMessage.objects.create(
            session=session,
            role=RequirementMessage.ROLE_ASSISTANT,
            content=analysis_result["response"],
        )
        session.save()
        return redirect("session_detail", session_id=session.id)

    return render(
        request,
        "collector/session_list.html",
        _build_chat_context(request, message_form=message_form),
    )


@login_required
def session_send(request, session_id):
    if request.method != "POST":
        return redirect("session_detail", session_id=session_id)

    active_session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user), id=session_id
    )
    message_form = ChatMessageForm(request.POST, request.FILES)
    if message_form.is_valid():
        user_content = message_form.cleaned_data["content"]
        user_attachment = message_form.cleaned_data["attachment"]
        rollback_draft = _get_rollback_draft(request, active_session.id) or {}
        rollback_attachment_path = rollback_draft.get("attachment_path", "")
        rollback_attachment_name = rollback_draft.get("attachment_name", "")

        if (not user_attachment) and rollback_attachment_path and os.path.exists(rollback_attachment_path):
            try:
                with open(rollback_attachment_path, "rb") as rollback_file:
                    from django.core.files.uploadedfile import SimpleUploadedFile
                    user_attachment = SimpleUploadedFile(
                        rollback_attachment_name or os.path.basename(rollback_attachment_path),
                        rollback_file.read(),
                    )
            except OSError:
                user_attachment = None

        # 检查是否既没有文本也没有附件
        if not user_content and not user_attachment:
            messages.error(request, "请输入消息内容或上传附件。")
            return render(
                request,
                "collector/session_list.html",
                _build_chat_context(
                    request, active_session=active_session, message_form=message_form
                ),
            )

        RequirementMessage.objects.create(
            session=active_session,
            role=RequirementMessage.ROLE_USER,
            content=user_content,
            attachment=user_attachment,  # 保存附件
        )

        # 获取对话历史
        conversation_history = []
        for msg in active_session.messages.all():
            conversation_history.append(_serialize_message_for_llm(msg))

        # 根据会话阶段处理
        if active_session.phase == RequirementSession.PHASE_COLLECTING:
            # 第一阶段：收集需求，判断是否完成
            analysis_result = analyzer.analyze_requirement(user_content, conversation_history, llm_model=active_session.project.llm_model)

            # 检查用户是否确认需求描述完成
            user_confirmed = any(keyword in user_content for keyword in ['说完了', '描述完了', '结束了', '完成了', '需求清楚了'])

            if user_confirmed and analysis_result["is_complete"]:
                # 用户确认完成，进入第二阶段
                active_session.phase = RequirementSession.PHASE_ORGANIZING
                active_session.save()

                # 读取项目规则
                project_rules = _get_project_rules(active_session.project)

                # 整理需求
                organize_result = analyzer.organize_requirement(conversation_history, project_rules, llm_model=active_session.project.llm_model)

                if organize_result["success"]:
                    # 保存生成的文档到会话
                    active_session.content = organize_result["document"]
                    active_session.title = organize_result["title"]
                    active_session.save()

                    # 保存文档到项目目录
                    _save_requirement_document(active_session, organize_result, request)

                    response_text = f"""需求整理完成！

已生成原始需求文档：{organize_result["title"]}.md

文档内容：
{organize_result["document"]}

如需修改，请继续对话；如确认无误，会话将标记为完成。"""
                else:
                    response_text = f"需求整理时出错：{organize_result['error']}"

                RequirementMessage.objects.create(
                    session=active_session,
                    role=RequirementMessage.ROLE_ASSISTANT,
                    content=response_text,
                )
            else:
                # 继续第一阶段
                RequirementMessage.objects.create(
                    session=active_session,
                    role=RequirementMessage.ROLE_ASSISTANT,
                    content=analysis_result["response"],
                )

        elif active_session.phase == RequirementSession.PHASE_ORGANIZING:
            # 第二阶段：用户可能需要修改需求文档
            # 重新整理需求
            project_rules = _get_project_rules(active_session.project)
            organize_result = analyzer.organize_requirement(conversation_history, project_rules, llm_model=active_session.project.llm_model)

            if organize_result["success"]:
                active_session.content = organize_result["document"]
                active_session.save()

                # 保存更新后的文档
                _save_requirement_document(active_session, organize_result, request)

                response_text = f"""需求文档已更新：{organize_result["title"]}.md

更新后的内容：
{organize_result["document"]}

如需继续修改请说明；如确认无误，请输入"确认完成"。"""
            else:
                response_text = f"更新文档时出错：{organize_result['error']}"

            RequirementMessage.objects.create(
                session=active_session,
                role=RequirementMessage.ROLE_ASSISTANT,
                content=response_text,
            )

            # 检查用户是否确认完成
            if '确认完成' in user_content or '完成了' in user_content:
                active_session.phase = RequirementSession.PHASE_COMPLETED
                active_session.save()

                RequirementMessage.objects.create(
                    session=active_session,
                    role=RequirementMessage.ROLE_ASSISTANT,
                    content="会话已完成！原始需求文档已保存。",
                )

        active_session.save()
        _clear_rollback_draft(request, active_session.id)
        return redirect("session_detail", session_id=active_session.id)

    return render(
        request,
        "collector/session_list.html",
        _build_chat_context(
            request, active_session=active_session, message_form=message_form
        ),
    )


@login_required
def session_rollback(request, session_id, message_id):
    if request.method != "POST":
        return redirect("session_detail", session_id=session_id)

    active_session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user), id=session_id
    )
    target_message = get_object_or_404(
        RequirementMessage.objects.filter(
            session=active_session,
            role=RequirementMessage.ROLE_USER,
        ),
        id=message_id,
    )

    rollback_draft = {
        "content": target_message.content or "",
        "attachment_path": target_message.attachment.path if target_message.attachment else "",
        "attachment_name": os.path.basename(target_message.attachment.name) if target_message.attachment else "",
    }

    # 回退该用户消息以及其后的所有消息，保留会话壳与左侧列表项。
    RequirementMessage.objects.filter(session=active_session, id__gte=target_message.id).delete()
    active_session.phase = RequirementSession.PHASE_COLLECTING
    active_session.save(update_fields=["phase", "updated_at"])
    _set_rollback_draft(request, active_session.id, rollback_draft)
    messages.success(request, "已回退到所选用户消息，可修改后重新发送。")
    return redirect("session_detail", session_id=active_session.id)


@login_required
def session_delete(request, session_id):
    """删除会话"""
    session = get_object_or_404(
        RequirementSession.objects.filter(created_by=request.user), id=session_id
    )
    session_title = session.title
    session.delete()
    messages.success(request, f"会话 '{session_title}' 已删除！")
    return redirect("session_list")


def _get_project_rules(project):
    """获取项目规则文档内容"""
    if not project:
        return None

    target_path = os.path.join(project.path, 'doc', '01-or')

    if RuleReader:
        reader = RuleReader()
        result = reader.read_hierarchical_rules(
            target_path=target_path,
            stop_at=project.path,
        )
        if result.get("success"):
            return result["data"].get("merged_rules")

    # 降级：仅读取当前层级 rules.md
    rules_path = os.path.join(target_path, 'rules.md')
    if FileReader and os.path.exists(rules_path):
        fallback_reader = FileReader()
        fallback_result = fallback_reader.read_file(rules_path)
        if fallback_result.get("success"):
            return fallback_result["data"]["content"]

    return None


def _save_requirement_document(session, organize_result, request):
    """保存需求文档到项目目录"""
    if not session.project:
        return False

    try:
        # 确保目录存在
        or_path = session.project.ensure_or_path_exists()

        # 构建文件名
        filename = f"{organize_result['title']}.md"
        if not filename.startswith('【原始需求】'):
            filename = f"【原始需求】{filename}"

        filepath = os.path.join(or_path, filename)

        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(organize_result["document"])

        messages.success(request, f"原始需求文档已保存：{filename}")
        return True
    except Exception as e:
        messages.error(request, f"保存文档时出错：{str(e)}")
        return False


# ==================== 项目管理视图 ====================

@login_required
def project_list(request):
    """项目列表"""
    projects = Project.objects.filter(created_by=request.user).order_by("-is_default", "-updated_at")
    return render(request, "collector/project_list.html", {
        "projects": projects,
        "current_project": _get_current_project(request),
    })


@login_required
def project_create(request):
    """创建项目"""
    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.created_by = request.user

            # 处理项目路径
            path_input = form.cleaned_data.get('path', '').strip()
            if path_input:
                # 如果用户输入了路径，使用用户输入的
                if os.path.isabs(path_input):
                    project.path = path_input
                else:
                    # 相对路径，放在 projects_base_path 下
                    base_path = Project.get_projects_base_path()
                    project.path = os.path.join(base_path, path_input)
            else:
                # 没有输入路径，默认放在 core 同级目录
                base_path = Project.get_projects_base_path()
                project.path = os.path.join(base_path, project.name)

            project.save()

            # 初始化项目目录结构（复制 doc、tools 和 roles.md）
            try:
                project.initialize_project_structure()
            except Exception as e:
                messages.warning(request, f"项目 '{project.name}' 创建成功，但初始化目录结构时出错：{str(e)}")
            else:
                messages.success(request, f"项目 '{project.name}' 创建成功！已初始化目录结构。")

            return redirect("project_list")
    else:
        form = ProjectForm()

    return render(request, "collector/project_form.html", {
        "form": form,
        "action": "创建",
        "current_project": _get_current_project(request),
    })


@login_required
def project_edit(request, project_id):
    """编辑项目"""
    project = get_object_or_404(Project, id=project_id, created_by=request.user)

    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        if form.is_valid():
            form.save()
            messages.success(request, f"项目 '{project.name}' 更新成功！")
            return redirect("project_list")
    else:
        form = ProjectForm(instance=project)

    return render(request, "collector/project_form.html", {
        "form": form,
        "project": project,
        "action": "编辑",
        "current_project": _get_current_project(request),
    })


@login_required
def project_delete(request, project_id):
    """删除项目"""
    project = get_object_or_404(Project, id=project_id, created_by=request.user)

    # 不允许删除默认项目
    if project.is_default:
        messages.error(request, "不能删除默认项目！")
        return redirect("project_list")

    if request.method == "POST":
        project_name = project.name
        project.delete()
        messages.success(request, f"项目 '{project_name}' 已删除！")
        return redirect("project_list")

    return render(request, "collector/project_confirm_delete.html", {
        "project": project,
        "current_project": _get_current_project(request),
    })


@login_required
def project_switch(request, project_id):
    """切换当前项目"""
    project = get_object_or_404(Project, id=project_id, created_by=request.user)
    request.session['current_project_id'] = project.id
    messages.success(request, f"已切换到项目 '{project.name}'")
    return redirect("session_list")


@login_required
def project_set_default(request, project_id):
    """设置默认项目"""
    project = get_object_or_404(Project, id=project_id, created_by=request.user)
    project.is_default = True
    project.save()
    messages.success(request, f"项目 '{project.name}' 已设为默认项目")
    return redirect("project_list")


# ==================== LLM 模型 API ====================

@login_required
def llm_provider_list(request):
    """获取所有 LLM 厂商及其模型（树形结构）"""
    _ensure_builtin_llm_models()
    providers = list(LLMProvider.objects.all().values("id", "name"))
    for provider in providers:
        models = list(
            LLMModel.objects.filter(provider_id=provider["id"]).values("id", "name", "model_id")
        )
        if provider["name"] == "阿里":
            order_map = {model_id: idx for idx, (model_id, _) in enumerate(ALI_BUILTIN_MODELS)}
            models.sort(key=lambda item: order_map.get(item["model_id"], 10**6))
        else:
            models.sort(key=lambda item: item["name"])
        provider["models"] = models
    return JsonResponse(providers, safe=False)


@login_required
def llm_model_list(request, provider_id):
    """获取指定厂商的所有 LLM 模型"""
    _ensure_builtin_llm_models()
    provider = get_object_or_404(LLMProvider, id=provider_id)
    models_qs = LLMModel.objects.filter(provider_id=provider_id).values('id', 'name', 'model_id')
    models = list(models_qs)

    if provider.name == "阿里":
        order_map = {model_id: idx for idx, (model_id, _) in enumerate(ALI_BUILTIN_MODELS)}
        models.sort(key=lambda item: order_map.get(item["model_id"], 10**6))
    else:
        models.sort(key=lambda item: item["name"])

    return JsonResponse(models, safe=False)


@login_required
def project_set_llm(request, project_id):
    if request.method == 'POST':
        try:
            model_id = request.POST.get('model_id')
            project = get_object_or_404(Project, id=project_id, created_by=request.user)
            llm_model = get_object_or_404(LLMModel, id=model_id)
            project.llm_model = llm_model
            project.save()
            return JsonResponse({'success': True, 'model_name': llm_model.name})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)
