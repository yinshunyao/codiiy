import logging
import base64
import mimetypes
from django.conf import settings
import sys
import os
import re

logger = logging.getLogger(__name__)

# 使用绝对路径导入 qwen_client
# 当前文件路径: core/code/collector/services.py
# qwen_client 路径: core/tools/qwen_client
current_dir = os.path.dirname(os.path.abspath(__file__))
core_tools_path = os.path.abspath(os.path.join(current_dir, '..', '..', 'tools', 'qwen_client'))
if core_tools_path not in sys.path:
    sys.path.insert(0, core_tools_path)

try:
    from qwen_client import QwenClient
    logger.info(f"QwenClient imported successfully from {core_tools_path}")
except ImportError as e:
    QwenClient = None
    logger.error(f"Failed to import QwenClient from {core_tools_path}: {str(e)}")


class RequirementAnalyzer:
    """
    需求分析服务
    使用大模型判断用户需求表达是否完整
    """

    def __init__(self, llm_model=None):
        self.api_key = settings.QWEN_API_KEY
        self.model = llm_model.model_id if llm_model else settings.QWEN_MODEL
        self.client = None

        if self.api_key and QwenClient:
            try:
                self.client = QwenClient(api_key=self.api_key)
            except Exception as e:
                logger.error(f"初始化 QwenClient 失败: {str(e)}")

    def is_available(self):
        """检查大模型服务是否可用"""
        return self.client is not None

    def analyze_requirement(self, user_content, conversation_history=None, llm_model=None, latest_attachment_path=None):
        """
        分析用户需求表达是否完整

        Args:
            user_content (str): 用户的最新输入
            conversation_history (list): 对话历史，格式为 [{"role": "user/assistant", "content": "..."}]
            llm_model (LLMModel, optional): 使用的大语言模型. Defaults to None.

        Returns:
            dict: 包含分析结果的字典
                {
                    "is_complete": bool,  # 需求是否完整
                    "response": str,     # 助手的回复内容
                    "questions": list,   # 如果不完整，需要问的问题列表
                    "error": str         # 错误信息（如果有）
                }
        """
        if not self.is_available():
            return {
                "is_complete": True,
                "response": "已收到，你描述完了么？",
                "questions": [],
                "error": "大模型服务不可用"
            }

        try:
            selected_model_id = llm_model.model_id if llm_model else self.model
            has_multimodal_input = self._has_multimodal_input(
                conversation_history=conversation_history,
                latest_attachment_path=latest_attachment_path,
            )
            use_multimodal = self._is_vision_model(selected_model_id) and has_multimodal_input
            messages = self._build_analysis_messages(
                user_content=user_content,
                conversation_history=conversation_history,
                latest_attachment_path=latest_attachment_path,
                use_multimodal=use_multimodal,
            )
            model_to_use = self._resolve_model_for_task(
                selected_model_id,
                has_multimodal_input=has_multimodal_input,
            )

            result = self.client.chat_completion(
                model=model_to_use,
                messages=messages,
                temperature=0.3,
                max_tokens=500
            )

            if result and result.get("success"):
                response_text = self._extract_response_text(result["data"])
                return self._parse_analysis_result(response_text)
            else:
                logger.error(f"大模型调用失败: {result.get('error') if result else '未知错误'}")
                return {
                    "is_complete": True,
                    "response": "已收到，你描述完了么？",
                    "questions": [],
                    "error": result.get("error") if result else "未知错误"
                }

        except Exception as e:
            logger.error(f"分析需求时出错: {str(e)}")
            return {
                "is_complete": True,
                "response": "已收到，你描述完了么？",
                "questions": [],
                "error": str(e)
            }

    def _build_analysis_messages(self, user_content, conversation_history=None, latest_attachment_path=None, use_multimodal=False):
        """
        构建用于分析的消息列表

        Args:
            user_content (str): 用户的最新输入
            conversation_history (list): 对话历史

        Returns:
            list: 消息列表
        """
        system_prompt = """你是一个专业的需求分析助手。你的任务是判断用户的需求描述是否完整。

请根据用户的需求描述进行判断：
1. 如果用户的需求描述完整、清晰，没有疑问，进入整理阶段。
2. 如果用户的需求描述不完整、不清晰或有疑问，继续澄清阶段。

注意：
- 重点关注需求的目标、功能、场景、约束等关键信息
- 如果信息缺失，提出针对性的问题
- 问题要简洁明了，一次最多问2-3个问题
- 保持友好、专业的语气

你必须严格按如下格式输出，并且只能输出两行：
SIGNAL: READY_FOR_ORGANIZE 或 NEED_CLARIFICATION
REPLY: 给用户显示的回复内容

当信息完整时：
- SIGNAL 必须为 READY_FOR_ORGANIZE
- REPLY 建议使用：已收到，你描述完了么？

当信息不完整时：
- SIGNAL 必须为 NEED_CLARIFICATION
- REPLY 仅输出澄清问题或澄清说明"""

        messages = [{"role": "system", "content": system_prompt}]

        for msg in conversation_history or []:
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            content = msg.get("content") or ""
            attachment_path = msg.get("attachment_path")
            messages.append({
                "role": role,
                "content": self._build_message_content(content, attachment_path, use_multimodal),
            })

        # 检查最后一条消息是否就是当前用户消息，避免重复添加
        if not self._is_same_as_last_user_message(
            conversation_history=conversation_history,
            user_content=user_content,
            latest_attachment_path=latest_attachment_path,
        ):
            messages.append({
                "role": "user",
                "content": self._build_message_content(user_content, latest_attachment_path, use_multimodal),
            })

        return messages

    def _parse_analysis_result(self, response_text):
        """
        解析大模型的返回结果

        Args:
            response_text (str): 大模型的返回文本

        Returns:
            dict: 解析后的结果
        """
        response_text = response_text.strip()
        signal, reply = self._extract_phase_signal_and_reply(response_text)

        if signal == "READY_FOR_ORGANIZE":
            return {
                "is_complete": True,
                "response": reply or "已收到，你描述完了么？",
                "questions": [],
                "error": None
            }

        if signal == "NEED_CLARIFICATION":
            display_text = reply or response_text
            return {
                "is_complete": False,
                "response": display_text,
                "questions": self._extract_questions(display_text),
                "error": None
            }

        # 兼容兜底：模型未遵循结构化输出时，继续使用语义识别。
        if self._is_completion_response(response_text):
            return {
                "is_complete": True,
                "response": "已收到，你描述完了么？",
                "questions": [],
                "error": None
            }

        return {
            "is_complete": False,
            "response": response_text,
            "questions": self._extract_questions(response_text),
            "error": None
        }

    def _extract_phase_signal_and_reply(self, response_text):
        """
        解析第一阶段返回中的结构化信号。
        """
        signal_match = re.search(
            r'^\s*SIGNAL\s*[:：]\s*(READY_FOR_ORGANIZE|NEED_CLARIFICATION)\s*$',
            response_text,
            re.MULTILINE
        )
        reply_match = re.search(r'^\s*REPLY\s*[:：]\s*(.+)$', response_text, re.MULTILINE)

        signal = signal_match.group(1).strip() if signal_match else None
        reply = reply_match.group(1).strip() if reply_match else ""
        return signal, reply

    def _is_completion_response(self, response_text):
        """
        判断模型回复是否表达了“需求已完整，可进入整理”语义。
        """
        normalized = (response_text or "").strip()
        if not normalized:
            return False

        if "已收到，你描述完了么？" in normalized:
            return True

        completion_keywords = [
            "需求描述已完成",
            "描述已完成",
            "已确认需求描述已完成",
            "需求已经完整",
            "信息已完整",
            "可以进入整理",
            "开始整理",
            "进行汇总",
            "整体整理",
            "总结如下",
            "需求摘要如下",
        ]
        return any(keyword in normalized for keyword in completion_keywords)

    def _extract_questions(self, text):
        """
        从文本中提取问题

        Args:
            text (str): 文本内容

        Returns:
            list: 问题列表
        """
        questions = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if line and ('?' in line or '？' in line):
                questions.append(line)

        return questions

    def organize_requirement(self, conversation_history, project_rules=None, llm_model=None):
        """
        第二阶段：整理需求，生成原始需求文档

        Args:
            conversation_history (list): 完整的对话历史
            project_rules (str): 项目规则文档内容
            llm_model (LLMModel, optional): 使用的大语言模型. Defaults to None.

        Returns:
            dict: 包含整理结果的字典
                {
                    "success": bool,
                    "document": str,     # 生成的原始需求文档
                    "title": str,        # 建议的文档标题
                    "error": str         # 错误信息（如果有）
                }
        """
        if not self.is_available():
            return {
                "success": False,
                "document": "",
                "title": "",
                "error": "大模型服务不可用"
            }

        try:
            selected_model_id = llm_model.model_id if llm_model else self.model
            has_multimodal_input = self._history_has_supported_modal_attachments(conversation_history)
            use_multimodal = self._is_vision_model(selected_model_id) and has_multimodal_input
            messages = self._build_organization_messages(
                conversation_history,
                project_rules,
                use_multimodal=use_multimodal,
            )
            model_to_use = self._resolve_model_for_task(
                selected_model_id,
                has_multimodal_input=has_multimodal_input,
            )

            result = self.client.chat_completion(
                model=model_to_use,
                messages=messages,
                temperature=0.3,
                max_tokens=2000
            )

            if result and result.get("success"):
                response_text = self._extract_response_text(result["data"])
                return self._parse_organization_result(response_text)
            else:
                logger.error(f"大模型调用失败: {result.get('error') if result else '未知错误'}")
                return {
                    "success": False,
                    "document": "",
                    "title": "",
                    "error": result.get("error") if result else "未知错误"
                }

        except Exception as e:
            logger.error(f"整理需求时出错: {str(e)}")
            return {
                "success": False,
                "document": "",
                "title": "",
                "error": str(e)
            }

    def _build_organization_messages(self, conversation_history, project_rules=None, use_multimodal=False):
        """
        构建用于整理需求的消息列表

        Args:
            conversation_history (list): 完整的对话历史
            project_rules (str): 项目规则文档内容

        Returns:
            list: 消息列表
        """
        # 构建对话内容
        conversation_text = ""
        attachment_paths = []
        for msg in conversation_history:
            role = "用户" if msg.get("role") == "user" else "助手"
            content = msg.get("content", "")
            attachment_path = msg.get("attachment_path")
            attachment_name = msg.get("attachment_name")
            if attachment_path and attachment_name:
                conversation_text += f"{role}: {content}\n（附件：{attachment_name}）\n\n"
                normalized = self._normalize_attachment_path(attachment_path)
                if normalized:
                    attachment_paths.append(normalized)
            else:
                conversation_text += f"{role}: {content}\n\n"

        rules_text = project_rules.strip() if project_rules else "未提供规则文档。"

        system_prompt = f"""你是一个专业的需求分析师。你的任务是根据用户与助手的完整对话，输出原始需求文档。

你必须遵循以下规则：
1. 严格遵循“规则文档”中的约束；当规则有层级时，按“就近优先”的顺序理解。
2. 使用用户语言描述，不要引入设计方案、实现细节和过度专业术语。
3. 输出结构必须完整，且保持简洁、重点明确。
4. 在文档开头用一行注释标注建议文件名，格式：<!-- 建议文件名：xxx.md -->

规则文档（按优先级从高到低）：
{rules_text}

请按照以下格式输出：

```markdown
# 背景
[描述需求的背景、业务场景等]

# 目标
[描述用户想要达成的目标，使用用户语言]

# 需求（或要求）
[详细描述用户的具体需求，使用用户语言]

# 当前工作项（已完成可忽略）
- **问题或者需求**：
  - [待解决的问题]
- **已完成**：
  - [已完成的内容]
```
"""
        user_prompt = f"""以下是完整对话，请直接整理原始需求文档：

{conversation_text}
"""

        if use_multimodal and attachment_paths:
            content_blocks = [{"text": user_prompt}]
            for path in attachment_paths:
                modal_block = self._build_modal_content_block(path)
                if modal_block:
                    content_blocks.append(modal_block)
            if len(content_blocks) == 1:
                return [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            return [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_blocks},
            ]

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_organization_result(self, response_text):
        """
        解析整理需求的结果

        Args:
            response_text (str): 大模型的返回文本

        Returns:
            dict: 解析后的结果
        """
        # 提取建议的文件名
        title = "原始需求"
        import re
        filename_match = re.search(r'<!--\s*建议文件名：(.+?)\s*-->', response_text)
        if filename_match:
            title = filename_match.group(1).replace('.md', '')

        # 清理响应文本，移除文件名注释
        document = re.sub(r'<!--\s*建议文件名：.+?\s*-->', '', response_text).strip()

        return {
            "success": True,
            "document": document,
            "title": title,
            "error": None
        }

    def _resolve_model_for_task(self, selected_model_id, has_multimodal_input=False):
        """
        模型路由：
        - 视觉模型(qwen-vl-*) + 无多模态输入 => 回退文本模型
        - 视觉模型(qwen-vl-*) + 有多模态输入 => 保持视觉模型
        - 文本模型 => 直接使用
        """
        candidate = (selected_model_id or "").strip()
        if not candidate:
            candidate = self.model

        if self._is_vision_model(candidate) and not has_multimodal_input:
            fallback = getattr(settings, "QWEN_MODEL", "qwen-plus") or "qwen-plus"
            # 避免配置仍为视觉模型，兜底到 qwen-plus
            if self._is_vision_model(fallback):
                fallback = "qwen-plus"
            logger.warning(
                "模型 %s 不适用于文本任务，自动回退到 %s",
                candidate,
                fallback,
            )
            return fallback

        return candidate

    def _is_vision_model(self, model_id):
        return (model_id or "").strip().startswith("qwen-vl-")

    def _has_multimodal_input(self, conversation_history=None, latest_attachment_path=None):
        return self._history_has_supported_modal_attachments(conversation_history) or self._is_supported_modal_attachment(
            latest_attachment_path
        )

    def _history_has_supported_modal_attachments(self, conversation_history=None):
        for msg in conversation_history or []:
            if self._is_supported_modal_attachment(msg.get("attachment_path")):
                return True
        return False

    def _is_same_as_last_user_message(self, conversation_history, user_content, latest_attachment_path):
        if not conversation_history:
            return False
        last_msg = conversation_history[-1]
        if last_msg.get("role") != "user":
            return False

        last_content = (last_msg.get("content") or "").strip()
        current_content = (user_content or "").strip()
        if last_content != current_content:
            return False

        last_attachment = self._normalize_attachment_path(last_msg.get("attachment_path"))
        current_attachment = self._normalize_attachment_path(latest_attachment_path)
        return last_attachment == current_attachment

    def _build_message_content(self, text, attachment_path, use_multimodal):
        normalized_text = (text or "").strip()
        normalized_attachment_path = self._normalize_attachment_path(attachment_path)

        if use_multimodal and normalized_attachment_path:
            modal_block = self._build_modal_content_block(normalized_attachment_path)
            if modal_block:
                content_blocks = []
                if normalized_text:
                    content_blocks.append({"text": normalized_text})
                content_blocks.append(modal_block)
                return content_blocks

        return self._build_text_fallback_content(normalized_text, normalized_attachment_path)

    def _build_text_fallback_content(self, text, attachment_path):
        if text and attachment_path:
            filename = os.path.basename(attachment_path)
            return f"{text}\n\n（用户上传了附件：{filename}）"
        if attachment_path:
            filename = os.path.basename(attachment_path)
            return f"用户上传了附件：{filename}"
        return text

    def _normalize_attachment_path(self, attachment_path):
        if not attachment_path:
            return None
        path = str(attachment_path).strip()
        if not path:
            return None
        return path if os.path.exists(path) else None

    def _get_attachment_mime_type(self, attachment_path):
        mime_type, _ = mimetypes.guess_type(attachment_path)
        return (mime_type or "").lower()

    def _is_supported_modal_attachment(self, attachment_path):
        normalized = self._normalize_attachment_path(attachment_path)
        if not normalized:
            return False
        mime_type = self._get_attachment_mime_type(normalized)
        return mime_type.startswith("image/") or mime_type.startswith("video/") or mime_type.startswith("audio/")

    def _build_modal_content_block(self, attachment_path):
        mime_type = self._get_attachment_mime_type(attachment_path)
        data_url = self._encode_attachment_as_data_url(attachment_path)
        if mime_type.startswith("image/"):
            return {"image": data_url}
        if mime_type.startswith("video/"):
            return {"video": data_url}
        if mime_type.startswith("audio/"):
            return {"audio": data_url}
        return None

    def _encode_attachment_as_data_url(self, attachment_path):
        mime_type = self._get_attachment_mime_type(attachment_path)
        if not mime_type:
            mime_type = "application/octet-stream"
        with open(attachment_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    def _extract_response_text(self, response_data):
        if isinstance(response_data, dict):
            if "choices" in response_data and response_data["choices"]:
                message = response_data["choices"][0].get("message", {})
                content = message.get("content", "")
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("text"):
                            parts.append(str(block["text"]))
                    joined = "\n".join(parts).strip()
                    if joined:
                        return joined
                elif content is not None:
                    text_content = str(content).strip()
                    if text_content:
                        return text_content

            text_field = response_data.get("text")
            if text_field is not None:
                text_value = str(text_field).strip()
                if text_value:
                    return text_value
            return str(response_data)
        if response_data is None:
            return ""
        return str(response_data)


analyzer = RequirementAnalyzer()
