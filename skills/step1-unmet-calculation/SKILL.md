---
name: step1-unmet-calculation
description: Step 1 未修课程计算（bucket 化）。ustplan step step1 执行 scripts/rank/buckets.py：必修一门一桶、选修一 pool 一桶、CC 一区域一桶；track 过滤 + pre-req 引用补录 + 已修/预选课扣除（OR 池整桶满足）；CC 区域满足性全脚本三层判定；AI 精读 Note 语义后保存 data/unmet_courses.json。Use when computing un-taken courses.
---

# Step 1 — 未修课程计算（bucket 化）

## 触发

- phase3-course-analysis begin 后（`ustplan phase begin phase3-course-analysis`）。

## 执行（ustplan 合约）

```bash
python3 scripts/ustplan.py step step1
```

- 前置检查自动完成：phase 状态、输入（profile/passed_courses + 可选 pre_enrolled）
  存在且过 schema、step 顺序；
- 命令由合约构建：`buckets.py --profile … --session {P1.session} --track {P1.track}
  --passed …`（session/track 从运行状态注入，无需手写）；
- 公式：未修 = 专业必修（按 track 过滤）+ 今年可读 CC − 已修 − 预选课。
- 脚本自动处理（无需 AI）：track 限制（"can only use X"）、EXT 主修合并、
  课号清洗、已修/预选扣除、OR 池整桶满足、pre-req 引用补录、
  **CC 区域满足性三层判定**（历史区域表 → AR 条目 → AR 组回退）。

## AI 职责（精读，脚本不做语义判断）

1. 核对产物与 SIS AR 一致（AR 权威）：AR 显示满足的栏位 → 相应 bucket 移除或标注；
2. **Note 语义已脚本固化**（`scripts/rank/note_eval.py`，AND/OR/方括号/any N of
   表达式解析 + 整桶满足判定），复杂 Note 的表达式形状写入 `buckets[].note_semantics`；
   AI 复核该形状与要求一致即可，**不再手写求值器**（嵌套括号/方括号 `[...]`
   不会被当 Python 列表误判；FYP 组如
   `[COMP 1991 AND (COMP 4981 OR COMP 4981H)] OR [COMP 4910]` 只修 0 学分
   实习不会误判整桶满足）；仅在与 AR/学生事实矛盾时标注 review_pending 并确认；
3. **CC 满足性不做 AI 判断**（脚本已全判）；仅在与 AR/学生事实矛盾时标注
   review_pending 并向用户确认；
4. 等效课（MATH 2011≡2023 类）→ 依据 AR/用户确认标注，可沉淀 database/mappings/；
5. 无法判定 → 本步内解决（含问用户），不留到下一步；120 学分/credit-reuse → 注记。

## 确认点 P3（question 工具内联提问，含过滤结果展示）

- 交互：AI 在流程中到达本点即用 question 工具一次问清（未修确认 + 目标学分，
  选项含默认 15 与自定义输入），用户作答后同一轮对话内继续；
- **P3 前 CC 满足性核查**：`python3 scripts/rank/cc_status.py --passed data/passed_courses.json
  --admission-year <AY> --major <MAJOR>`（区域已修/未修 + Broadening 12 学分 4 区域结论，
  脚本固化，AI 不自行推导）；
- 展示（产品化）：必修按 bucket 全列；CC/选修仅列未满足栏位；review_pending 列表；
  pre-req 参考课程；
- **未修学分统计（指导建议）**：产物含 `unmet_credits`（未修学分总和）/
  `estimated_semesters_left`（剩余学期估算，4 年制 8 学期含当前）/
  `credits_per_semester_estimate`（平均每学期建议学分）。P3 问目标学分前
  展示建议值："按剩余 X 个学期，每学期平均约 Y 学分即可按时毕业"——
  若用户目标明显低于该值，提示后续学期压力/毕业风险（Agent 有义务指导，
  双主修 double count 会使统计偏高，以 AR 审计为准）；
- **同回合问目标学分**（默认 15，一次问清）；
- **同回合顺带展示 step3 过滤结果**（今年未开设移除 / waiver 课程 / 复核项），
  用户有异议（教授豁免/等效课）→ 记录 `overrides` 重跑 step3；
- 记录：`ustplan decisions set P3 confirmed=true target_credits=<N> [overrides=...]`；
- 修正 → 覆盖 + 重跑 `step step1 --force` + 重新确认。

## 交接

unmet_courses.json → step3（filter.py）。P3 确认后 step3 可执行。
