---
name: step5-score-fusion
description: Step 5 Bucket 评分合成。ustplan step step5 执行 scripts/rank/bucket_score.py：A+B+C+D（课程总评/本学期教授/热度档位/AI 精读 D），每栏位取 TOP N（默认 3）汇总 data/course_scores.json（score_components 可追溯）；权重参数来自 config/ustplan.json → scoring。Use when fusing scores into the final per-bucket ranking.
---

# Step 5 — Bucket 评分合成（A+B+C+D）

## 触发

- step4 done 后（`ustplan step step5`）。

## 执行（ustplan 合约）

```bash
python3 scripts/ustplan.py step step5
```

- 输入：filter_report（kept[]）+ ustspace_reviews（A/B/C）+ review_summary（D）+
  courses_{session}（本学期教授）+ unmet（桶元数据）；
- 公式（参数全部来自 config/ustplan.json → scoring，纯函数在 scoring.py）：

```
课程得分 = A + B + C + D                        （满分 100，可负分）
A = (课程四维均分 − baseline) / baseline × wA     # 均分<baseline 倒扣；新课 → 0
B = (本学期教授评分综合 − baseline) / baseline × wB
    教授评分综合 = Σ(维度均分 × 权重)；评论 <min_reviews 每缺 1 条降权；新教授 wB=0
C = 热度档位分；评论 < min_reviews_for_score → 总分直接 0
D = 本学期任课教授最近 5 条评论 AI 精读（0~25，review_summary.d_rating）
major_required 低阶加分：1xxx +5% / 2xxx +3% / 3xxx +1%（负分不乘）
```

- 每栏位取 `top_per_bucket` 门 → 总表；栏位并列不混排（防选重/选多）；
  其余进 ranked_out 备选池（must-take/多样性换课用）。

## AI 职责

- 核对 score_reason 与组件分合理性（D 组件缺失的课应在 P5 前提示）；
- 无评论新课（<5 条）→ 0 分；差评课（<2.5）→ 负分垫底——报告引用 score_reason。

## 确认点

- 本步无独立确认点；评分结果随 step6 方案在 P5 一并展示。

## 交接

course_scores.json → step6（planner.py，按栏位配额 + 目标学分编排）。
