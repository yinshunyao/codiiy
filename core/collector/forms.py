import json

from django import forms

from .models import CompanionProfile, LLMApiConfig, LLMModel, LocalLLMConfig, Project


class ChatMessageForm(forms.Form):
    content = forms.CharField(
        label="消息内容",
        max_length=4000,
        widget=forms.Textarea(
            attrs={"rows": 4, "placeholder": "输入你的需求内容（Shift+Enter 换行），或使用麦克风语音输入"}
        ),
        required=False,  # 允许仅发送附件而不填写文本
    )
    attachment = forms.FileField(
        label="上传附件",
        required=False,
        widget=forms.ClearableFileInput(attrs={"style": "margin-top: 10px;"}),
    )


class ProjectForm(forms.ModelForm):
    """项目表单"""
    # 将 path 设为可选，如果不填则默认放在 core 同级目录
    path = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-mindforge', 'placeholder': '留空则默认放在 core 同级目录，或输入路径如：test 或 /path/to/project'}),
        label='项目路径',
        help_text='支持相对路径（相对于 core 的父目录）或绝对路径。需求文档将保存到项目路径下的 doc/01-or 文件夹'
    )

    class Meta:
        model = Project
        fields = ['name', 'path', 'description', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-mindforge', 'placeholder': '项目名称'}),
            'description': forms.Textarea(attrs={'class': 'form-mindforge', 'rows': 3, 'placeholder': '项目描述（可选）'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': '项目名称',
            'description': '项目描述',
            'is_default': '设为默认项目',
        }


class CompanionProfileForm(forms.ModelForm):
    allowed_agent_modules = forms.MultipleChoiceField(
        label="可调用智能体模块",
        choices=(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    allowed_control_modules = forms.MultipleChoiceField(
        label="可调用工具组件模块",
        choices=(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    allowed_toolsets = forms.MultipleChoiceField(
        label="可调用工具集",
        choices=(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    allowed_control_components = forms.MultipleChoiceField(
        label="可调用组件",
        choices=(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-mindforge", "id": "id_allowed_control_components", "size": "8"}),
    )
    allowed_control_functions = forms.MultipleChoiceField(
        label="可调用组件 API",
        choices=(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-mindforge", "id": "id_allowed_control_functions", "size": "10"}),
    )
    model_binding_key = forms.ChoiceField(
        label="可用模型配置",
        choices=(),
        required=False,
        widget=forms.Select(attrs={"class": "form-mindforge", "id": "id_model_binding_key"}),
    )
    backup_models = forms.MultipleChoiceField(
        label="备用模型",
        choices=(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-mindforge", "id": "id_backup_models", "size": "6"}),
    )

    class Meta:
        model = CompanionProfile
        fields = [
            "name",
            "display_name",
            "role_title",
            "persona",
            "tone",
            "memory_notes",
            "llm_routing_mode",
            "llm_source_type",
            "llm_api_config",
            "local_llm_config",
            "default_model_name",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "伙伴标识，如 er_gou"}),
            "display_name": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "展示名，如 二狗"}),
            "role_title": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "角色，如 开发伙伴"}),
            "persona": forms.Textarea(attrs={"class": "form-mindforge", "rows": 3, "placeholder": "角色描述、人设边界"}),
            "tone": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "语气，如 友好、简洁、技术向"}),
            "memory_notes": forms.Textarea(attrs={"class": "form-mindforge", "rows": 4, "placeholder": "长期记忆摘要"}),
            "llm_routing_mode": forms.Select(attrs={"class": "form-mindforge", "id": "id_llm_routing_mode"}),
            "llm_source_type": forms.Select(attrs={"class": "form-mindforge", "id": "id_llm_source_type"}),
            "llm_api_config": forms.HiddenInput(),
            "local_llm_config": forms.HiddenInput(),
            "default_model_name": forms.Select(
                attrs={"class": "form-mindforge", "id": "id_default_model_name"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "伙伴标识",
            "display_name": "展示名称",
            "role_title": "角色名称",
            "persona": "角色描述",
            "tone": "回复语气",
            "memory_notes": "记忆摘要",
            "llm_routing_mode": "模型模式",
            "llm_source_type": "模型来源",
            "llm_api_config": "API 模型配置",
            "local_llm_config": "本地模型配置",
            "default_model_name": "默认使用模型",
            "is_active": "启用伙伴",
        }

    @staticmethod
    def _format_model_label(model_id, display_name):
        model_id_text = str(model_id or "").strip()
        display_name_text = str(display_name or "").strip()
        if not model_id_text:
            return ""
        if display_name_text and display_name_text != model_id_text:
            return f"{display_name_text}（{model_id_text}）"
        return model_id_text

    @staticmethod
    def _build_binding_key(source, config_id):
        return f"{source}|{config_id}"

    @staticmethod
    def _parse_binding_key(binding_key):
        raw = str(binding_key or "").strip()
        parts = raw.split("|")
        if len(parts) != 2:
            return "", ""
        return str(parts[0]).strip(), str(parts[1]).strip()

    @staticmethod
    def _build_model_token(source, config_id, model_name):
        return f"{source}|{config_id}|{str(model_name or '').strip()}"

    def _build_api_model_candidates(self, api_config):
        if not api_config:
            return []
        candidates = []
        provider_name = str(api_config.provider_name or "").strip()
        if provider_name:
            model_qs = LLMModel.objects.filter(provider__name=provider_name).order_by("-is_default", "name")
            for item in model_qs:
                model_id = str(item.model_id or "").strip()
                if not model_id:
                    continue
                candidates.append((model_id, self._format_model_label(model_id, item.name)))
        fallback_model_id = str(api_config.default_model_id or "").strip()
        if fallback_model_id:
            candidates.append((fallback_model_id, self._format_model_label(fallback_model_id, "")))
        unique_candidates = []
        seen = set()
        for model_id, label in candidates:
            if model_id in seen:
                continue
            seen.add(model_id)
            unique_candidates.append((model_id, label))
        return unique_candidates

    @staticmethod
    def _build_local_model_candidates(local_config):
        if not local_config:
            return []
        model_name = str(local_config.model_name or "").strip()
        if not model_name:
            return []
        backend = str(local_config.runtime_backend or "").strip()
        if backend == LocalLLMConfig.BACKEND_LLAMA_CPP:
            backend_label = "llama-cpp"
            param_text = f"n_ctx={local_config.llama_cpp_n_ctx}"
        else:
            backend_label = "ollama"
            param_text = f"keep_alive={local_config.keep_alive}"
        return [(model_name, f"{model_name}（{backend_label} / {param_text}）")]

    @staticmethod
    def _resolve_source_value(raw_value):
        source = str(raw_value or "").strip()
        if source in {CompanionProfile.LLM_SOURCE_API, CompanionProfile.LLM_SOURCE_LOCAL}:
            return source
        return CompanionProfile.LLM_SOURCE_API

    @staticmethod
    def _resolve_routing_mode(raw_value):
        mode = str(raw_value or "").strip()
        if mode in {CompanionProfile.LLM_ROUTING_MANUAL, CompanionProfile.LLM_ROUTING_AUTO}:
            return mode
        return CompanionProfile.LLM_ROUTING_MANUAL

    def __init__(self, *args, **kwargs):
        agent_module_choices = kwargs.pop("agent_module_choices", ())
        control_module_choices = kwargs.pop("control_module_choices", ())
        toolset_choices = kwargs.pop("toolset_choices", ())
        control_component_choices = kwargs.pop("control_component_choices", ())
        control_function_choices = kwargs.pop("control_function_choices", ())
        control_function_component_map = kwargs.pop("control_function_component_map", {})
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["allowed_agent_modules"].choices = agent_module_choices
        self.fields["allowed_control_modules"].choices = control_module_choices
        self.fields["allowed_toolsets"].choices = toolset_choices
        self.fields["allowed_control_components"].choices = control_component_choices
        self.fields["allowed_control_functions"].choices = control_function_choices
        self._control_function_component_map = {
            str(key or "").strip(): str(value or "").strip()
            for key, value in dict(control_function_component_map or {}).items()
            if str(key or "").strip()
        }
        self.fields["llm_api_config"].required = False
        self.fields["local_llm_config"].required = False
        self.fields["default_model_name"].required = False
        self.fields["backup_models"].required = False
        self.fields["llm_api_config"].queryset = LLMApiConfig.objects.none()
        self.fields["local_llm_config"].queryset = LocalLLMConfig.objects.none()
        api_queryset = LLMApiConfig.objects.none()
        local_queryset = LocalLLMConfig.objects.none()
        if user is not None:
            api_queryset = LLMApiConfig.objects.filter(
                created_by=user,
                is_enabled=True,
            ).order_by("-updated_at", "name")
            local_queryset = LocalLLMConfig.objects.filter(
                created_by=user,
                is_enabled=True,
            ).order_by("-updated_at", "name")
            self.fields["llm_api_config"].queryset = api_queryset
            self.fields["local_llm_config"].queryset = local_queryset
        self._api_config_map = {str(item.id): item for item in api_queryset}
        self._local_config_map = {str(item.id): item for item in local_queryset}

        source_value = None
        routing_mode = None
        binding_key = ""
        if self.is_bound:
            routing_mode = self.data.get(self.add_prefix("llm_routing_mode"))
            source_value = self.data.get(self.add_prefix("llm_source_type"))
            binding_key = str(self.data.get(self.add_prefix("model_binding_key")) or "").strip()
        elif self.instance and self.instance.pk:
            routing_mode = self.instance.llm_routing_mode
            source_value = self.instance.llm_source_type
            if self.instance.llm_source_type == CompanionProfile.LLM_SOURCE_LOCAL and self.instance.local_llm_config_id:
                binding_key = self._build_binding_key(CompanionProfile.LLM_SOURCE_LOCAL, self.instance.local_llm_config_id)
            elif self.instance.llm_api_config_id:
                binding_key = self._build_binding_key(CompanionProfile.LLM_SOURCE_API, self.instance.llm_api_config_id)
        routing_mode = self._resolve_routing_mode(routing_mode)
        source_value = self._resolve_source_value(source_value)

        model_options_map = {}
        for config_id, config in self._api_config_map.items():
            key = self._build_binding_key(CompanionProfile.LLM_SOURCE_API, config_id)
            model_options_map[key] = self._build_api_model_candidates(config)
        for config_id, config in self._local_config_map.items():
            key = self._build_binding_key(CompanionProfile.LLM_SOURCE_LOCAL, config_id)
            model_options_map[key] = self._build_local_model_candidates(config)

        binding_choices = [("", "请选择配置")]
        for config_id, config in self._api_config_map.items():
            key = self._build_binding_key(CompanionProfile.LLM_SOURCE_API, config_id)
            provider_name = str(config.provider_name or "").strip() or "API"
            binding_choices.append((key, f"API · {config.name}（{provider_name}）"))
        for config_id, config in self._local_config_map.items():
            key = self._build_binding_key(CompanionProfile.LLM_SOURCE_LOCAL, config_id)
            backend = "llama-cpp" if config.runtime_backend == LocalLLMConfig.BACKEND_LLAMA_CPP else "ollama"
            binding_choices.append((key, f"本地 · {config.name}（{backend}）"))
        self.fields["model_binding_key"].choices = binding_choices
        if binding_key and all(binding_key != item[0] for item in binding_choices):
            binding_key = ""
        if not self.is_bound:
            self.initial["model_binding_key"] = binding_key

        available_model_choices = []
        if binding_key:
            available_model_choices = list(model_options_map.get(binding_key, []))

        default_model_value = ""
        if self.is_bound:
            default_model_value = str(self.data.get(self.add_prefix("default_model_name")) or "").strip()
        elif self.instance and self.instance.pk:
            default_model_value = str(self.instance.default_model_name or "").strip()
        if default_model_value and all(default_model_value != item[0] for item in available_model_choices):
            available_model_choices.append((default_model_value, self._format_model_label(default_model_value, "")))

        default_model_choices = [("", "不设置")] + available_model_choices
        self.fields["default_model_name"].choices = default_model_choices
        self.fields["default_model_name"].widget.choices = default_model_choices
        self.fields["default_model_name"].widget.attrs["data-model-options-map"] = json.dumps(
            model_options_map,
            ensure_ascii=False,
        )

        backup_choices = []
        for item_binding_key, model_items in model_options_map.items():
            source, config_id = self._parse_binding_key(item_binding_key)
            config_obj = self._local_config_map.get(config_id) if source == CompanionProfile.LLM_SOURCE_LOCAL else self._api_config_map.get(config_id)
            source_label = "本地" if source == CompanionProfile.LLM_SOURCE_LOCAL else "API"
            config_name = config_obj.name if config_obj else "未知配置"
            for model_value, model_label in model_items:
                token = self._build_model_token(source, config_id, model_value)
                backup_choices.append((token, f"[{source_label}] {config_name} / {model_label}"))
        self.fields["backup_models"].choices = backup_choices

        if not self.is_bound and self.instance and self.instance.pk:
            initial_tokens = []
            for raw in self.instance.backup_model_tokens or []:
                token = str(raw or "").strip()
                if token:
                    initial_tokens.append(token)
            self.initial["backup_models"] = initial_tokens

        if self.instance and self.instance.pk:
            self.fields["allowed_agent_modules"].initial = self.instance.get_allowed_agent_modules()
            self.fields["allowed_control_modules"].initial = self.instance.get_allowed_control_modules()
            self.fields["allowed_toolsets"].initial = self.instance.get_allowed_toolsets()
            self.fields["allowed_control_components"].initial = self.instance.get_allowed_control_components()
            self.fields["allowed_control_functions"].initial = self.instance.get_allowed_control_functions()

    def clean(self):
        cleaned_data = super().clean()
        routing_mode = self._resolve_routing_mode(cleaned_data.get("llm_routing_mode"))
        source = self._resolve_source_value(cleaned_data.get("llm_source_type"))
        binding_key = str(cleaned_data.get("model_binding_key") or "").strip()
        default_model_name = str(cleaned_data.get("default_model_name") or "").strip()
        backup_models = list(cleaned_data.get("backup_models") or [])

        if routing_mode == CompanionProfile.LLM_ROUTING_AUTO:
            cleaned_data["llm_source_type"] = CompanionProfile.LLM_SOURCE_API
            cleaned_data["llm_api_config"] = None
            cleaned_data["local_llm_config"] = None
            cleaned_data["default_model_name"] = ""
            cleaned_data["backup_models"] = []
            return cleaned_data

        cleaned_data["llm_source_type"] = source
        binding_source, binding_config_id = self._parse_binding_key(binding_key)
        if not binding_key:
            self.add_error("model_binding_key", "请选择可用模型配置。")
            binding_config_id = ""
        elif binding_source != source:
            self.add_error("model_binding_key", "所选配置与模型来源不一致。")

        available_model_choices = []
        llm_api_config = None
        local_llm_config = None
        if source == CompanionProfile.LLM_SOURCE_API:
            llm_api_config = self._api_config_map.get(binding_config_id)
            if llm_api_config is None:
                self.add_error("model_binding_key", "请选择有效的 API 模型配置。")
            cleaned_data["local_llm_config"] = None
            available_model_choices = self._build_api_model_candidates(llm_api_config)
        else:
            local_llm_config = self._local_config_map.get(binding_config_id)
            if local_llm_config is None:
                self.add_error("model_binding_key", "请选择有效的本地模型配置。")
            cleaned_data["llm_api_config"] = None
            available_model_choices = self._build_local_model_candidates(local_llm_config)

        cleaned_data["llm_api_config"] = llm_api_config
        cleaned_data["local_llm_config"] = local_llm_config

        valid_models = {item[0] for item in available_model_choices}
        if default_model_name and default_model_name not in valid_models:
            self.add_error("default_model_name", "默认模型不在当前配置可选范围内。")

        default_token = ""
        if default_model_name and binding_config_id:
            default_token = self._build_model_token(source, binding_config_id, default_model_name)
        if default_token and default_token in backup_models:
            self.add_error("backup_models", "备用模型不能与默认模型重复。")

        dedup_backup = []
        for raw in backup_models:
            token = str(raw or "").strip()
            if not token or token in dedup_backup:
                continue
            dedup_backup.append(token)
        cleaned_data["backup_models"] = dedup_backup

        allowed_control_modules = {
            str(item or "").strip() for item in (cleaned_data.get("allowed_control_modules") or []) if str(item or "").strip()
        }
        allowed_control_components = list(cleaned_data.get("allowed_control_components") or [])
        allowed_control_functions = list(cleaned_data.get("allowed_control_functions") or [])
        for component_key in allowed_control_components:
            normalized_key = str(component_key or "").strip()
            module_name = normalized_key.split(".", 1)[0] if "." in normalized_key else ""
            if module_name and allowed_control_modules and module_name not in allowed_control_modules:
                self.add_error("allowed_control_components", f"组件 {normalized_key} 未命中已授权组件模块。")
        selected_component_set = {
            str(item or "").strip() for item in allowed_control_components if str(item or "").strip()
        }
        for function_path in allowed_control_functions:
            normalized_path = str(function_path or "").strip()
            parts = normalized_path.split(".")
            module_name = parts[1] if len(parts) >= 3 else ""
            if module_name and allowed_control_modules and module_name not in allowed_control_modules:
                self.add_error("allowed_control_functions", f"API {normalized_path} 未命中已授权组件模块。")
            component_key = self._control_function_component_map.get(normalized_path, "")
            if selected_component_set and component_key and component_key not in selected_component_set:
                self.add_error("allowed_control_functions", f"API {normalized_path} 未命中已授权组件。")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.allowed_agent_modules_text = ",".join(self.cleaned_data.get("allowed_agent_modules", []))
        instance.allowed_control_modules_text = ",".join(self.cleaned_data.get("allowed_control_modules", []))
        instance.allowed_toolsets_text = ",".join(self.cleaned_data.get("allowed_toolsets", []))
        instance.allowed_control_components_text = ",".join(self.cleaned_data.get("allowed_control_components", []))
        instance.allowed_control_functions_text = ",".join(self.cleaned_data.get("allowed_control_functions", []))
        instance.backup_model_tokens = list(self.cleaned_data.get("backup_models", []))
        if commit:
            instance.save()
        return instance


class LLMApiConfigForm(forms.ModelForm):
    class Meta:
        model = LLMApiConfig
        fields = ["name", "provider_name", "base_url", "api_key", "default_model_id", "is_enabled"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "如：阿里-生产"}),
            "provider_name": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "如：阿里 / OpenAI"}),
            "base_url": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "如：https://dashscope.aliyuncs.com/compatible-mode/v1"}),
            "api_key": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "输入 API Key"}),
            "default_model_id": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "如：qwen-plus"}),
            "is_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "配置名称",
            "provider_name": "厂商名称",
            "base_url": "API Base URL",
            "api_key": "API Key",
            "default_model_id": "默认模型 ID",
            "is_enabled": "启用配置",
        }


class LocalLLMConfigForm(forms.ModelForm):
    class Meta:
        model = LocalLLMConfig
        fields = [
            "name",
            "runtime_backend",
            "model_name",
            "endpoint",
            "keep_alive",
            "model_file_path",
            "llama_cpp_n_ctx",
            "is_enabled",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "如：本地Qwen"}),
            "runtime_backend": forms.Select(attrs={"class": "form-mindforge", "id": "id_runtime_backend"}),
            "endpoint": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "如：http://127.0.0.1:11434"}),
            "model_name": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "如：qwen2.5:7b"}),
            "keep_alive": forms.TextInput(attrs={"class": "form-mindforge", "placeholder": "如：5m / 1h"}),
            "model_file_path": forms.TextInput(
                attrs={"class": "form-mindforge", "placeholder": "如：/data/models/qwen2.5-7b-instruct.gguf"}
            ),
            "llama_cpp_n_ctx": forms.NumberInput(attrs={"class": "form-mindforge", "min": "256", "step": "256"}),
            "is_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        labels = {
            "name": "配置名称",
            "runtime_backend": "本地模型实现模式",
            "endpoint": "Ollama 地址",
            "model_name": "模型名称",
            "keep_alive": "keep_alive",
            "model_file_path": "llama-cpp 模型文件路径",
            "llama_cpp_n_ctx": "llama-cpp 上下文窗口",
            "is_enabled": "启用配置",
        }

    def clean(self):
        cleaned_data = super().clean()
        backend = str(cleaned_data.get("runtime_backend") or LocalLLMConfig.BACKEND_OLLAMA).strip()
        endpoint = str(cleaned_data.get("endpoint") or "").strip()
        model_name = str(cleaned_data.get("model_name") or "").strip()
        model_file_path = str(cleaned_data.get("model_file_path") or "").strip()

        if not model_name:
            self.add_error("model_name", "请输入模型名称。")

        if backend == LocalLLMConfig.BACKEND_OLLAMA:
            if not endpoint:
                self.add_error("endpoint", "Ollama 模式必须填写地址。")
            cleaned_data["model_file_path"] = ""
            if not str(cleaned_data.get("keep_alive") or "").strip():
                cleaned_data["keep_alive"] = "5m"
        elif backend == LocalLLMConfig.BACKEND_LLAMA_CPP:
            if not model_file_path:
                self.add_error("model_file_path", "llama-cpp 模式必须填写模型文件路径。")
            cleaned_data["endpoint"] = ""
        else:
            self.add_error("runtime_backend", "不支持的本地模型实现模式。")

        return cleaned_data

