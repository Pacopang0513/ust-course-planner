---
name: step3-schedule-filter
description: Step 3 候选课程过滤。对照本学年 Class Schedule（wcq 抓取）删除今年未开设与 pre-requisite 明确不满足的课程，记录移除原因并按固定结构总结保存为 data/filter_report.json。Use when filtering candidates against the current class schedule.
---

# Step 3 — Schedule 过滤（50 → 50-x）

## 目的

对照**本学年实际开设情况**过滤候选池，只保留今年能选且 pre-req 满足的课。
移除过程**逐条记录原因**，供 AI 复核与用户知悉。

## 输入

| 文件 | 来源 |
|---|---|
| `data/candidate_rank.json` | Step 2 产物 |
| `data/courses_{session}.json` | `scripts/wcq/crawler.py --session {s}` 产物（含 pre-req/exclusion/Remarks） |
| `data/passed_courses.json` | 已修课程（pre-req 判定） |
| `database/course_catalog/{year}/` | 兜底 pre-req（schedule 页无 PRE-REQUISITE 时） |

## 执行（固定）

```bash
python3 scripts/rank/filter.py --candidates data/candidate_rank.json \
    --session 2610 --passed data/passed_courses.json \
    --output data/filter_report.json
# kept < 15 时自动补位（从 Step 2 truncated 候补池按分数补入）：
python3 scripts/rank/filter.py --candidates data/candidate_rank.json \
    --session 2610 --passed data/passed_courses.json --fill 15
```

## 过滤规则（固定）

| 规则 | 判定 | 结果 |
|---|---|---|
| 今年未开设 | 课程不在 `courses_{session}.json` | **删除**（not_offered_this_year） |
| pre-req 明确不满足 | 表达式递归求值（脚本内实现，**OR 优先**：顶层 OR 分支任一满足即可，分支内 AND 全满足；括号组递归——与 UST 真实文本格式一致） | **删除**（prereq_not_met:缺失列表） |
| pre-req 无法解析 | 文本无课程代码 / 结构异常 | **保留 + 标记** prereq_unknown（AI 复核，不擅自删） |
| 仅限特定专业 | Remarks 含 "For XXX students only" | **保留 + 标记** restricted（AI/用户确认） |

- 移除数量与原因必须总结在产物 `removed[]`；`kept[]` 的标记不阻止保留
- pre-req 的最终解释权在 AI（脚本保守判定，AI 复核豁免可能性：教授豁免/等价课程）

## 总结结构（固定，写入 data/filter_report.json）

```json
{
  "generated_at": "ISO",
  "session": "2610",
  "input_count": 50,
  "kept_count": 38,
  "removed_count": 12,
  "note": "removed=硬性删除；kept 的 filter_reasons 可能含 prereq_unknown/restricted，由 AI 复核",
  "kept": [
    {"code": "PHYS 4191", "name": "...", "rule_score": 87.5, "category": "major_required",
     "schedule_found": true, "sections": 1, "filter_reasons": []}
  ],
  "removed": [
    {"code": "ACCT 4720", "name": "...", "rule_score": 71.5, "category": "major_elective",
     "schedule_found": false, "sections": 0, "filter_reasons": ["not_offered_this_year"]}
  ]
}
```

校验：`scripts/harness/schema_validate.py --target data/filter_report.json`

## 确认点 P4（强制中断）— 过滤结果确认

**过滤完成后必须暂停，向用户展示移除统计与原因分类，等待用户确认：**

```
过滤结果（输入 N → 保留 M / 移除 K）
- not_offered_this_year：{列表}
- prereq_not_met：{列表（含缺失课程）}
- 需 AI/用户复核（保留但标记）：prereq_unknown / restricted → {列表}
- 补位情况（kept < 15 时从 truncated 补位）：{说明}
```

- 用户确认 → 进入 Step 4
- 用户对某门移除课有异议（如教授豁免 / 等价课程）→ 手动放回 kept 并标注
  `filter_reasons: ["user_overridden"]`，重新校验
- 补位重跑后同样需展示并确认

## 交接

- `kept[]` → Step 4 评论抓取 + Step 5 合成排名
- 若 `kept` 过少（< 15），AI 可从 Step 2 的 `truncated[]` 候补池补位并重跑本步
- 本步结论（移除了哪些、为什么）在最终报告 phase4 中向用户说明
