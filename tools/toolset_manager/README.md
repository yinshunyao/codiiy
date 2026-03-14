# toolset_manager（兼容导入壳）

`toolset_manager` 已降级为兼容导入壳，主实现迁移到 `tools/manager.py`。

推荐导入方式：

```python
from tools.manager import list_toolsets, set_toolset_enabled
```

兼容导入（仍可用）：

```python
from tools.toolset_manager import list_toolsets, set_toolset_enabled
```
