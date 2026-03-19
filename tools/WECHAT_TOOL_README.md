# 微信消息发送工具

## ⚠️ 权限要求

要让此工具正常工作，需要在 macOS 中授予以下权限：

### 1. 辅助功能权限

1. 打开 **系统设置** > **隐私与安全性** > **辅助功能**
2. 点击 `+` 添加以下应用：
   - **终端** (Terminal)
   - **Python** (如果使用 Python 运行)
   - 或者你使用的任何终端应用（如 iTerm2）
3. 确保开关已打开 ✅

### 2. 辅助功能权限详细说明

在 **辅助功能** 设置中，确保授予以下权限：

- ✅ **控制您的计算机** - 允许模拟键盘输入
- ✅ **观察您的屏幕** - 允许读取 UI 元素
- ✅ **发送按键** - 允许模拟键盘事件

### 3. 重启终端

添加权限后，**必须重启终端应用**才能生效。

---

## 使用方法

### 基本用法

```bash
# 发送消息给联系人 "in"
python3 tools/wechat_sender.py --contact "in" --message "你好"

# 简单模式（假设聊天窗口已打开）
python3 tools/wechat_sender.py --contact "in" --message "你好" --simple

# JSON 输出（便于程序调用）
python3 tools/wechat_sender.py --contact "in" --message "你好" --json
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `-c, --contact` | 联系人名称（必填） |
| `-m, --message` | 消息内容（必填） |
| `--simple` | 简单模式：假设聊天窗口已打开 |
| `--json` | 以 JSON 格式输出结果 |

---

## 工作原理

1. **检查微信运行状态** - 确认微信是否已启动
2. **激活微信窗口** - 将微信带到前台
3. **搜索联系人** - 在搜索框中输入联系人名称
4. **发送消息** - 在消息输入框中输入并发送

---

## 故障排除

### 问题 1: "osascript 不允许辅助访问"

**解决方案**: 
- 检查 系统设置 > 隐私与安全性 > 辅助功能
- 确保终端/Python 已添加并启用
- 重启终端应用

### 问题 2: "osascript 不允许发送按键"

**解决方案**:
- 这是 macOS 的安全限制
- 尝试在 辅助功能 设置中找到更详细的权限选项
- 或者使用 **简单模式** 并手动打开聊天窗口

### 问题 3: 搜索联系人失败

**可能原因**:
- 微信 UI 结构发生变化
- 联系人名称不匹配

**解决方案**:
- 使用 `--simple` 模式并手动打开聊天窗口
- 确保联系人名称完全匹配（包括空格和特殊字符）

### 问题 4: 消息发送失败

**解决方案**:
- 确保微信窗口未被最小化
- 确保目标聊天窗口已打开（简单模式）
- 检查消息内容是否包含特殊字符

---

## 替代方案

如果 AppleScript 方案无法工作，可以考虑：

### 方案 1: 使用微信快捷键手动发送

```bash
# 创建一个快捷指令，手动触发
osascript -e 'tell application "WeChat" to activate'
# 然后手动操作...
```

### 方案 2: 使用第三方工具

- **Keyboard Maestro** - 强大的 macOS 自动化工具
- **Hammerspoon** - Lua 脚本的自动化工具
- **BetterTouchTool** - 支持复杂的自动化流程

### 方案 3: 使用微信 API（需要企业微信）

如果是企业微信，可以使用官方 API 发送消息。

---

## 安全说明

⚠️ **重要**: 此工具需要较高的系统权限，请确保：

1. 只在可信的环境中使用
2. 不要授予未知脚本权限
3. 定期审查已授权的辅助功能应用
4. 使用后可以考虑移除权限

---

## 技术细节

### AppleScript UI Scripting

```applescript
tell application "System Events"
    tell process "WeChat"
        set frontmost to true
        keystroke "v" using command down
        keystroke return
    end tell
end tell
```

### 微信 UI 层级结构

```
Window 1
├── Splitter Group 1
│   ├── Group 1 (聊天列表)
│   │   └── Scroll Area 1
│   │       └── Text Field 1 (搜索框)
│   └── Group 1 (聊天窗口)
│       └── Scroll Area 2
│           └── Text Field 1 (消息输入框)
```

---

## 更新日志

- **v1.0** - 初始版本，支持基本的消息发送功能
- **v1.1** - 添加简单模式和剪贴板备用方案
- **v1.2** - 改进错误处理和权限检测
