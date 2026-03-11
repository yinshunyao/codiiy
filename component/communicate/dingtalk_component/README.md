# dingtalk_component

钉钉机器人文本消息发送组件。

## 对外函数
- `component.communicate.send_dingtalk_text`

## 参数来源规则
1. 函数显式传参优先。
2. 未显式传入时，若提供 `config_name`，则从 Django `CommunicationChannelConfig` 中读取 `provider=dingtalk` 的配置。

## 必要配置参数
- `webhook_url`

## 可选配置参数
- `secret`（启用签名时使用）
