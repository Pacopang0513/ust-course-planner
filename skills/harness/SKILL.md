---
name: harness
description: 主编排 skill。固定调用顺序 phase1-input → phase2-profile → step1..6（承载于 phase3-course-analysis 检查点）→ phase4-report → phase4.5-must-take，异常处理矩阵与 checkpoint 推进规则。Use when orchestrating the full course planning flow.
---

# Harness — 主编排

## 固定调用顺序（R4 checkpoint 链）

```
phase1-input           输入准备（skills/phase1-input）
  → [P1] 用户提供 cookie + 目标学期确认
  → phase2-profile     画像（skills/phase2-profile）
  → [P2] 画像二次确认（用户核对专业/入学年份/年级/学分/CGA）
  → phase3-course-analysis  承载 Step 1-6：
       step1-unmet-calculation      (skills/step1-*)
       → [P3] 未修清单确认（Note 语义 + review_pending 复核）
       step2-candidate-ranking
       step3-schedule-filter
       → [P4] 过滤结果确认（移除原因 + 复核标记）
       step4-review-analysis
       step5-score-fusion
       step6-timetable-planning
       → [P5] 方案展示与选择
  → phase4-report      总结报告（skills/phase4-report）
  → phase4.5-must-take 强制选课（skills/must-take-course-insertion）
```

**确认点（P1-P5，强制中断）**：各 phase/step 的 skill 内均有"确认点"小节，
AI 必须暂停等待用户响应后才能 `checkpoint.py done` 推进；用户修正即覆盖并重校验。
无用户响应时禁止跳过（跳确认点 = 违规推进）。

每个阶段以 `scripts/harness/checkpoint.py begin/done {phase}` 推进；
`begin` 校验前置已完成，跳阶段即失败（R4）。

## 阶段 ↔ 检查点对照

| 检查点阶段 | 执行的 skills | 确认点 | 主要产物 |
|---|---|---|---|
| phase1-input | phase1-input | P1（cookie + 目标学期） | checkpoint、目标学期/session |
| phase2-profile | phase2-profile | P2（画像 + 预选课二次确认） | profile.json、passed_courses.json、pre_enrolled.json |
| phase3-course-analysis | step1 → step6 依次 | P3（未修清单）/ P4（过滤结果）/ P5（方案选择） | unmet/candidate_rank/filter_report/ustspace_reviews/review_summary/course_scores/cc_courses/timetable_plan |
| phase4-report | phase4-report + enrollment-dates-reminder | —（报告即交付物） | final_report.md |
| phase4.5-must-take | must-take-course-insertion | 用户指定课程询问 | 调整后 timetable_plan（可选） |

## 数据抓取时机（web-crawl-guide 固化）

- wcq subject 页：step3 前（`--session`）
- wcq Common Core 池：step1 前（`--admission-year`）
- SIS：phase2（cookie）
- USTspace：step4（cookie）
- 先查 cache 再联网；产物落 data/ 或 cache/

## 异常处理矩阵（固定）

| 情况 | 处理 |
|---|---|
| SIS cookie 失效 / 抓取失败 | 停在此步，引导用户跑 `scripts/cookies_setup.py`（交互粘贴失效键，自动验证）后重跑 `--check` 确认；不猜测数据 |
| USTspace cookie 失效 | 同上引导重获取；评论抓取失败课程标记 failed[]，继续其余 |
| 本地 curriculum 缺失 | 二次匹配（web-crawl-guide §4）；仍失败则明确告知不可计算 |
| 过滤后候选过少（<15） | 从 candidate_rank.truncated 补位重跑 step3 |
| 用户指定课程冲突 | 用户取舍（must-take skill），不擅自决定 |
| 任意 step 产物 schema 校验失败 | 停在本 step 修复产物，不携带坏数据前进 |

## 校验（每阶段收尾执行）

```bash
python3 scripts/harness/schema_validate.py --dir data --dir output
```

全流程完成后再跑 R1-R6（`scripts/harness/test_runner.py --case scripts/tests/{demo,rank}`）
可选——正常运行的产物合规由阶段内校验保证。
