# create_tool 工具脚手架

description: 根据外部传入的内容创建工具目录及关键文件，统一复用 file_path_tool 和 file_operator_tool 执行目录创建与文件写入。

支持操作系统: all

## 功能说明
- 创建工具目录（默认在 `tools/` 下）。
- 写入 `__init__.py`、`README.md` 和主功能代码文件。
- 创建成功后自动写入工具源标记：`自生成`。
- 支持 `overwrite` 控制：默认不覆盖已有文件。
- 所有目录与文件写入统一走已有工具，不直接操作组件或重复实现底层逻辑。

## 输入与输出
- 入口方法：`create_tool(...)`
- 关键输入：
  - `folder_name`：工具目录名（仅允许字母/数字/下划线，且不能以数字开头）。
  - `init_content`：写入 `__init__.py` 的内容。
  - `readme_content`：写入 `README.md` 的内容。
  - `code_file_name`：主功能代码文件名（如 `my_tool.py`）。
  - `code_content`：主功能代码内容。
  - `overwrite`：是否覆盖已有文件，默认 `False`。
- 返回结构：
  - 成功：`{"success": True, "data": {...}}`
  - 失败：`{"success": False, "error": "..."}`

## 依赖组件
- 本 tool 不直接调用组件 API。
- 本 tool 通过以下工具完成落盘能力：
  - `tools.file_path_tool.FilePathTool`
  - `tools.file_operator_tool.FileOperatorTool`

## 使用示例
```python
from tools.create_tool import CreateTool

tool = CreateTool(auto_install=False)
result = tool.create_tool(
    folder_name="demo_tool",
    init_content="from .demo_tool import DemoTool\n\n__all__ = ['DemoTool']\n",
    readme_content="# demo_tool\n\ndescription: 示例工具。\n\n支持操作系统: all\n",
    code_file_name="demo_tool.py",
    code_content="class DemoTool:\n    pass\n",
    overwrite=False,
)
print(result)
```

## 边界说明
- `folder_name` 非法时会直接失败，不创建任何文件。
- `code_file_name` 仅允许单个 `.py` 文件名，不允许目录分隔符。
- `overwrite=False` 时若任一目标文件已存在将返回失败，避免误覆盖。
- 新工具目录固定创建在当前仓库 `tools/` 下（与本工具目录同级），不支持通过入参写到其他目录。

