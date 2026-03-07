# FileReader 文件内容读取工具

## 功能概述

FileReader 是一个用于读取文件内容的工具，支持以下功能：

1. **整个文件内容读取**：读取完整文件内容
2. **指定行范围读取**：读取文件指定开始行到结束行的内容
3. **关键字搜索读取**：搜索关键字并返回关键字前后上下文内容
4. **正则表达式搜索**：使用正则表达式搜索匹配内容
5. **文件统计信息**：获取文件的行数、大小等统计信息
6. **操作系统识别**：自动识别当前操作系统类型

## 安装

无需额外依赖，直接使用 Python 标准库。

```bash
# 如需安装依赖（本工具无额外依赖）
pip install -r requirements.txt
```

## 使用方法

### 1. 导入工具

```python
from core.tools.file_reader import FileReader

# 创建实例
reader = FileReader()
```

### 2. 读取整个文件

```python
result = reader.read_file("/path/to/file.txt")

if result["success"]:
    content = result["data"]["content"]
    file_info = result["data"]["file_info"]
    print(f"文件内容: {content}")
    print(f"文件大小: {file_info['file_size_human']}")
else:
    print(f"读取失败: {result['error']}")
```

### 3. 读取指定行范围

```python
# 读取第 10 行到第 20 行
result = reader.read_lines("/path/to/file.txt", start_line=10, end_line=20)

if result["success"]:
    content = result["data"]["content"]
    start = result["data"]["start_line"]
    end = result["data"]["end_line"]
    print(f"第 {start}-{end} 行内容: {content}")
```

### 4. 关键字搜索

```python
# 搜索关键字并返回前后 3 行上下文
result = reader.search_keyword(
    "/path/to/file.txt",
    keyword="target",
    context_lines=3,
    case_sensitive=False
)

if result["success"]:
    matches = result["data"]["matches"]
    for match in matches:
        print(f"匹配行: {match['match_line']}")
        print(f"匹配内容: {match['match_content']}")
        for ctx in match['context']:
            marker = ">>>" if ctx['is_match_line'] else "   "
            print(f"{marker} {ctx['line_number']}: {ctx['content']}")
```

### 5. 正则表达式搜索

```python
# 使用正则表达式搜索
result = reader.search_regex(
    "/path/to/file.txt",
    pattern=r"def\s+\w+",
    context_lines=2
)

if result["success"]:
    matches = result["data"]["matches"]
    for match in matches:
        print(f"匹配行: {match['match_line']}")
        print(f"匹配组: {match['match_groups']}")
```

### 6. 获取文件统计信息

```python
result = reader.get_file_stats("/path/to/file.txt")

if result["success"]:
    stats = result["data"]
    print(f"文件大小: {stats['file_size_human']}")
    print(f"总行数: {stats['line_count']}")
    print(f"创建时间: {stats['created_time']}")
```

### 7. 获取系统信息

```python
result = reader.get_system_info()

if result["success"]:
    info = result["data"]
    print(f"操作系统: {info['system']}")
    print(f"平台: {info['platform']}")
    print(f"Python版本: {info['python_version']}")
```

## API 参考

### FileReader 类

#### 方法

| 方法名 | 描述 | 返回值 |
|--------|------|--------|
| `read_file(file_path, encoding='utf-8')` | 读取整个文件 | `{"success": bool, "data": {...} or "error": str}` |
| `read_lines(file_path, start_line, end_line, encoding='utf-8')` | 读取指定行范围 | `{"success": bool, "data": {...} or "error": str}` |
| `search_keyword(file_path, keyword, context_lines=3, encoding='utf-8', case_sensitive=False)` | 关键字搜索 | `{"success": bool, "data": {...} or "error": str}` |
| `search_regex(file_path, pattern, context_lines=3, encoding='utf-8')` | 正则搜索 | `{"success": bool, "data": {...} or "error": str}` |
| `get_file_stats(file_path)` | 获取文件统计 | `{"success": bool, "data": {...} or "error": str}` |
| `get_system_info()` | 获取系统信息 | `{"success": bool, "data": {...}}` |

## 返回值格式

所有方法统一返回字典格式：

**成功时：**
```python
{
    "success": True,
    "data": { ... }  # 具体数据根据方法不同而变化
}
```

**失败时：**
```python
{
    "success": False,
    "error": "错误信息"
}
```

## 操作系统支持

本工具支持以下操作系统：

- Windows (`windows`)
- macOS (`darwin`)
- Linux (`linux`)

工具会自动识别当前操作系统类型，并在文件信息中返回。

## 注意事项

1. 文件路径支持绝对路径和相对路径
2. 默认使用 UTF-8 编码，如遇编码问题可尝试其他编码（如 `gbk`、`latin-1` 等）
3. 行号从 1 开始计数
4. 关键字搜索默认不区分大小写
