# Codiiy

Codiiy 是一个本地运行的 AI 自动化助手平台，通过网页界面与 AI 对话，让 AI 帮你完成截图理解、文件操作、消息发送等自动化任务。
![main.png](main.png)
---

## 系统架构简述

```
浏览器（你的操作界面）
      ↕
  Django 服务（core/）       ← 网页、账号、会话管理
      ↕
  AI 执行引擎（agents/）     ← 接收指令、推理、调用工具
      ↕
  组件能力层（component/）   ← 截图理解 / 文件操作 / 消息发送 / AI 对话
```

主要能力：
- **屏幕理解**：截图并分析当前画面内容(规划中)
- **文件操作**：读取、检索本地文件
- **消息通知**：发送钉钉 / 企业微信 / 飞书消息
- **AI 对话**：基于 Qwen 模型进行文本生成与对话

---

## 环境要求

- Python 3.10 及以上
- macOS / Linux（Windows 需自行适配）

---

## 快速启动

### 第一步：初始化环境（仅首次需要）

```bash
./manage.sh --init
```

脚本会自动创建虚拟环境并安装所有依赖到 `.venv`，完成后提示"初始化完成"。

### 第二步：初始化数据库（仅首次需要）

```bash
./manage.sh migrate
```

完成后会自动创建默认管理员账号：
- 用户名：`admin`
- 密码：`123456`

### 第三步：启动服务

```bash
./manage.sh
```

启动后访问：[http://127.0.0.1:8000/](http://127.0.0.1:8000/)

> 每次启动时，若依赖未变化，脚本会自动跳过安装步骤，直接用 `.venv/bin/python` 启动服务。

---

## 常用页面

| 页面 | 地址 |
| :--- | :--- |
| 登录 | `/accounts/login/` |
| 会话列表 | `/sessions/` |
| 新建会话 | `/sessions/new/` |
| 修改密码 | `/accounts/password/change/` |
| 管理后台 | `/admin/` |

---

## 配置 AI 密钥（可选）

如需使用 Qwen AI 能力，需配置 API Key：

```bash
# 临时生效（仅本次启动）
QWEN_API_KEY=你的key ./manage.sh

# 永久生效（写入终端配置后重新打开终端）
export QWEN_API_KEY=你的key
```

---

## 常见问题

**提示 `No module named django`**

重新安装依赖：
```bash
./manage.sh --reinstall
```

**默认管理员无法登录**

若数据库中已有其他用户，初始化时不会重复创建 `admin`，可在管理后台手动创建或重置密码。

**想指定数据目录**

```bash
./manage.sh runserver --project-dir /你的/项目/路径
```
