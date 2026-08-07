---
name: must-take-course-insertion
description: 在课程表方案输出后询问用户是否有特别想上的课程（单门、多门或指定组合），用 ustplan plan --must-take 硬性插入并重新排课，决策记录到 decisions。Use when finalizing the timetable plan or when the user requests specific courses to be included in the arrangement.
---

# Must-Take Course Insertion（phase4.5）

## 何时使用

Phase 4 输出报告之后、最终确认之前调用。用户可指定单门、多门或组合。

## 步骤

0. **推进检查点**：`python3 scripts/ustplan.py phase begin phase4.5-must-take`
1. **询问用户**：是否有特别想上的课程？（单门/多门/组合均可）
2. **校验指定课程**（对照 filter_report/ranked_out 与 courses_{session}）：
   今年是否开设 / 时间槽是否冲突 / pre-req、exclusion 是否满足
   （EXCLUSION 互斥由 planner 排课时自动强制检查，冲突课程不会入排并留
   note 说明；此处仅需核对提示信息）；
3. **硬性插入**（保留目标学分）：
   ```bash
   python3 scripts/ustplan.py plan --must-take "PHYS 4291" "COMP 3111"
   ```
   自动记录 decisions.phase4.5.must_take → planner 重排 → schema 校验 → 周历更新
   （`ustplan grid --plan 1`）；输出标注 `must_take_inserted`；
4. **重新输出**：调整后方案（标注强制课程）+ 再次附加选课时间提醒
   （enrollment-dates-reminder）；
5. **取舍建议**：无法同时满足全部指定课程时给出取舍建议。

## 异常处理（固定）

| 情况 | 处理 |
|---|---|
| 课程今年不开 | 告知用户，建议替代课程（同栏位其余评分课或 ranked_out 备选池按得分补入） |
| 课程不在评分池（TOP N 之外） | ranked_out 含全部评分课程，可直接 --must-take 排入 |
| 时间冲突无法消除 | 请用户在冲突课程中取舍，不擅自决定 |
| pre-req 未满足 | 提醒需教授豁免（waiver），或建议先修课程 |
| exclusion 冲突 | planner 已自动拦截并留 note；向用户说明该课与已修/在修课程互斥即可 |
| 用户无指定课程 | 跳过本阶段，维持原方案 |

## 收尾（固定）

调整完成并重新校验后关闭检查点（无指定课程时同样执行）：

```bash
python3 scripts/ustplan.py phase done phase4.5-must-take
```
