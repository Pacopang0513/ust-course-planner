---
name: must-take-course-insertion
description: 在课程表方案输出后询问用户是否有特别想上的课程（单门、多门或指定组合），将其硬性插入方案并重新排课。Use when finalizing the timetable plan or when the user requests specific courses to be included in the arrangement.
---

# Must-Take Course Insertion

## 何时使用

Phase 4 输出 N 套课程表方案之后、最终确认之前调用。用户可指定单门课程、多门课程或指定课程组合/排列。

## 步骤

0. **推进检查点**（R4 链的最后一段，必须执行）：
   ```bash
   python3 scripts/harness/checkpoint.py begin phase4.5-must-take
   ```
1. **询问用户**：是否有特别想上的课程？（可指定单门、多门或组合；也可直接指定某门课必须排入）
2. **校验指定课程**：
   - 是否在本年度 Class Schedule 中开设
   - 时间槽是否与其他必修/已选课程冲突
   - pre-requisite / exclusion 是否满足
3. **硬性插入**：用 Step 6 编排脚本重排（硬插课程 phase0 优先入排，冲突/超限
   记入 notes，不强行）：
   ```bash
   python3 scripts/rank/planner.py --scores data/course_scores.json \
       --session 2610 --passed data/passed_courses.json \
       --must-take "COMP 3111" "MATH 2023" --output output/timetable_plan.json
   ```
   输出标注 `must_take_inserted`；若有 notes 提示未排入，回到异常处理表处理。
   重排后重新跑 schema 校验。
4. **重新输出**：输出调整后的方案（标注强制课程），并再次附加选课时间提醒（enrollment-dates-reminder）
5. **取舍建议**：若无法同时满足全部指定课程，给出取舍建议

## 异常处理（固定）

| 情况 | 处理 |
|---|---|
| 课程今年不开 | 告知用户，建议替代课程（从候补池按得分补入） |
| 时间冲突无法消除 | 请用户在冲突课程中取舍，不擅自决定 |
| pre-req 未满足 | 提醒需教授豁免，或建议先修课程 |
| exclusion 冲突 | 告知用户该课与已修/在修课程互斥 |
| 用户无指定课程 | 跳过本阶段，维持原方案 |

## 收尾（固定）

调整完成并重新校验后，关闭检查点（用户无指定课程时同样执行）：

```bash
python3 scripts/harness/checkpoint.py done phase4.5-must-take
```
