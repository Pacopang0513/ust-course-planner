---
name: step5-score-fusion
description: Step 5 合成排名。将规则分（Step 2）与 USTspace 口碑（Step 4 总结）合成为吸引力 + 置信度，按固定结构总结保存为 data/course_scores.json（含 score_reason 可追溯）。Use when fusing rule scores and review signals into a final ranking.
---

# Step 5 — 合成排名（吸引力 + 置信度）

## 目的

把 Step 2 规则分与 Step 4 口碑信号合成最终排名，作为 Step 6 编排的输入。
每门课的得分构成**写入 score_reason**，保证可追溯。

## 输入

| 文件 | 来源 |
|---|---|
| `data/filter_report.json`（kept[]） | Step 3 产物 |
| `data/ustspace_reviews.json` | Step 4 抓取产物（评论数/四维评分） |
| `data/review_summary.json` | Step 4 AI 精读总结（可选，作口碑调整依据） |

## 执行（固定）

```bash
python3 scripts/rank/final.py --filter data/filter_report.json \
    --reviews data/ustspace_reviews.json --output data/course_scores.json
```

## 合成规则（固定）

```
吸引力 = 规则分 × 0.60 + 口碑分 × 0.40
口碑分 = 课程四维均分归一化 × 0.40 + 评论热度(评论数/20×5 封顶100) × 0.60
置信度分档 = 评论数 ≥100 → high(90) / ≥20 → medium(60) / ≥1 → low(30) / 0 → none(10)
review_confidence 字段按档位写 high/medium/low（none 降为 low）
```

- 若 `review_summary.json` 存在：AI 可用其 `recommendation`/`grading`/`workload`
  对口碑分做 ±10 内的调整，并在 `score_reason` 注明（如 "AI 调 +5: 导师口碑好"）
- 排名按 score 降序；分数相同按评论数多的优先

## 总结结构（固定，写入 data/course_scores.json）

```json
{
  "courses": [
    {"code": "PHYS 4191", "name": "...", "credits": 4.0,
     "score": 65.36, "score_reason": "rule=87.5(60%), ustspace口碑=32.0(40%), 均分=4.10/5, 评论数=4",
     "review_count": 4, "review_confidence": "low",
     "open_this_year": true,
     "attractiveness": 65.36, "confidence_score": 30,
     "category": "major_required"}
  ],
  "generated_at": "ISO"
}
```

校验：`scripts/harness/schema_validate.py --target data/course_scores.json`

## 交接

- 排名 `courses[]` → Step 6 编排（按名次优先入排）
- 每门课的 `score_reason` 直接供 phase4 报告引用
