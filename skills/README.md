# skills/

流程 skills 目录（按调用顺序组织）。

当前已有（按调用顺序）：

- `harness` 主编排（固定调用顺序 phase1→phase4.5、异常处理矩阵、checkpoint 推进）
- `phase1-input` 输入准备（前置检查、目标学期→session 映射）
- `phase2-profile` 画像生成（SIS 提取 + 入学年份推断 + 用户确认）
- `step1-unmet-calculation` Step 1 未修计算（专业必修 + 今年可读 CC − 已修，公式见 skill）
- `step2-candidate-ranking` Step 2 本地规则打分 Top50（类别/等级/紧迫度权重固定）
- `step3-schedule-filter` Step 3 schedule 过滤（未开设/pre-req，移除原因逐条记录）
- `step4-review-analysis` Step 4 USTspace 评论精读（热度 top5 + 今年导师 top5 → review_summary.json）
- `step5-score-fusion` Step 5 合成排名（吸引力 = 规则 60% + 口碑 40%，置信度分档）
- `step6-timetable-planning` Step 6 课程表编排（N 套方案 + wcq 冲突校验）
- `phase4-report` 总结报告（整合各产物 → output/final_report.md）
- `enrollment-dates-reminder` 选课时间提醒（输出末尾附加三期选课时间）
- `must-take-course-insertion` 强制选课（用户指定课程硬性插入后重新排课）
- `web-crawl-guide` 联网抓取规范（固定 URL 模板/关键词/cookie 约定，AI 抓取必须遵守）

每个 step/phase skill 都规定了：输入文件、固定执行脚本、**固定总结结构（JSON 产物）**、
本地保存路径与 schema 校验、交接给下一步的内容。产物均过 R2 schema 校验。

**确认点（P1-P5）**：关键阶段间设有人类确认中断（cookie 提供/画像确认/未修清单/
过滤结果/方案选择），详见各 skill 的"确认点"小节与 harness 流程图；无用户确认
不得推进 checkpoint。

- 写入者：开发阶段人工维护
- 权限：AI 读取调用
- gitignore：否（跟踪）
