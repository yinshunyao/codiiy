# 运行说明

## 1. 环境要求
1. Python 3.10 及以上
2. 操作系统：macOS / Linux / Windows（命令示例以 macOS/Linux 为主）

## 2. 安装依赖
在项目目录 `core/code` 下执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../doc/99-ops/requirements.txt
```

## 3. 初始化数据库
在 `core/code` 下执行：

```bash
python manage.py migrate
```

说明：
1. 默认数据库为 SQLite，文件位置：`core/code/db.sqlite3`
2. 首次迁移后会自动初始化默认管理员账号（仅用户表为空时）：
- 用户名：`admin`
- 密码：`123456`

## 4. 启动服务
在 `core/code` 下执行：

```bash
# QWEN_API_KEY 更新
QWEN_API_KEY=sk-12aa3ad61301458c80b839736224a856   python manage.py runserver
```

默认访问地址：`http://127.0.0.1:8000/`

## 5. 常用页面
1. 登录页：`/accounts/login/`
2. 会话列表：`/sessions/`
3. 新建会话：`/sessions/new/`
4. 修改密码：`/accounts/password/change/`
5. 管理后台：`/admin/`

## 6. 常见问题
1. 提示 `No module named django`
- 先激活虚拟环境，再执行 `pip install -r ../doc/99-ops/requirements.txt`
2. 默认管理员无法登录
- 确认是否首次迁移前已存在用户；如已存在用户，初始化逻辑不会重复创建默认 admin
