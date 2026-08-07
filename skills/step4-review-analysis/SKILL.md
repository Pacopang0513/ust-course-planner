---
name: step4-review-analysis
description: Step 4 USTspace 评论分析。后台 job ustspace_pre 抓取评论（热度 top5 + 每导师 top5 + 导师统计 + 本学期导师最近 5 条）→ data/ustspace_reviews.json；ustplan step step4 生成基架后 AI 精读覆盖 data/review_summary.json（评分/教学/给分/工作量/推荐度 + D 组件 d_rating），--finalize 完成。Use when analyzing course reviews for candidate courses.
---

# Step 4 — USTspace 评论分析

## 触发

- step3 done + P4 确认后；抓取在 P2 提问前已后台启动（`ustplan job start ustspace_pre`）。

## 执行（ustplan）

```bash
python3 scripts/ustplan.py job status ustspace_pre    # 抓取完成？未完成继续等
python3 scripts/ustplan.py step step4                 # 基架生成（档位+今年导师+D 占位）
python3 scripts/ustplan.py step step4 --finalize      # AI 精读覆盖后完成本步
```

- 无评论/API error（`{"error":true}`）= 该课在 ust.space 无数据，正常现象，
  记入 failed[]，后续按公式得 0 分（风险课不推荐）；
- P4 计算（step5）前如仍未完成 → `ustplan job wait ustspace_pre`。

## AI 职责（精读范围收缩：只精读影响排课的候选，控制耗时）

1. **精读范围（固定）**：只精读以下子集，其余课程保留基架档位（评分由
   A/B/C 组件承担，D 缺失不阻塞）：
   - 每 bucket TOP3（course_scores.courses，排课主要候选）；
   - 全部 major_required / cc_required（必修必排）；
   - CC A/H/T 每区评分前 3（本学生需补的 CC 区域）；
   通常 20-30 门，禁止全量精读 60+ 门。
2. 每门精读课：读 `heat_top5` + 本学期任课教授（schedule sections instructors）
   的 `instructor_recent` 最近 5 条；记录评分倾向、给分松紧、工作量、考核形式、
   反复优缺点（≥2 条独立评论才记为共识）；
3. 矛盾或 <3 条评论 → 字段置 null + evidence_note；
4. **D 组件**：本学期任课教授最近 5 条评论精读 → `d_rating`（0-25）+ `d_note`
   （读了哪些/结论）；这是评分公式的 D 分量，越具体越好；
5. 未精读课程保持基架（d_rating=null → step5 按 0 分处理，不阻塞）。

## 确认点

- 本步无独立确认点（精读质量由 step5 评分结果在 P5 前整体核对）；
- 精读完成后 `--finalize`（自动校验 schema + 收录 manifest）。

## 交接

review_summary.json（含 D 组件）→ step5（bucket_score.py）；同文件供
phase4 报告"口碑摘要"引用。
