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
```

- SIS 产物：cache/sis/sis_{student_info,course_history,transcript,academic_req,pre_enroll}.json
- buckets_pre 先生成未修基架；cookie 到位、画像确认后由 step1 正式重跑。

## AI 职责

1. 数据源权威顺序（固定）：SIS Transcript → Course History → USTSPACE settings → 问用户
   （绝不编造）；
2. 生成 `data/profile.json`（admission_year/year_of_study/programs/cga/credits_earned/
   source/confirmed_by_user）与 `data/passed_courses.json`（status 映射：
   T→transferred、EX→exempted、AU→audit、I→incomplete、无成绩+term→in_progress；
   EX 视同满足 pre-req）；
   **programs 必须完整回写 P1 三字段**：first_major=P1.major；
   extended_major=P1.extended_major（"NA" → 省略）；minor=P1.minor
   （"NA" → 空数组 []，否则为数组 [代码]）；
3. 预选课写入 `data/pre_enrolled.json`（预选课视为已确定：不重复推荐、占用时段）；
4. major 与 AR requirement-group 名交叉确认，冲突时 AR 优先并询问用户；
   AR 中出现 P1 未声明的需求组（如 EXT (AI)/minor 组）→ 回查 P1 三字段并
   **回问用户确认**（防漏读扩展主修/副修）；
5. 产物过 schema（`ustplan step` 与 `phase done` 会自动校验，无需手动跑）。

## 确认点 P2（强制中断）

- 展示（产品化）：专业 / track / 入学年份（含推断依据）/ 年级 / 已修学分 / CGA /
  已修门数 + **未修清单预览**（必修全列；CC/选修仅列未满足栏位）
- 提问前启动 `ustplan job start ustspace_pre`（候选清单就绪时；否则 step3 后启动）
- 用户确认 → 记录：`ustplan decisions set P2 confirmed=true admission_year=...`
- 修正 → 覆盖画像产物 + 重校验 + 重新确认；未确认不得进入 step1。
- 推进：`ustplan phase done phase2-profile`

## 交接

profile.json + passed_courses.json + pre_enrolled.json → step1（buckets.py）。
