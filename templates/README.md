# templates/

通用输出模板（规范化输出的唯一标准），AI 按模板自动填入：

- `schemas/` JSON Schema —— 脚本强制校验（如 `profile.schema.json`）
- markdown 输出模板（如课程总结、最终报告）——由对应 phase skills 规定结构

- 写入者：开发阶段人工维护
- 权限：AI 只读，产出必须符合模板并校验通过
- gitignore：否（跟踪）
