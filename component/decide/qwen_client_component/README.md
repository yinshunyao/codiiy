# qwen_client_component

Qwen 客户端组件，封装 dashscope SDK 的文本与多模态调用能力。

## 对外函数
- `component.decide.create_qwen_client`
- `component.decide.chat_completion`
- `component.decide.text_generation`

## 说明
1. `chat_completion` 与 `text_generation` 返回统一结构：`success/data` 或 `success/error`。
2. 当消息包含 `image/video/audio/file` 块时，优先尝试使用 `MultiModalConversation.call`。
3. 组件依赖由当前目录 `requirements.txt` 管理。
4. 组件参数采用组件级共享配置策略，默认读取配置名 `default` 下的 `api_key`。
