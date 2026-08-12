---
name: step4-review-analysis
description: Step 4 USTspace 评论分析。后台 job ustspace_pre 抓取评论（热度 top5 + 每导师 top5 + 导师统计 + 本学期导师最近 5 条）→ data/ustspace_reviews.json；ustplan step step4 生成基架后 AI 精读覆盖 data/review_summary.json（评分/教学/给分/工作量/推荐度 + D 组件 d_rating），--finalize 完成。Use when analyzing course reviews for candidate courses.
---

# Step 4 — USTspace 评论分析

## 触发

- step3 done + P3 确认后；抓取在 P2 提问前已后台启动（`ustplan job start ustspace_pre`）。

## 执行（ustplan）

```bash
python3 scripts/ustplan.py job status ustspace_pre    # 抓取完成？未完成继续等
python3 scripts/rank/review_scope.py --filter data/filter_report.json \
    --reviews data/ustspace_reviews.json --session <S> [--top 3]  # 精读范围（固定规则）
python3 scripts/ustplan.py step step4                 # 基架生成（档位+今年导师+D 占位）
python3 scripts/ustplan.py step step4 --finalize      # AI 精读覆盖后完成本步
```

- 无评论/API error（`{"error":true}`）= 该课在 ust.space 无数据，正常现象，
  记入 failed[]，后续按公式得 0 分（风险课不推荐）；
- step5 评分前如仍未完成 → `ustplan job wait ustspace_pre`。

## AI 职责（精读范围已固化，不自行构建）

1. **精读范围（固定）**：直接运行 `scripts/rank/review_scope.py` 生成
   `data/review_scope.json`（scope[]）+ `data/review_digest.md`（每门课热度摘要）。
   规则（脚本固化，AI 不临场推导）：
   - major_required / cc_required 桶 → 全部精读；
   - 其余桶（cc_elective / major_elective）→ 按 review_count 取 TOP N（默认 3）。
2. 每门精读课：读 `data/review_digest.md`（heat_top5 摘要 + 今年任课教师）；
   记录评分倾向、给分松紧、工作量、考核形式、反复优缺点（≥2 条独立评论才记为共识）；
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
