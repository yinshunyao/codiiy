# 运行说明

## 1. 环境要求
1. Python 3.10 及以上
2. 操作系统：macOS / Linux / Windows（命令示例以 macOS/Linux 为主）

## 2. 安装依赖
在项目目录 `core` 下执行：

```bash
python3 -m venv .venv
python3 -m pip install --user -r requirements.txt
```

## 3. 初始化数据库
在 `core` 下执行：

```bash
python manage.py migrate
```

说明：
1. 默认数据库为 SQLite，文件位置：`core/db.sqlite3`
2. 首次迁移后会自动初始化默认管理员账号（仅用户表为空时）：
- 用户名：`admin`
- 密码：`123456`

## 4. 项目目录参数（新增）
系统根目录默认是 `core` 的上一级目录；可在 Django 启动前显式覆盖。

### 4.1 `manage.py` 参数方式

在仓库根目录执行：

```bash
python core/manage.py runserver --project-dir /absolute/path/to/project_root
```

也支持相对路径（相对于默认系统根目录）：

```bash
python core/manage.py runserver --project-dir projects/demo
```

### 4.2 WSGI / ASGI 环境变量方式

```bash
export CODIIY_PROJECT_ROOT=/absolute/path/to/project_root
```

未设置 `CODIIY_PROJECT_ROOT` 且未传 `--project-dir` 时，自动使用默认值：`core` 的上一级目录。

## 5. 统一命令文件运行（macOS / Ubuntu）
在 `core` 下使用 `manage.sh`，脚本会自动完成以下动作：
1. 检查 `python3`
2. 不存在 `.venv` 时自动创建虚拟环境
3. 依据 `requirements.txt` 哈希自动判断是否需要安装依赖（安装到系统 Python 用户目录）
4. 使用系统 `python3` 启动 `manage.py`（不依赖激活虚拟环境）

首次执行前先赋予可执行权限：

```bash
chmod +x manage.sh
```

### 5.1 默认启动（开发环境）

```bash
./manage.sh
```

默认访问地址：`http://127.0.0.1:8000/`
说明：日常启动时，若 `requirements.txt` 未变化，不会重复安装依赖。

### 5.2 指定 Django 命令

```bash
./manage.sh migrate
./manage.sh createsuperuser
./manage.sh runserver 0.0.0.0:8000
./manage.sh runserver --project-dir /absolute/path/to/project_root
```

### 5.3 脚本参数

```bash
# 首次初始化环境并退出（不执行 Django 命令）
./manage.sh --init

# 强制重装依赖后再执行命令
./manage.sh --reinstall migrate

# 跳过依赖检查（已确认环境可用时）
./manage.sh --skip-install runserver
```

### 5.4 配置 QWEN_API_KEY（可选）
方式一：临时注入（仅本次命令生效）

```bash
QWEN_API_KEY=你的key ./manage.sh
```

方式二：写入当前终端环境

```bash
export QWEN_API_KEY=你的key
./manage.sh
```

## 6. 常用页面
1. 登录页：`/accounts/login/`
2. 会话列表：`/sessions/`
3. 新建会话：`/sessions/new/`
4. 修改密码：`/accounts/password/change/`
5. 管理后台：`/admin/`

## 7. 常见问题
1. 提示 `No module named django`
- 先执行 `./manage.sh --reinstall` 让脚本重建依赖，或手动执行 `python3 -m pip install --user -r requirements.txt`
2. 默认管理员无法登录
- 确认是否首次迁移前已存在用户；如已存在用户，初始化逻辑不会重复创建默认 admin

## 8. 本地屏幕理解组件（control/observe）
1. 安装依赖（示例）：

```bash
pip install mss pillow vllm
```

2. 启动本地 vLLM（Qwen2-VL-0.5B）：

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2-VL-0.5B-Instruct \
  --served-model-name qwen2-vl-0.5b \
  --max-model-len 4096 \
  --dtype auto \
  --gpu-memory-utilization 0.85
```

3. Python 调用（在仓库根目录）：

```python
from agents.observe import understand_current_screen

result = understand_current_screen(json_mode=True)
print(result)
```
