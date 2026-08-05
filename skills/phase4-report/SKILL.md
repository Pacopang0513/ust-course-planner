---
name: phase4-report
description: Phase 4 总结报告。把 Step 1-6 的固定结构产物整合为最终报告（未修清单、过滤理由、口碑摘要、N 套课程表方案），输出到 output/，末尾附加选课时间提醒（enrollment-dates-reminder）。Use when producing the final course selection report.
---

# Phase 4 — 总结报告

## 目的

把各 Step 的本地总结产物整合成**用户可读的最终报告**，输出到 `output/`。
报告必须引用各产物（可溯源），不含脚本运行细节。

## 输入（全部应为已存在的固定结构产物）

| 数据 | 文件 |
|---|---|
| 画像 | `data/profile.json` |
| 预选课 | `data/pre_enrolled.json`（学校已预选，方案中已占用时段） |
| 未修清单 | `data/unmet_courses.json` |
| Top N 候选 | `data/candidate_rank.json` |
| 过滤报告 | `data/filter_report.json`（移除理由逐条引用） |
| 评论总结 | `data/review_summary.json`（每门课口碑摘要） |
| 最终排名 | `data/course_scores.json` |
| 课程表方案 | `output/timetable_plan.json` |

## 报告结构（固定）

```
# 课程选择报告（{目标学期}）

## 1. 画像摘要
  专业/入学年份/年级/学分/CGA（来自 profile.json）

## 2. 未修课程
  专业必修 x 门、CC 必修 x 门、选修 x 门（unmet_courses.json 统计）

## 3. 过滤说明
  输入 N → 保留 M → 移除 K；移除原因分类统计（未开设 / pre-req 不满足），
  逐条列原因（filter_report.json removed[]）；pre-req 豁免提醒

## 4. 候选口碑摘要（Top 10）
  每门课：综合评分、推荐度、给分/工作量、今年导师口碑（review_summary.json）

## 5. 最终排名（course_scores.json，前 15）

## 6. 课程表方案（N 套）
  每套：课程列表、学分、workload、CC/major/选修配比、冲突说明、取舍理由

## 7. 下一步建议
  优先锁定方案、必须现在做的准备（如教授豁免申请）
```

末尾必须附加 `enrollment-dates-reminder` 输出的选课时间提醒（固定模板，不可省略）。

## 执行（固定，含检查点推进）

```bash
python3 scripts/harness/checkpoint.py begin phase4-report
# ... 撰写报告、附加 enrollment-dates-reminder、跑校验 ...
python3 scripts/harness/checkpoint.py done phase4-report
```

## 输出

- `output/final_report.md`（用户可读版）
- `output/timetable_plan.json` 已由 Step 6 产出（报告引用之）

校验：`python3 scripts/harness/schema_validate.py --target output/timetable_plan.json`

## 交接

- 报告给用户 → 用户选择方案 → phase4.5 `must-take-course-insertion`（指定课程硬插重排）
- 无指定课程 → 流程结束
