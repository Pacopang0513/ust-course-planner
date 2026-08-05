---
name: phase2-profile
description: Phase 2 用户画像生成。按数据权威性排序（SIS Transcript → course history 推断 → USTSPACE settings → 问用户）获取入学年份/CGA/专业，经用户确认后生成 data/profile.json 与 data/passed_courses.json。Use when building the student profile.
---

# Phase 2 — 用户画像（profile + passed_courses）

## 目的

把 SIS 原始数据整理为流程标准输入：`data/profile.json`（画像）与
`data/passed_courses.json`（已修课程）。画像数据必须**经用户确认**后才进入 Step 1。

> **重要声明**：测试数据（开发期 mock / 样本）仅用于验证脚本正确性。
> **真实运行必须重新抓取**，不得沿用任何测试产物（data/ 在交付态为空，
> 全部从本阶段重建）。

## 数据获取：权威性排序（固定）

| 优先级 | 来源 | 提供什么 | 说明 |
|---|---|---|---|
| 1（首选） | **SIS Transcript**（dropdown 2035） | CGA、最早修读学期、学术状态 | 判断新生/老生的**权威依据**（见下） |
| 2 | **SIS Course History**（dropdown 2050） | 已修课程全量、每门课 term | 推断入学年份的次选 |
| 3 | **USTSPACE settings**（账户设置页） | 若前两者都拿不到 | 补救手段，见异常处理 |
| 4 | 询问用户 | 一切缺失字段 | 最终兜底，**不编造** |

## 入学年份判断规则（固定，经用户确认规则后固化）

1. **查 Transcript**：看是否有 CGA 记录
   - **无 CGA 记录** → 该生是大一新生 → **入学年份 = 当年**（如规划 2026-27 学期则
     admission_year = 2026-27）
   - **有 CGA 记录** → 非新生 → 查看**最早上课时间**（最早 term）→ 入学年份 =
     该 term 所属学年（如最早 2023-24 Fall → 2023-24）
2. Transcript 不可用（抓取失败/无数据）→ 用 Course History 最早修读学期推断
   （`infer_admission_year`，只取 taken/in_progress/transferred）
3. 仍无 → USTSPACE settings → 仍无 → 问用户
4. **年级**：入学年份 → 目标学期学年差 + 1（如 2023-24 入学，2026-27 Fall = Year 4）

## 输入

| 文件 | 来源 |
|---|---|
| `cache/sis/sis_transcript.json` | `scripts/sis/parser.py --fetch`（需 credentials/cookies.txt 的 PS_TOKEN） |
| `cache/sis/sis_course_history.json` | 同上 |
| `cache/sis/sis_academic_req.json` | 同上（专业/需求组信息） |
| `cache/sis/sis_pre_enroll.json` | 同上（HKUST 定制 Enrollment Summary：学校预选课） |

## 执行步骤（固定）

1. 跑 `python3 scripts/sis/parser.py --fetch --cookie-file credentials/cookies.txt`
   （AI 不接触 cookie，脚本负责；失败则提示用户更新 PS_TOKEN）
2. **入学年份**：按上面规则表判断（Transcript CGA 优先）
3. **年级**：`infer_year_of_study(admission_year, 目标学期)`
4. **专业**：优先从 AR 需求组名提取（"PHYS Required Course" → PHYS；"EXT (AI)" →
   extended_major=AI）；AR 缺失时问用户 first/second major / minor / extended major
5. **已修课程**：course history → `data/passed_courses.json`（code/name/credits/grade/term/status，
   status 映射：T→transferred、EX→exempted、AU→audit、I→incomplete、其余→taken/in_progress）
6. **学分与 CGA**：`credits_earned` 取 course history total_units；CGA 从 Transcript 取
   （无则 null）
7. **用户确认**：把画像要点列给用户（专业/入学年份/年级/学分/CGA），确认后
   `confirmed_by_user: true`；有出入按用户修正

## 总结结构（固定）

`data/profile.json`（schema: templates/schemas/profile.schema.json）：

```json
{
  "admission_year": "2023-24",
  "year_of_study": 4,
  "programs": {"first_major": "PHYS", "additional_major": [],
               "extended_major": "AI", "minor": []},
  "cga": 3.0,
  "credits_earned": 113.0,
  "school": "SSCI",
  "source": "SIS(transcript+course_history)",
  "confirmed_by_user": true
}
```

`data/passed_courses.json`（schema: passed_courses.schema.json）：全量已修，
含 transferred/exempted/audit（Step 3 pre-req 判定按"通过"处理，EX 视为满足）。

校验：
```bash
python3 scripts/harness/schema_validate.py --target data/profile.json
python3 scripts/harness/schema_validate.py --target data/passed_courses.json
```

## 确认点 P2（强制中断）— 画像 + 预选课二次确认

**SIS 提取完成后必须暂停，向用户展示画像摘要与预选课清单并等待确认，
确认前不得 `done phase2-profile`（也禁止携带未确认画像进入 Step 1）：**

```
画像摘要（来源: SIS transcript + course history）
- 入学年份：2023-24（推断依据：最早 term 2023-24 Fall）
- 年级：Year 4（2026-27 Fall）
- 专业：first=PHYS, extended=AI, minor=[]
- 已修学分：113.0 / CGA：3.0
- 已修课程：N 门（含 transferred/exempted/audit）

Pre-Enroll（学校预选课，SIS 默认学期 {term}）
- confirmed：COMP 2011 [L1]（3 学分）/ ...（无则写"空"）
- pending：...（无则写"空"）
- 说明：预选课将视为"已确定修读"——不重复推荐、排课时占用其时段
```

- 用户确认 → `confirmed_by_user: true` 写入 profile.json；
  预选课写入 `data/pre_enrolled.json`（schema: pre_enroll.schema.json）
- 用户修正 → 按用户值覆盖并重新校验 schema，再次确认
- 确认完成才 `checkpoint.py done phase2-profile`

## 异常处理（固定）

| 情况 | 处理 |
|---|---|
| SIS cookie 失效 | 提示用户更新 credentials/cookies.txt 的 PS_TOKEN，不猜测 |
| Transcript 抓取失败 | 降级用 course history 推断；再不行 USTSPACE settings；仍无则问用户 |
| 无 CGA 且无课程记录 | 视为大一新生（入学年份=当年），但仍需用户确认 |
| 专业与 AR 不符 | 以 AR 需求组为准并询问用户 |
| 用户修正画像 | 按用户值覆盖并重新校验 schema |

## 交接

- `data/profile.json` + `data/passed_courses.json` → Step 1（未修计算）
