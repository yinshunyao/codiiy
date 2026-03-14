# mac arm架构下conda排查
## 输入命令
```shell
python -c "import platform; print('Machine:', platform.machine(), '| Processor:', platform.processor())"
```

## 正确输出（ARM64 原生）：
```shell
Machine: arm64 | Processor: arm
```

## 错误输出（Rosetta / x86_64）：
```shell
Machine: x86_64 | Processor: i386
```

# llama-python
```shell
# 1. 卸载现有版本（避免冲突）
pip uninstall llama-cpp-python

# 2. 安装必要依赖（确保使用 ARM64 的 Python 环境）
# 如果你用的是 conda，请确认当前环境是 arm64：
#   python -c "import platform; print(platform.machine())"  # 应输出 'arm64'

# 3. 从源码安装，并启用 Metal 加速（Apple GPU）
CMAKE_ARGS="-DLLAMA_METAL=on" pip install --no-cache-dir llama-cpp-python
```