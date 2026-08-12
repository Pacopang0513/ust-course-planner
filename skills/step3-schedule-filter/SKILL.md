---
name: step3-schedule-filter
description: Step 3 候选课程过滤。ustplan step step3 执行 scripts/rank/filter.py 对照本学年 Class Schedule：今年未开设 → 移除；pre-req 未满足/无法解析 → 保留 + 标记（waiver 路径，不移除）；仅限专业学生 → 标记；输出 data/filter_report.json（含每课 prereq 字段）。Use when filtering candidates against the class schedule.
---

# Step 3 — 候选课程过滤

## 触发

- step1 done + P3 确认后（`ustplan step step3`）。

## 执行（ustplan 合约）

```bash
python3 scripts/ustplan.py step step3
```

- 规则（固定，脚本执行）：今年未开设 → **移除**（not_offered_this_year）；
  pre-req 未满足 → **保留 + 标记** `prereq_not_met:xxx`（waiver 是处理路径，
  评分与排课不考虑 pre-req）；无法解析 → `prereq_unknown:xxx`（AI 复核不擅自删除）；
  仅限专业 → `restricted:xxx`；
  **EXCLUSION 互斥** → 解析 EXCLUSION 字段写入 `exclusion {text, codes,
  conflicts_with_passed[]}`，与已修重叠标 `excluded_by_passed:xxx`（保留 +
  提示；排课阶段 planner 做强制互斥检查）；
- 用户豁免放回：`ustplan decisions set P4 overrides=PHYS4191`（或追加后）重跑
  `step step3 --force`，课程标 `user_overridden`；
- 每门 kept 课程附 `prereq {text, met, missing[], grading[]}` → step6 据此输出
  waiver_required[]；
- **pre-req 成绩要求（grading，2026-08）**：pre-req 文本可含成绩要求
  （"Grade A or above in PHYS 1312" / "Pass grade in COMP 1028"）。filter 解析
  出逐条 `grading {code, required, actual, met}` 并对照已修成绩（对照
  passed_courses.json 的 grade）；三状态：无要求（不存在）/ 需要某 grading
  （met True/False）/ 有 grading 语义但无法解析（如 "Level 3 or above in
  HKDSE ..." 无课程码 → met=null，AI 复核）。成绩不达标 → `grading_not_met`
  标记，同 pre-req 未满足一样走 waiver 路径（step6 提醒"成绩不达标需豁免"）；
  成绩判定与 OR/AND 分支绑定（分支内不达标不影响其他已满足分支）。

## AI 职责

- 复核 `prereq_unknown` / `restricted` 标记（对照 remarks 文本），需要时向用户确认；
- 不在这一步因 pre-req 删除任何课程（豁免路径固定）。

## 确认点（并入 P3，不单独提问）

- 过滤结果（移除清单 / waiver 课程 / 复核项）随 P3 确认点**同一 question 回合**
  展示并收集异议；
- 用户对移除有异议（教授豁免/等效课）→ 记录 `ustplan decisions set P3 overrides=...`
  重跑 `step step3 --force`；
- 不再单独提问（P4 已并入 P3）。

## 交接

filter_report.json（kept[]）→ step4（USTSPACE 精读）+ step5（bucket 评分）。
P3 确认后 step4 可执行。
