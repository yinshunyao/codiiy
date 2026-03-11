# ComponentCallTool

## 功能概述

`ComponentCallTool` 是面向 `component` 的通用工具封装，支持：

1. 调用前按函数所属组件自动检查对应 `requirements.txt` 依赖；
2. 可选运行时安装缺失依赖（默认关闭，建议部署时预装）；
3. 查询 `component` 整体信息（自动读取 `component/**/README.json`）；
4. 通过 `control_call` 调用指定函数路径；
5. 统一返回字典结构：`success`、`data`、`error`。

## 目录结构

- `control_call_tool.py`：工具主实现
- `__init__.py`：包导出
- `README.md`：使用说明

## 使用方式

```python
from tools.control_call_tool import ComponentCallTool

tool = ComponentCallTool(auto_install=False)

# 1) 查询 component 整体信息
info = tool.control_info()
print(info)

# 2) 调用特定函数（control_call）
result = tool.control_call(
    function_path="component.observe.understand_current_screen",
    kwargs={
        "prompt": "请描述当前屏幕内容。",
        "json_mode": True,
    },
)
print(result)
```

## API

### `ensure_dependencies(function_path)`
- 根据 `function_path` 映射到组件目录，检查并安装该组件 `requirements.txt` 中缺失依赖。

### `control_info()`
- 查询 `component` 全量模块信息与函数清单（基于各目录 `README.json`）。

### `control_call(function_path, kwargs=None)`
- 通过字符串路径调用 `component` 下函数，调用前自动执行依赖检查。

## 注意事项

1. `function_path` 必须以 `component.` 开头；
2. `control_info()` 依赖 `component/**/README.json` 的完整性；
3. 调用目录不维护依赖清单，依赖来源于组件目录；
4. 默认不执行运行时自动安装；如需启用可显式传入 `auto_install=True`，或设置环境变量 `COMPONENT_AUTO_INSTALL=1`；
5. 建议在非 root 用户 + 虚拟环境中运行，避免 `pip` 权限与目录可写问题。
