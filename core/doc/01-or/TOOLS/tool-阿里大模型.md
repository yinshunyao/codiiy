# 背景
1. 一定遵从规则 "core/rules.md"
2. 阿里官方提供有 python 的 dashscope 组件接入

# 目标
1. tools 参考当前智能体比较主流的方式，定义工具的基础规范，形成 tools-roles.md， 放到 tools 目录中
2. 在 tools 目录下实现一个方便调用的 api 客户端代码， 遵循 "tools-roles.md"
- 使用 dashscope sdk，参考阿里官网代码
- 作为工具方便调用

# 要求
暂无

# 当前工作项（已实现和已完成直接忽略）
- 【已实现】当前实现在目录 "tools/api_client"，名称也是 api_client， 修改为 "qwen_client"
- 【已实现】需要实现当前需求