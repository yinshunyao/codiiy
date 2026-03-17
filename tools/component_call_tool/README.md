# ComponentCallTool

## 功能概述

`ComponentCallTool` 是面向 `component` 的通用工具封装，支持：

1. 调用前按函数所属组件自动检查对应 `requirements.txt` 依赖；
2. 可选运行时安装缺失依赖（默认关闭，建议部署时预装）；
3. 查询 `component` 整体信息（自动读取 `component/**/README.json`）；
4. 通过 `control_call` 调用指定函数路径；
5. 统一返回字典结构：`success`、`data`、`error`。
6. 查询/设置组件启停状态（`get_component_enabled`、`set_component_enabled`）。
7. 作为跨模块访问 `component` 的唯一标准入口，供非组件模块调用。
8. 调用前自动按目标函数签名过滤无效参数（避免“unexpected keyword argument”中断流程）。
9. 调用前统一校验组件必需系统权限（`system_permission_schema.required=true`），未确认时拒绝执行。

支持操作系统：macos, linux, windows

## 目录结构

- `component_call_tool.py`：工具主实现
- `__init__.py`：包导出
- `README.md`：使用说明

## 使用方式

```python
from tools.component_call_tool import ComponentCallTool

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

## 输入与输出约定

- 输入：
  - `control_info()`：无参数。
  - `ensure_dependencies(function_path)`：`function_path` 必须为组件函数全路径字符串。
  - `control_call(function_path, kwargs=None)`：`function_path` 为组件函数路径，`kwargs` 为字典参数。
- 成功返回：
  - `{"success": True, "data": {...}}`
- 失败返回：
  - `{"success": False, "error": "错误信息"}`

## 依赖组件

- 本工具内部通过 `component.call_by_path` 执行组件函数调用。
- 非组件模块如果需要查询或调用组件，必须通过本工具，不应直接调用 `component` 代码。

## API

### `ensure_dependencies(function_path: str) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `function_path` | `str` | 必填 | 组件函数全路径，必须以 `component.` 开头。 |

返回 `data` 字段：`checked_component`、`installed_dependencies`、`missing_dependencies`（按实现返回）。

### `control_info() -> Dict`

无参数。

返回 `data` 字段：组件清单及函数元信息（来自 `component/**/README.json` 聚合结果）。

### `control_call(function_path: str, kwargs: Optional[Dict] = None) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `function_path` | `str` | 必填 | 目标组件函数路径，如 `component.observe.understand_current_screen`。 |
| `kwargs` | `Optional[Dict]` | `None` | 传递给目标函数的关键字参数。 |

返回 `data` 字段：目标函数原始返回结果；当权限不足时，失败结果中包含 `missing_permissions`。

### `get_component_enabled(component_key: str) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `component_key` | `str` | 必填 | 组件 key（通常是组件目录名）。 |

返回 `data` 字段：`component_key`、`enabled`。

### `set_component_enabled(component_key: str, enabled: bool) -> Dict`

| 参数 | 类型 | 默认值 | 说明 |
|:---|:---|:---|:---|
| `component_key` | `str` | 必填 | 组件 key（通常是组件目录名）。 |
| `enabled` | `bool` | 必填 | 是否启用该组件。 |

返回 `data` 字段：`component_key`、`enabled`、`updated`（按实现返回）。

### `call_control_function(function_path: str, kwargs: Optional[Dict] = None) -> Dict`

兼容旧方法名，参数与 `control_call` 完全一致。

## 注意事项

1. `function_path` 必须以 `component.` 开头；
2. `control_info()` 依赖 `component/**/README.json` 的完整性；
3. 调用目录不维护依赖清单，依赖来源于组件目录；
4. 默认不执行运行时自动安装；如需启用可显式传入 `auto_install=True`，或设置环境变量 `COMPONENT_AUTO_INSTALL=1`；
5. 建议在非 root 用户 + 虚拟环境中运行，避免 `pip` 权限与目录可写问题；
6. 本工具只负责组件能力查询与调用，不负责实现具体业务流程编排。
7. 当 Django/ORM 或权限存储不可用时，权限检查按降级策略放行，避免因迁移未执行导致整体调用中断。
