# macos_terminal_component

## 功能
- 创建 macOS shell 终端会话（session）
- 在会话内执行命令并返回本次输出
- 获取会话累计输出（支持 offset 增量读取）
- 关闭会话并释放进程资源

## 设计要点
- 以 `session_id` 表示终端对象，复用同一 shell 子进程，保证上下文连续（例如 `cd` 后后续命令仍在新目录）。
- 创建会话通过 `shell_mode` 选择 shell，默认 `zsh`，支持 `zsh`、`bash`、`csh`、`dash`、`ksh`、`sh`、`tcsh`。
- 命令执行采用唯一结束标记解析退出码，返回 `exit_code` 与本次新增输出。
- 组件仅支持 macOS（darwin）。

## 导出函数
- `component.handle.create_macos_terminal_session`
- `component.handle.run_macos_terminal_command`
- `component.handle.get_macos_terminal_output`
- `component.handle.close_macos_terminal_session`

## 依赖
见同目录 `requirements.txt`（当前仅使用 Python 标准库）。
