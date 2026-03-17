# 背景
- paperclip 实现了 adapter 对接机制，能够快速引入成熟的 agent 程序（如 Cursor、Claude CLI、Codex 等），扩充平台能力
- paperclip 的 adapter 代码目录在 paperclip/packages/adapters，核心抽象包括：adapter 类型注册、执行函数、环境检测、配置构建
- 本平台（codiiy）也需要实现类似的 adapter 机制，以 Python 实现，集成到现有伙伴（CompanionProfile）体系中

# 目标
1. 在目录 codiiy/adapter 移植 paperclip 的 adapter 对接能力，使用 Python 实现核心抽象（基类、注册表、执行接口）
2. 首批支持 process（通用命令行）和 http（HTTP 接口）两种 adapter 类型
3. 创建伙伴（朋友）时增加 adapter 选项，暂时只支持下拉点选 adapter 类型
4. adapter 配置以 JSON 形式存储在伙伴配置中，不同 adapter 类型有不同的配置字段

# 要求

## 功能性要求
1. adapter 基类定义统一的执行接口（execute）和环境检测接口（test_environment）
2. adapter 注册表支持通过 adapter_type 字符串查找对应的 adapter 实现
3. process adapter 支持配置：command（命令）、args（参数列表）、cwd（工作目录）、env（环境变量）、timeout_sec（超时秒数）
4. http adapter 支持配置：url（请求地址）、method（HTTP方法）、headers（请求头）、timeout_sec（超时秒数）
5. CompanionProfile 模型新增 adapter_type 和 adapter_config 字段
6. 伙伴创建/编辑表单新增 adapter 类型下拉选择（点选），adapter_config 暂用 JSON 文本域
7. adapter_type 为可选字段，不选择时伙伴沿用现有行为（内置 LLM 对话）

## 非功能性要求
1. adapter 模块与现有 collector 应用松耦合，通过字段关联而非硬编码
2. 预留扩展性，后续可方便新增 adapter 类型（如 cursor、claude_local 等）

# 当前工作项
（暂无）

# 已完成工作项

## 需求
- 实现 adapter 基础模块（base、registry、process、http）— 完成 codiiy/adapter/ 模块实现
- CompanionProfile 模型增加 adapter_type 和 adapter_config 字段 — 含 Django migration 0027
- 伙伴创建/编辑表单增加 adapter 类型点选 — 表单和模板均已更新

## 问题
（暂无）
