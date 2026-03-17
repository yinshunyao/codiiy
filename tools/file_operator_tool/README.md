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

## API

### `read_file(file_path: str, encoding: str = "utf-8") -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `file_path` | `str` | 必填 | 文件路径，支持 `@` 前缀，相对路径基于项目根目录。 |
| `encoding` | `str` | `"utf-8"` | 文件编码。 |

返回 `data` 字段：`content`、`file_path`（按实现返回）。

### `read_lines(file_path: str, start_line: int, end_line: int, encoding: str = "utf-8") -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `file_path` | `str` | 必填 | 文件路径。 |
| `start_line` | `int` | 必填 | 起始行号（从 1 开始）。 |
| `end_line` | `int` | 必填 | 结束行号（包含）。 |
| `encoding` | `str` | `"utf-8"` | 文件编码。 |

返回 `data` 字段：`lines`、`content`、`start_line`、`end_line`（按实现返回）。

### `search_keyword(file_path: str, keyword: str, context_lines: int = 3, encoding: str = "utf-8", case_sensitive: bool = False) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `file_path` | `str` | 必填 | 文件路径。 |
| `keyword` | `str` | 必填 | 关键字。 |
| `context_lines` | `int` | `3` | 每个命中前后展示的上下文行数。 |
| `encoding` | `str` | `"utf-8"` | 文件编码。 |
| `case_sensitive` | `bool` | `False` | 是否区分大小写。 |

返回 `data` 字段：`matches`（每项通常含 `line_number`、`line`、`context`）。

### `search_regex(file_path: str, pattern: str, context_lines: int = 3, encoding: str = "utf-8") -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `file_path` | `str` | 必填 | 文件路径。 |
| `pattern` | `str` | 必填 | 正则表达式（Python `re` 语法）。 |
| `context_lines` | `int` | `3` | 每个命中前后展示的上下文行数。 |
| `encoding` | `str` | `"utf-8"` | 文件编码。 |

返回 `data` 字段：`matches`（结构同关键词检索）。

### `get_file_stats(file_path: str) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `file_path` | `str` | 必填 | 文件路径。 |

返回 `data` 字段：`size`、`line_count`、`created_at`、`modified_at`（按实现返回）。

### `create_file(file_path: str, content: str = "", encoding: str = "utf-8", create_parent_dirs: bool = True, overwrite: bool = False) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `file_path` | `str` | 必填 | 目标文件路径。 |
| `content` | `str` | `""` | 初始文件内容。 |
| `encoding` | `str` | `"utf-8"` | 文件编码。 |
| `create_parent_dirs` | `bool` | `True` | 是否自动创建父目录。 |
| `overwrite` | `bool` | `False` | 文件已存在时是否覆盖。 |

返回 `data` 字段：`file_path`、`action`、`written_bytes`（按实现返回）。

### `write_file(file_path: str, content: str, encoding: str = "utf-8", create_parent_dirs: bool = True) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `file_path` | `str` | 必填 | 目标文件路径。 |
| `content` | `str` | 必填 | 写入内容（全量覆盖）。 |
| `encoding` | `str` | `"utf-8"` | 文件编码。 |
| `create_parent_dirs` | `bool` | `True` | 是否自动创建父目录。 |

返回 `data` 字段：`file_path`、`action`、`written_bytes`（按实现返回）。

### `append_file(file_path: str, content: str, encoding: str = "utf-8", create_parent_dirs: bool = True) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `file_path` | `str` | 必填 | 目标文件路径。 |
| `content` | `str` | 必填 | 追加内容。 |
| `encoding` | `str` | `"utf-8"` | 文件编码。 |
| `create_parent_dirs` | `bool` | `True` | 是否自动创建父目录。 |

返回 `data` 字段：`file_path`、`action`、`written_bytes`（按实现返回）。

### `replace_file_text(file_path: str, old_text: str, new_text: str, encoding: str = "utf-8", count: int = -1) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `file_path` | `str` | 必填 | 目标文件路径。 |
| `old_text` | `str` | 必填 | 被替换文本，不能为空。 |
| `new_text` | `str` | 必填 | 替换后的文本。 |
| `encoding` | `str` | `"utf-8"` | 文件编码。 |
| `count` | `int` | `-1` | 替换次数，`-1` 表示全部替换。 |

返回 `data` 字段：`file_path`、`replaced_count`（按实现返回）。

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

