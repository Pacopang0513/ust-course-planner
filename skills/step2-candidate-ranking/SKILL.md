---
name: step2-candidate-ranking
description: Step 2 候选课程本地规则打分。按类别/课程等级/学分紧迫度确定性地为未修课程打分，取 Top N（默认 50）并按固定结构总结保存为 data/candidate_rank.json。Use when ranking un-taken courses to a shortlist.
---

# Step 2 — 候选课程本地规则打分（Top N）

## 目的

把 Step 1 未修列表压缩成 Top N（默认 50）候选池，后续步骤只对候选池做
schedule 过滤与评论分析。纯本地确定性规则，无网络、无 AI 判断。

## 输入

- `data/unmet_courses.json`（Step 1 产物，必填）
- `data/profile.json`（紧迫度计算：credits_earned / year_of_study）

## 执行（固定）

```bash
python3 scripts/rank/local.py --unmet data/unmet_courses.json \
    --profile data/profile.json --top 50 --output data/candidate_rank.json
```

## 规则（固定权重）

```
得分 = 类别优先级 × 0.40 + 课程等级 × 0.25 + 学分紧迫度 × 0.35
类别优先级: major_required=100 > cc_required=80 > major_elective=60 > cc_elective=40 > free_elective=20
课程等级:   1xxx-2xxx=100 > 3xxx=70 > 4xxx=40 > 其他=10
紧迫度:     (120 − credits_earned) / 剩余 Regular Term 数 × 4，封顶 100
```

权重与优先级在 `local.py` 内定义（`rules` 字段一并写入产物，便于追溯）。

## 总结结构（固定，写入 data/candidate_rank.json）

```json
{
  "generated_at": "ISO",
  "top_n": 50,
  "total_candidates": 120,
  "rules": {"category_weight": 0.40, "level_weight": 0.25, "urgency_weight": 0.35, "category_priority": {...}},
  "courses": [
    {"code": "COMP 2011", "name": "...", "credits": 4.0, "category": "major_required",
     "source_groups": [...], "rule_score": 87.5,
     "breakdown": {"category": 100, "level": 100, "urgency": 64.3}}
  ],
  "truncated": [{"code": "...", "rule_score": ..., "category": "..."}]
}
```

校验：`scripts/harness/schema_validate.py --target data/candidate_rank.json`

## 交接

- `courses[]` → Step 3 过滤输入
- `truncated[]` 保留为候补池（Step 3 移除过多时可补位，由 AI 决定）
