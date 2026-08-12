---
name: phase2-profile
description: Phase 2 用户画像。SIS Transcript/Course History 权威优先，生成 data/profile.json、data/passed_courses.json、data/pre_enrolled.json；与用户提供 major/track 交叉确认；后台并行 buckets_pre（无需 cookie）。Use when building the student profile.
---

# Phase 2 — 用户画像

## 触发

- phase1-input done 后（`ustplan phase begin phase2-profile`）。

## 执行（ustplan，并行时间线）

```bash
python3 scripts/ustplan.py job start sis_fetch        # SIS 抓取（cookie 到位后）
python3 scripts/ustplan.py job start buckets_pre      # 未修 bucket 预计算（major+track 即可）
python3 scripts/ustplan.py job status sis_fetch       # 用户回复后先查任务
python3 scripts/sis/build_profile.py --session <S>    # 画像基架（course_history → profile/passed_courses）
python3 scripts/rank/cc_status.py --passed data/passed_courses.json \
    --admission-year <AY> --major <MAJOR>             # CC 区域满足性核查（可选，P3 前用）
```

- SIS 产物：cache/sis/sis_{student_info,course_history,transcript,academic_req,pre_enroll}.json
- `build_profile.py` 固化机械转换（status 白名单 / in_progress 判定 / 入学年份与年级
  推断 / P1 程序字段回写 / school 推断），AI 不再手写转录脚本；
- buckets_pre 先生成未修基架；cookie 到位、画像确认后由 step1 正式重跑。

## AI 职责

1. 数据源权威顺序（固定）：SIS Transcript → Course History → USTSPACE settings → 问用户
   （绝不编造）；
2. 生成 `data/profile.json`（admission_year/year_of_study/programs/cga/credits_earned/
   source/confirmed_by_user）与 `data/passed_courses.json`：
   **基架由 `scripts/sis/build_profile.py` 自动生成**（status 映射、学分统计、
   入学年份/年级推断、P1 程序字段回写均固化）；AI 仅复核产物、补充
   transcript 缺失的 cga（问用户）、确认后置 confirmed_by_user=true。
   status 判定（脚本与 AI 统一白名单，与 filter.PASSED_STATUSES 一致）：只有
   taken/transferred/exempted/in_progress 计入"已修/已确定"；**incomplete（挂科）
   不算已修**（保留在未修清单、允许推荐重修）、audit（旁听）不算、unknown
   （解析异常）不算——P2 展示时提示挂科课程需重修；EX（exempted）视同满足
   pre-req；无成绩 + term == 目标学期 → in_progress（含 "&nbsp;" 空成绩）；
   **programs 必须完整回写 P1 程序字段（2026-08 支持多主修/多副修）**：
   first_major=P1.major 数组第 1 个；**additional_major=P1.major[1:]**（单主修
   → []）；extended_major=P1.extended_major（"NA"/"" → 省略）；minor=P1.minor
   数组（[]=没有，原样回写）；P1 双主修（如 COSC+MATH）时 two majors 都必须
   体现，step1 会自动合并两个培养方案；
   **school 字段（学院）**：从 AR 组名/专业归属推断（如 COMP/COSC→SENG、
   MATH/PHYS→SSCI），step1 据此加载学院 School Requirement（SREQ-{SCHOOL}.json，
   如 SREQ-SENG；2025-26 起 SENG 无独立 school req，缺失属正常，以 AR 为准）；
3. **预选课（Pre-Enroll）自动落盘**：sis_fetch job 抓取 SIS Enrollment Summary
   （SA_LEARNER_SERVICES.ZR_SSENRL_SUM_CMP.GBL）→ `cache/sis/sis_pre_enroll.json`
   **并同步写 `data/pre_enrolled.json`**（同构同 schema，无需 AI 手写）。
   预选课视为已确定：不重复推荐（step1 计入已确定）、评分按 pre_enroll_boost
   加权（默认 +40%）、占用 section 时段（step6）。AI 职责=核对 term 与清单，
   P2 展示预选课摘要；列表为空（如非预选季 "Total Unit Load: 0"）属正常；
4. major 与 AR requirement-group 名交叉确认，冲突时 AR 优先并询问用户；
   AR 中出现 P1 未声明的需求组（如 EXT (AI)/minor 组）→ 回查 P1 三字段并
   **回问用户确认**（防漏读扩展主修/副修）；
5. 产物过 schema（`ustplan step` 与 `phase done` 会自动校验，无需手动跑）。

## 确认点 P2（question 工具内联提问，不截断流程）

- 交互：AI 在流程中到达本点即用 question 工具确认（选项：正确 / 需修正 +
  自由回答补充），用户作答后同一轮对话内继续；
- 展示（产品化）：专业 / track / 入学年份（含推断依据）/ 年级 / 已修学分 / CGA /
  已修门数 + **未修清单预览**（必修全列；CC/选修仅列未满足栏位）
- 提问前启动 `ustplan job start ustspace_pre`（候选清单就绪时；否则 step3 后启动）
- 用户确认 → 记录：`ustplan decisions set P2 confirmed=true admission_year=...`
- 修正 → 覆盖画像产物 + 重校验 + 重新确认；未确认不得进入 step1。
- 推进：`ustplan phase done phase2-profile`

## 交接

profile.json + passed_courses.json + pre_enrolled.json → step1（buckets.py）。
