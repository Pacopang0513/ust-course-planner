# templates/

通用输出模板（规范化输出的唯一标准），AI 与脚本按模板生成：

- `schemas/` JSON Schema —— 脚本强制校验（全部带 `$id` + `version` 版本号，
  如 `profile.schema.json`；`config.schema.json` 校验产品参数）
- `reports/` 报告模板 —— `final_report.md.tpl` 由 `report/render.py` 渲染
  机械段落，AI 补口碑精读与建议

- 写入者：开发阶段人工维护
- 权限：AI 只读，产出必须符合模板并校验通过
- gitignore：否（跟踪）
