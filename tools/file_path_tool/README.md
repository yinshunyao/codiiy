# file_path_tool 路径管理工具

description: 提供文件/文件夹新建、重命名、移动能力，默认支持目标目录自动处理；不提供删除能力。

支持操作系统: all

## 功能说明
- 新建目录：`create_directory`，支持按需自动创建父目录。
- 新建文件：`create_file`，复用 `component.handle.create_file`，支持按需自动创建父目录。
- 重命名：`rename_path`，支持文件或目录改名（同目录内改名）。
- 移动：`move_path`，支持文件或目录移动到目标目录，目标目录可按需自动创建。
- 高危边界：本工具不提供删除接口（文件删除、目录删除、递归删除均禁止）。

## 输入与输出
- 统一返回：
  - 成功：`{"success": True, "data": {...}}`
  - 失败：`{"success": False, "error": "..."}`
- 关键返回字段：
  - `action`：如 `created`、`renamed`、`moved`。
  - `source_path` / `target_path`：重命名和移动操作的路径信息。
  - `path_type`：新建时区分 `directory`。

## 依赖组件
- `create_file` 通过 `tools/component_call_tool.ComponentCallTool.control_call` 调用：
  - `component.handle.create_file`
- 其余目录重命名/移动能力为本工具本地路径编排逻辑，不直接调用组件 API。

## 使用示例
```python
from tools.file_path_tool import FilePathTool

tool = FilePathTool(auto_install=False)

tool.create_directory("data/temp/demo")
tool.create_file("data/temp/demo/hello.txt", content="hello\n")
tool.rename_path("data/temp/demo/hello.txt", "hello_v2.txt")
tool.move_path("data/temp/demo/hello_v2.txt", "data/temp/archive")
```

## 边界说明
- `rename_path` 的 `new_name` 仅允许传名称，不允许包含路径分隔符。
- `move_path` 默认不覆盖同名目标路径；若目标已存在会返回失败。
- 不提供任何删除能力，避免误删风险。

