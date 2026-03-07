# Qwen API 客户端

## 功能说明

这是一个基于阿里 dashscope SDK 的 API 客户端工具，用于方便地调用各种 Qwen 模型。

## 安装

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法

### 初始化客户端

```python
from tools.qwen_client.qwen_client import QwenClient

# 初始化客户端
client = QwenClient(api_key="your_api_key")
```

### 调用聊天完成

```python
# 准备消息
messages = [
    {
        "role": "user",
        "content": "你好，如何使用 dashscope SDK？"
    }
]

# 调用模型
result = client.chat_completion(
    model="qwen-plus",
    messages=messages,
    temperature=0.7,
    max_tokens=1024
)

# 处理结果
if result["success"]:
    print(result["data"])
else:
    print(f"Error: {result['error']}")
```

### 调用文本生成

```python
# 准备提示
prompt = "写一篇关于人工智能的短文"

# 调用模型
result = client.text_generation(
    model="qwen-plus",
    prompt=prompt,
    temperature=0.7,
    max_tokens=1024
)

# 处理结果
if result["success"]:
    print(result["data"])
else:
    print(f"Error: {result['error']}")
```

## 支持的模型

- qwen-plus
- qwen-turbo
- 其他 dashscope 支持的模型

## 注意事项

1. 请确保已经获取了有效的 DashScope API 密钥
2. 调用模型会产生费用，请根据实际情况控制调用频率
3. 对于长时间运行的任务，建议使用异步调用方式