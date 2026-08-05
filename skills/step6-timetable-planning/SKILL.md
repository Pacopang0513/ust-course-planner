---
name: step6-timetable-planning
description: Step 6 课程表编排。按 Step 5 排名组合 N 套无时间冲突方案（不同学分/workload/CC 与 major 配比），用 wcq 冲突检测验证，按固定结构总结保存为 output/timetable_plan.json。Use when generating timetable plans.
---

# Step 6 — 课程表编排

## 目的

按 Step 5 排名产出 **N 套（默认 3 套）**无时间冲突的课程表方案，覆盖不同偏好
（学分高低 / workload / CC 与 major 配比），供用户选择。

## 输入

| 文件 | 来源 |
|---|---|
| `data/course_scores.json` | Step 5 产物（排名） |
| `data/courses_{session}.json` | 本学年 schedule（section 时间/教室/导师/Quota） |
| `data/passed_courses.json` | 已修（排课不含已修课） |
| `database/policies/registration.md` | 负荷规则：每 Regular Term 12-18 学分 |

## 执行步骤（固定）

1. **选课池**：`scripts/rank/planner.py` 从 course_scores 排名前 N（默认 20）取池，
   按 `review_confidence` 高的优先不适用——排名即分数降序，无需二次排序
2. **编排（脚本，确定性）**：
   ```bash
   python3 scripts/rank/planner.py --scores data/course_scores.json \
       --session 2610 --passed data/passed_courses.json --plans 3 \
       --pre-enrolled data/pre_enrolled.json \
       --output output/timetable_plan.json
   ```
   - 严格按 schedule 排课：每门课从 `courses_{session}.json` 的 sections 中选
     第一个与已选课程无冲突的 section（时间槽由 wcq/conflict.py 同一解析器判定）；
     TBA 无时间 section 不参与排课，对应课程记入 notes
   - **预选课（学校 Pre-Enroll）**：`--pre-enrolled` 预选课的 section 时段进入
     占用槽，选课不得与其冲突；未匹配到时段（未开设/TBA）记入 notes 提示
   - section 的 datetime / room / instructors 原样记录在方案 `course_details`（
     每门课的上课时间与授课教授由此可溯）
   - 两阶段选课：phase1 专业必修全入（必修优先），phase2 按方案偏好
     （低学分 12-13 必修优先 / 中 15-16 均衡 / 高 17-18 CC 配比高）补足学分，
     达到目标下限即停；方案间课程完全相同会自动做一次确定性换课（多样性）
   - 硬约束：学分 12-18 / 不含已修课 / 无重复课（脚本保证）
3. **AI 复核**：读产物 notes 与 course_details，确认取舍理由合理
   （换掉的课、未入方案的高分课、学分未达区间的说明），必要时调整 `--top`/
   `--plans` 重跑
4. 每个方案 `no_conflict: true` 由脚本构造保证；如需独立复核可另跑
   `scripts/wcq/conflict.py` 验证任一方案

## 总结结构（固定，写入 output/timetable_plan.json）

```json
{
  "plans": [
    {"plan_id": "plan-1", "courses": ["COMP 2011", "MATH 2023", "..."],
     "course_details": [
       {"code": "COMP 2011", "name": "...", "category": "major_required",
        "credits": 4.0, "section": "L1", "datetime": "TuTh 01:30PM - 02:50PM",
        "room": "...", "instructors": ["LI, Xin"]}],
     "total_credits": 15.0, "workload": "medium",
     "cc_credits": 3.0, "major_credits": 9.0, "elective_credits": 3.0,
     "no_conflict": true, "must_take_inserted": [],
     "notes": ["取舍说明（冲突换课/未入方案的高分课）"]}
  ],
  "generated_at": "ISO"
}
```

- `course_details` 为脚本按 schedule 严格落地的每课 section（时间/教室/授课教授），
  供报告与用户核对
- 校验：`scripts/harness/schema_validate.py --target output/timetable_plan.json`

## 确认点 P5（强制中断）— 方案展示与选择

**排课产物生成并校验后必须暂停，向用户展示方案摘要，等待用户选择/反馈：**

```
课程表方案（{session}，共 3 套）
plan-1：14 学分 light  CC 3 / major 11 / 选修 0   [课程...]
plan-2：17 学分 heavy  CC 6 / major 11 / 选修 0   [课程...]
plan-3：17 学分 heavy  CC 6 / major 11 / 选修 0   [课程...]
取舍说明（notes 摘要）：冲突换课 / 未入方案的高分课 / 目标区间未达
```

- 用户选定方案 → phase4 报告按所选方案展开；有偏好修正（如"不要 plan-3 的 X 课"）
  → 用 `--must-take`/调整参数重跑 planner 再展示
- 用户确认后 `done phase3-course-analysis`，进入 phase4-report
- 用户指定额外课程 → phase4.5 must-take（报告之后执行）

## 交接

- 方案 → phase4 报告输出给用户，末尾附加 enrollment-dates-reminder 选课时间提醒
- 用户确认后 → phase4.5 must-take-course-insertion：指定课程硬插 → 重排 → 重新校验
