# file_operator_tool 文件操作工具

description: 基于组件调用统一提供文件读取与写入能力，覆盖创建、覆盖写、追加写、文本替换与检索，并支持写入场景父目录自动处理。

支持操作系统: all

## 功能说明
- 统一封装文件读取能力：`read_file`、`read_lines`、`search_keyword`、`search_regex`、`get_file_stats`。
- 统一封装文件写入能力：`create_file`、`write_file`、`append_file`、`replace_file_text`。
- 写入类接口默认支持父目录自动创建（`create_parent_dirs=True`），减少“目录不存在”导致的失败。
- 返回结构统一：成功 `{"success": True, "data": ...}`；失败 `{"success": False, "error": "..."}`。

## 依赖组件
本工具仅通过 `tools/component_call_tool.ComponentCallTool.control_call` 调用以下组件 API：

- `component.handle.read_file`
- `component.handle.read_lines`
- `component.handle.search_keyword`
- `component.handle.search_regex`
- `component.handle.get_file_stats`
- `component.handle.create_file`
- `component.handle.write_file`
- `component.handle.append_file`
- `component.handle.replace_file_text`

## 使用示例
```python
from tools.file_operator_tool import FileOperatorTool

tool = FileOperatorTool(auto_install=False)

write_result = tool.write_file(
    file_path="data/temp/demo/note.txt",
    content="hello\n",
)
print(write_result)

read_result = tool.read_file(file_path="data/temp/demo/note.txt")
print(read_result)
```

## 边界说明
- 工具层不直接读写系统 API，不绕过组件调用链路。
- 目录自动处理仅作用于写入类能力中的父目录创建，不负责目录清理与删除。
- 文本替换依赖原文件存在；`old_text` 为空会返回失败。
- 文件路径会先做工具层归一化：支持去除 `@` 前缀，且相对路径统一按项目根目录解析（不依赖当前进程工作目录）；兼容 `@core/doc/...` 映射到项目 `doc/...`。

