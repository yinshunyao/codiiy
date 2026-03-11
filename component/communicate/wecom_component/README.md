# wecom_component

企业微信机器人文本消息发送组件。

## 对外函数
- `component.communicate.send_wecom_text`

## 参数来源规则
1. 函数显式传参优先。
2. 未显式传入时，若提供 `config_name`，则从 Django `CommunicationChannelConfig` 中读取 `provider=wecom` 的配置。

## 必要配置参数
- `webhook_url`
