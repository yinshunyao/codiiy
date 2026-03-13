# codiiy

面向本地自动化与 AI 协作的 Python 工程，当前以 Django 管理端 + 组件化能力层为核心。

## 当前实现概览

- `core/`：Django 工程，提供组件管理、配置与测试页面。
- `component/`：组件统一入口与能力实现，支持按 `function_path` 路由调用。
- `control/agents/`：ReAct 执行引擎（支持 Thought -> Action -> Observation 循环）。
- `tools/`：面向 `component` 的工具封装（如统一调用与依赖检查）。
- `data/`：运行期数据目录（`cache`、`database`、`roles`、`tasks`、`temp`）。
- `test/`：测试代码目录，按被测目录镜像组织。

## 组件能力（已落地）

- **observe**：截图与屏幕理解
- **handle**：文件读取/检索、鼠标动作、Python 包管理
- **communicate**：钉钉/企业微信/飞书文本消息发送
- **decide**：Qwen 客户端与文本生成/对话能力

## 快速启动（开发）

```bash
cd core
./manage.sh --init
./manage.sh runserver
```

说明：
- `manage.sh` 会创建 `.venv` 并按 `requirements.txt` 自动安装/更新依赖。
- 不传 Django 命令时，默认执行 `python3 manage.py runserver`。

## 参考文档

- 设计与运维文档：`doc/`
- 组件索引：`component/component_index.json`
- 组件统一说明：`component/README.json`