# 背景

- 当前平台已实现 adapter 基础模块（`codiiy/adapter/`），包含 `ProcessAdapter`（通用命令行）和 `HttpAdapter`（HTTP 接口），但尚未针对 Cursor Agent CLI 做专门适配
- 用户反馈"平台的 Cursor 好像无法使用"——当前 `ProcessAdapter` 虽然可以启动外部命令，但缺少 Cursor 特有的流式 JSON 输出解析、会话恢复（`--resume`）、模型选择、自动信任（`--yolo`）、指令文件注入、Skill 注入等关键能力
- Paperclip 项目已有成熟的 Cursor 本地适配器实现（`paperclip/packages/adapters/cursor-local`），使用 TypeScript 编写，可作为功能参考
- Cursor Agent CLI（命令名 `agent`）已在本机安装（`/Users/shunyaoyin/.local/bin/agent`），支持 `--output-format stream-json` 输出结构化事件流

# 目标

1. 在 `codiiy/adapter/` 中新建 `cursor_local/` 子目录，实现 Cursor Local 适配器，使伙伴（CompanionProfile）可通过 Cursor Agent CLI 执行任务
2. 支持 Cursor 特有的流式 JSON 事件解析，提取会话 ID、token 用量、执行摘要和错误信息
3. 支持 Cursor 会话恢复（`--resume`），允许跨次执行保持上下文
4. 支持模型选择、执行模式（plan/ask）、指令文件注入和自动信任（`--yolo`）等配置项
5. 将 Cursor Local 适配器注册到全局 `AdapterRegistry`，使前端下拉菜单可选

# 要求

## 功能性要求

### 适配器核心执行

1. `CursorLocalAdapter` 继承 `BaseAdapter`，`adapter_type = "cursor_local"`，`label = "Cursor CLI (本地)"`
2. `execute()` 方法通过 `subprocess` 调用 `agent` 命令（可通过 `config.command` 覆盖），使用 `-p --output-format stream-json --workspace <cwd>` 参数
3. prompt 通过 stdin 管道传入 Cursor 进程
4. 支持从配置中读取 `model`（默认 `auto`）、`mode`（`plan` / `ask`，可选）、`extra_args`（额外 CLI 参数）
5. 若 `extra_args` 中未包含 `--trust`、`--yolo` 或 `-f`，则自动追加 `--yolo` 以跳过交互确认

### 流式 JSON 输出解析

6. 解析 Cursor 的 stream-json 输出（每行一个 JSON 事件），提取以下信息：
   - `session_id`：从 `system.init` 事件或 `result` 事件中提取
   - `usage`：`input_tokens`、`cached_input_tokens`、`output_tokens` 的累计值
   - `cost_usd`：累计费用
   - `summary`：从 `assistant` 类型事件收集文本组成执行摘要
   - `error_message`：从 `error` 或 `result.is_error` 事件提取错误信息
7. 支持处理前缀格式行（如 `stdout: {...}`），自动去除前缀后解析 JSON

### 会话管理

8. 执行结果中返回 `session_id` 和相关参数（`cwd`、`workspace_id` 等），供上层存储
9. 恢复会话时，若上次保存的 session `cwd` 与本次不一致，则放弃恢复并记录日志
10. 若使用 `--resume` 恢复失败（Cursor 返回"unknown session"类错误），自动以新会话重试一次

### 指令文件注入

11. 支持 `config.instructions_file_path` 配置项，启动前读取该文件内容并拼接到 prompt 前面
12. 拼接时附加路径提示：`The above agent instructions were loaded from <path>. Resolve any relative file references from <dir>.`

### 环境检测

13. `test_environment()` 方法检测：
    - 工作目录是否存在且可访问
    - `agent` 命令是否可执行（通过 `shutil.which`）
    - 可选的 hello probe：执行 `agent -p --mode ask --output-format json --yolo "Respond with hello."` 验证 Cursor CLI 可正常工作

### 目录组织

14. 适配器代码放在独立子目录 `codiiy/adapter/cursor_local/` 中，包含 `__init__.py`、核心执行逻辑和流式解析逻辑
15. 在 `codiiy/adapter/registry.py` 的自动注册函数中注册 `CursorLocalAdapter`

## 非功能性要求

1. 适配器模块与 Paperclip 无运行时依赖，仅参考其设计思路，代码完全独立实现
2. 流式解析容错处理：非 JSON 行跳过，缺失字段使用默认值，不因单行解析失败中断整体流程
3. `execute()` 方法必须处理 `subprocess.TimeoutExpired`、`FileNotFoundError` 等异常，返回结构化错误而非抛异常
4. Cursor 环境检测的 hello probe 超时设置为 45 秒，避免阻塞过久

# 当前工作项

（暂无）

# 已完成工作项

## 需求
- Cursor Local 适配器实现 — 已完成 `adapter/cursor_local/` 模块、注册、测试与文档同步。

## 问题
（暂无）
