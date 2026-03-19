#!/usr/bin/env python3
"""
微信消息发送工具 - 通过 AppleScript 控制 macOS 微信应用

使用方法:
    python wechat_sender.py --contact "in" --message "你好"

注意：需要在 系统设置 > 隐私与安全性 > 辅助功能 中授予终端/Python 权限
"""

import argparse
import subprocess
import sys
import time
import json


def run_applescript(script: str, timeout_sec: int = 30) -> tuple[bool, str]:
    """执行 AppleScript 并返回结果"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout_sec
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "AppleScript 执行超时"
    except Exception as e:
        return False, str(e)


def check_assistive_access() -> bool:
    """检查是否有辅助功能权限"""
    script = '''
    tell application "System Events"
        return "ok"
    end tell
    '''
    success, _ = run_applescript(script)
    return success


def check_wechat_running() -> bool:
    """检查微信是否正在运行"""
    script = 'tell application "System Events" to count (every process whose name is "WeChat")'
    success, result = run_applescript(script)
    if success:
        try:
            count = int(result.strip())
            return count > 0
        except ValueError:
            return False
    return False


def send_message_simple(message: str) -> tuple[bool, str]:
    """
    简单模式：假设微信已打开且聊天窗口已选中，直接发送消息
    """
    # 转义消息中的特殊字符
    escaped_message = message.replace('"', '\\"').replace('\n', ' & return & ')
    
    script_template = '''
    tell application "System Events"
        tell process "WeChat"
            set frontmost to true
            delay 0.3
            
            try
                # 找到消息输入框
                set message_field to text field 1 of scroll area 2 of group 1 of splitter group 1 of window 1
                set value of message_field to "%s"
                delay 0.2
                
                # 按 Enter 发送
                keystroke return
                delay 0.3
                return "sent"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
    end tell
    '''
    script = script_template % escaped_message
    return run_applescript(script, timeout_sec=15)


def send_message_via_clipboard(message: str) -> tuple[bool, str]:
    """
    备用方案：通过剪贴板发送
    """
    # 先复制到剪贴板
    escaped_msg = message.replace('"', '\\"')
    script_copy = 'set the clipboard to "%s"' % escaped_msg
    success, _ = run_applescript(script_copy)
    if not success:
        return False, "无法复制到剪贴板"
    
    time.sleep(0.2)
    
    # 粘贴并发送
    script_paste = '''
    tell application "System Events"
        tell process "WeChat"
            set frontmost to true
            delay 0.3
            
            try
                # 粘贴
                keystroke "v" using command down
                delay 0.2
                
                # 发送
                keystroke return
                delay 0.3
                return "sent"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
    end tell
    '''
    return run_applescript(script_paste, timeout_sec=15)


def search_and_send(contact_name: str, message: str) -> tuple[bool, str]:
    """
    搜索联系人并发送消息
    """
    escaped_message = message.replace('"', '\\"').replace('\n', ' & return & ')
    escaped_contact = contact_name.replace('"', '\\"')
    
    # 使用 UI scripting 搜索
    script_template = '''
    tell application "WeChat"
        activate
    end tell
    
    delay 1
    
    tell application "System Events"
        tell process "WeChat"
            set frontmost to true
            delay 0.5
            
            try
                # 尝试找到搜索框并输入
                set search_field to text field 1 of scroll area 1 of group 1 of splitter group 1 of window 1
                set value of search_field to "%s"
                delay 1
                
                # 按回车选择
                keystroke return
                delay 0.5
                
                # 输入消息
                set message_field to text field 1 of scroll area 2 of group 1 of splitter group 1 of window 1
                set value of message_field to "%s"
                delay 0.2
                
                # 发送
                keystroke return
                delay 0.3
                return "sent"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
    end tell
    '''
    script = script_template % (escaped_contact, escaped_message)
    return run_applescript(script, timeout_sec=20)


def send_wechat_message(contact_name: str, message: str, simple_mode: bool = False) -> dict:
    """
    发送微信消息到指定联系人
    
    返回:
        dict: {success: bool, error: str, steps: list}
    """
    result = {
        "success": False,
        "error": "",
        "steps": [],
        "contact": contact_name,
        "message": message
    }
    
    # Step 0: 检查辅助功能权限
    result["steps"].append("检查辅助功能权限...")
    if not check_assistive_access():
        result["error"] = "❌ 缺少辅助功能权限！\n\n请在 系统设置 > 隐私与安全性 > 辅助功能 中授予终端/Python 权限"
        return result
    result["steps"].append("✅ 辅助功能权限正常")
    
    # Step 1: 检查微信是否运行
    result["steps"].append("检查微信运行状态...")
    if not check_wechat_running():
        result["steps"].append("⚠️ 微信未运行，请先手动打开微信")
        result["error"] = "微信未运行"
        return result
    result["steps"].append("✅ 微信已在运行")
    
    # Step 2: 激活微信
    result["steps"].append("激活微信窗口...")
    activate_script = 'tell application "WeChat" to activate'
    success, error = run_applescript(activate_script)
    if not success:
        result["error"] = f"无法激活微信：{error}"
        return result
    time.sleep(1)
    
    if simple_mode:
        # 简单模式：假设聊天窗口已打开
        result["steps"].append("发送消息（简单模式）...")
        success, send_result = send_message_simple(message)
        if not success or "error" in send_result.lower():
            # 尝试剪贴板方案
            result["steps"].append("尝试剪贴板方案...")
            success, send_result = send_message_via_clipboard(message)
    else:
        # 完整模式：搜索联系人后发送
        result["steps"].append(f"搜索联系人并发送：{contact_name}")
        success, send_result = search_and_send(contact_name, message)
    
    if not success or "error" in send_result.lower():
        result["error"] = f"发送失败：{send_result}"
        result["steps"].append("❌ 发送失败")
        return result
    
    result["success"] = True
    result["steps"].append("✅ 消息发送成功")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="微信消息发送工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
权限设置:
  1. 打开 系统设置 > 隐私与安全性 > 辅助功能
  2. 添加 终端 或 Python 到允许列表
  3. 重启终端后重试

使用示例:
  python wechat_sender.py -c "in" -m "你好"
  python wechat_sender.py -c "张三" -m "晚上吃饭吗？" --simple
        """
    )
    parser.add_argument("--contact", "-c", required=True, help="联系人名称")
    parser.add_argument("--message", "-m", required=True, help="消息内容")
    parser.add_argument("--simple", action="store_true", help="简单模式：假设聊天窗口已打开")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    
    args = parser.parse_args()
    
    result = send_wechat_message(args.contact, args.message, simple_mode=args.simple)
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n" + "="*50)
        print("微信消息发送工具")
        print("="*50)
        for step in result["steps"]:
            print(f"  {step}")
        if result["error"]:
            print(f"\n❌ 错误：{result['error']}")
        if result["success"]:
            print(f"\n✅ 成功发送消息给 {result['contact']}: {result['message']}")
        print("="*50 + "\n")
    
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
