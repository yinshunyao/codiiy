# 关联文档
| 类型 | 文档路径 |
|:---|:---|
| 原始需求 | `codiiy/doc/01-or/【adapter】对接比较成熟的agent程序.md` |
| 原始需求 | `codiiy/doc/01-or/【适配器】Cursor Local 适配器实现.md` |
| 开发设计 | `codiiy/doc/02-dr/11 adapter/11.01 adapter对接设计.md` |

# 测试范围

1. adapter 基类与类型定义的基本行为
2. adapter 注册表的注册、查询、列举功能
3. process adapter 的配置校验与执行逻辑
4. http adapter 的配置校验
5. cursor_local adapter 的 stream-json 解析、会话恢复、容错重试
6. CompanionProfile 模型 adapter_type 和 adapter_config 字段
7. 伙伴创建/编辑表单 adapter 类型选择

# 测试用例

## 单元测试（codiiy/test/test_adapter/）

### 注册表测试

| 编号 | 用例 | 前置条件 | 操作 | 预期结果 |
|:---|:---|:---|:---|:---|
| R-01 | 注册并查询 adapter | 注册表为空 | 注册 process adapter，查询 type="process" | 返回 process adapter 实例 |
| R-02 | 查询不存在的 adapter | 注册表已注册 process | 查询 type="unknown" | 返回 None |
| R-03 | 列举所有 adapter | 注册 process 和 http | 调用 list_adapters() | 返回两个 adapter |
| R-04 | 获取 choices 列表 | 注册 process 和 http | 调用 get_adapter_choices() | 返回含空选项的 choices 元组列表 |

### Process Adapter 测试

| 编号 | 用例 | 前置条件 | 操作 | 预期结果 |
|:---|:---|:---|:---|:---|
| P-01 | 执行简单命令 | 无 | execute config={command: "echo", args: ["hello"]} | exit_code=0, stdout 含 "hello" |
| P-02 | 命令不存在 | 无 | execute config={command: "nonexistent_cmd_xyz"} | error_message 非空 |
| P-03 | 缺少 command 配置 | 无 | execute config={} | 抛出异常或返回错误 |
| P-04 | 环境检测-命令存在 | 无 | test_environment config={command: "echo"} | status="pass" |
| P-05 | 环境检测-命令不存在 | 无 | test_environment config={command: "nonexistent_cmd_xyz"} | status="fail" |

### HTTP Adapter 测试

| 编号 | 用例 | 前置条件 | 操作 | 预期结果 |
|:---|:---|:---|:---|:---|
| H-01 | 缺少 url 配置 | 无 | execute config={} | 抛出异常或返回错误 |
| H-02 | 环境检测-url 格式正确 | 无 | test_environment config={url: "http://localhost:8000"} | status="pass" |
| H-03 | 环境检测-url 缺失 | 无 | test_environment config={} | status="fail" |

### Cursor Local Adapter 测试

| 编号 | 用例 | 前置条件 | 操作 | 预期结果 |
|:---|:---|:---|:---|:---|
| C-01 | 自动追加 yolo | `extra_args` 不含 trust/yolo/f | execute | 实际命令包含 `--yolo` |
| C-02 | 保留现有 trust 参数 | `extra_args=["--trust"]` | execute | 不重复追加 `--yolo` |
| C-03 | 解析 stream-json | stdout 含 `system/assistant/result` 事件 | execute | 正确提取 `session_id/usage/cost/summary` |
| C-04 | 会话 cwd 不一致 | 传入 `session_id+session_cwd` 且 cwd 改变 | execute | 跳过 `--resume` 并记录原因 |
| C-05 | resume 失败自愈重试 | 首次执行返回 unknown session 错误 | execute | 自动无 resume 重试一次并成功 |
| C-06 | 环境检测 hello probe | `hello_probe=true` 且命令可执行 | test_environment | 返回 `cursor_hello_probe_ok` |

### 基类测试

| 编号 | 用例 | 前置条件 | 操作 | 预期结果 |
|:---|:---|:---|:---|:---|
| B-01 | 调用基类 execute | 无 | BaseAdapter().execute(ctx) | 抛出 NotImplementedError |
| B-02 | 调用基类 test_environment | 无 | BaseAdapter().test_environment(cfg) | 抛出 NotImplementedError |

## 模型与表单测试（codiiy/test/test_core/test_collector/）

| 编号 | 用例 | 前置条件 | 操作 | 预期结果 |
|:---|:---|:---|:---|:---|
| M-01 | 创建含 adapter 字段的伙伴 | 用户和项目已存在 | 创建 CompanionProfile(adapter_type="process", adapter_config={...}) | 保存成功 |
| M-02 | adapter_type 为空时正常创建 | 用户和项目已存在 | 创建 CompanionProfile(adapter_type="") | 保存成功 |
| M-03 | 表单包含 adapter_type 字段 | 无 | 实例化 CompanionProfileForm | 表单含 adapter_type 字段 |

# 自动化测试标识

| 测试类别 | 框架 | 自动化 |
|:---|:---|:---|
| 单元测试（adapter 模块） | pytest | 是 |
| 模型/表单测试 | Django TestCase + pytest | 是 |
| E2E 表单交互 | Playwright | 后续迭代 |
