# 课程选择报告（{{semester_label}}）

> 由 ustplan report 自动渲染机械段落（1/2/3/5/6）；第 4、7 节由 AI 精读补充。

## 1. 画像摘要

- 主修：{{profile.major}} / Track：{{profile.track}} / 入学年份：{{profile.admission_year}} / 年级：{{profile.year_of_study}}
- 已修学分：{{profile.credits_earned}} / CGA：{{profile.cga}} / 已修门数：{{profile.courses_taken}}
- 预选课（Pre-Enroll）：{{profile.pre_enrolled_summary}}

## 2. 未修栏位（bucket）

{{unmet_sections}}

## 3. 过滤说明

{{filter_summary}}

## 4. 候选口碑摘要（AI 精读填写）

<!-- AI 填写：每栏位 TOP3 课程的综合评分 / 推荐度 / 给分 / 工作量 / 今年导师口碑（依据 data/review_summary.json） -->

## 5. 最终评分总表（每栏位 TOP{{top_per_bucket}}）

{{scores_sections}}

## 6. 课程表方案（N 套，选定：{{chosen_plan}}）

{{plans_sections}}

### 6.x 选定方案 {{chosen_plan}} 明细

{{chosen_plan_detail}}

**pre-req / waiver 提醒清单**（{{chosen_plan}}）：

{{waiver_section}}

**预选课 drop 建议**（{{chosen_plan}}，评分已含 +20% 预选课加权）：

{{pre_enroll_section}}

## 7. 下一步建议（AI 填写）

<!-- AI 填写：validation period 尽早提交 shopping cart；waiver 申请（列出课程与 missing pre-req）；overload/低学分说明（如有）；预选课 drop 决策（如适用，需申请 waiver） -->

---

## 选课时间提醒（{{semester_label}}）

<!-- AI 附加：enrollment-dates-reminder 固定模板（Shopping Cart / Enrollment Appointment / Add-Drop 三期） -->
