---
name: step6-timetable-planning
description: Step 6 课程表编排。ustplan step step6 执行 scripts/rank/planner.py 以用户目标学分（P3 决定）为参照生成 N 套无冲突方案（目标/±3 夹 12-18），bucket 配额选课（防选重/选多），低阶必修先排，L+T 组件各选一节；输出 output/timetable_plan.json（含 waiver_required）。Use when generating timetable plans.
---

# Step 6 — 课程表编排（目标学分驱动）

## 触发

- step5 done 后（`ustplan step step6`）。

## 执行（ustplan 合约）

```bash
python3 scripts/ustplan.py step step6
python3 scripts/ustplan.py plan --must-take "PHYS 4291"   # phase4.5 硬插重排
python3 scripts/ustplan.py plan --exclude "PHYS 4191"     # 备选排除
python3 scripts/ustplan.py plan --target 19               # overload 提示（按 18 编排）
python3 scripts/ustplan.py grid --plan 1 [--html]         # 周历展示（ASCII/HTML）
```

- 方案生成：目标学分参照（P3），默认三档 目标 / +3 / −3（夹 12-18）；
  <12 或 >18 → 按边界编排 + 提示（<12 咨询学校、>18 Dean 批准 overload）；
- 硬约束：学分 12-18 / 不重复 / 不含已修 / 每栏位不超配额 / 无时间冲突 /
  **无 EXCLUSION 互斥**（对照 Class Schedule EXCLUSION 属性，与已修/预选/已排
  课程互斥 → 不排入并说明；MATH 2411/2421 类重复课不会同排）；
- **tutorial 组件**：一门课多个组件类型（L/T/LA/R…）时每组件各选一节
  （L1+T2 亦可），组件间与已排课不得冲突；course_details[].sections[] 全列；
- 必修先入（低阶优先；**0 学分课程靠后**——同桶真实学分课先占配额，防
  COMP 1991 实习挡 FYP）→ 按分数补足（最高档方案优先 CC）；
- **0 学分课程**（如 COMP 1991 实习）：无时间 section 时仅标注占位
  （course_details.zero_credit=true），不占排课时间；
- 预选课时段进入占用槽；TBA 课程计学分占位不排时间；
- **方案多样性**：phase2 取课顺序按方案变体轮转（分数/CC 优先/按桶轮转）；
  多套方案课程相同时自动换课（只换非必修非 must-take 的低分课，尊重配额与
  互斥）；无课可换时自动换用不同 section 时段；
- **waiver_required[]**：placed 课程 pre-req 未满足/无法判定 → 提醒写豁免申请。

## AI 职责

- 读 notes 与 course_details 做合理性检查（换课原因、高分课被排除原因、
  未达目标说明）；需要时 `plan --target/--must-take/--exclude` 重跑。

## 方案展示（P5 弱化，不强制中断）

- 展示（产品化）：N 套方案（学分/workload/CC-major 配比/课程清单/notes 摘要）
  + 周历（`ustplan grid`）；pre-req/waiver 提醒清单单独呈现；
- 用户要求修改 → 记录：`ustplan decisions set P5 chosen_plan=plan-N must_take=...`
  （或 exclude/target），重跑后再展示；
- 用户无异议即视为通过，直接推进：`ustplan phase done phase3-course-analysis`；
- 用户指定的必选课（"把 X 加进去"）→ 走 phase4.5 流程（must-take-course-insertion）。

## 交接

timetable_plan.json → phase4-report（报告渲染 + 口碑 + 建议 + 选课时间提醒）。
