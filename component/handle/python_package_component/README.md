# python_package_component

## 功能
- 查询 Python 依赖包安装状态与版本信息
- 安装指定 Python 依赖包（支持指定版本与升级）
- 卸载指定 Python 依赖包

## 导出函数
- `component.handle.query_python_package`
- `component.handle.install_python_package`
- `component.handle.uninstall_python_package`

## 说明
- 通过 `sys.executable -m pip` 调用当前运行环境的 pip，避免跨解释器安装。
- 适用于当前 Python 运行环境，不会自动切换虚拟环境。

## 依赖
见同目录 `requirements.txt`（当前仅使用 Python 标准库）。
