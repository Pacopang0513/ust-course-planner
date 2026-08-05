---
name: step4-review-analysis
description: Step 4 USTspace 评论分析。对保留候选抓取 USTspace 评论（热度 top5 + 今年导师 top5），AI 按固定结构精读总结为 data/review_summary.json（评分/教学/给分/工作量/考试/推荐度）。Use when analyzing course reviews for candidate courses.
---

# Step 4 — USTspace 评论分析

## 目的

为过滤后的候选课程收集 USTspace 口碑，AI **精读**热度 top5 评论与**今年导师**（
schedule 中的 instructor）的 top5 评论，按固定结构总结，供 Step 5 合成排名与
最终报告引用。

## 输入

| 文件 | 来源 |
|---|---|
| `data/filter_report.json`（kept[]） | Step 3 产物 |
| `data/courses_{session}.json` | 今年导师名单（section.instructors） |
| `credentials/cookies.txt` | `ustspace_session`（scripts 读取，AI 不接触） |

## 执行（固定）

```bash
# 抓取全部保留候选（scripts 经 cookie 读取，AI 不碰明文）
python3 scripts/ustspace/crawler.py --codes-file data/filter_report.json \
    --cookie-file credentials/cookies.txt
# 或按课程逐个（--codes "COMP 2011"），原始 JSON 缓存在 cache/ustspace/raw/
```

产物 `data/ustspace_reviews.json`：每课 review_count / 四维评分 / heat_top5 /
instructor_top5（热度 = vote_count 降序）。

## AI 精读步骤（固定）

1. 对每门候选课读 `heat_top5`（全局热度）+ 该课**今年导师**（来自 schedule，
   名字匹配 `instructors[]`）的 `top5` 评论；评论不足 5 条读全部
2. 记录关键信号：评分倾向（rating_content/teaching/grading/workload）、给分松紧、
   工作量、考试形式（has_midterm/final/assignment/project/attendance）、
   反复出现的优缺点（≥2 条独立评论提及才记为"共识"）
3. 评论矛盾或样本过少（<3 条）→ 对应字段标 `null` + `evidence_note` 说明，
   **不得编造**
4. 按下方固定结构写入 `data/review_summary.json`

## 总结结构（固定，新增 schema: templates/schemas/review_summary.schema.json）

```json
{
  "generated_at": "ISO",
  "session": "2610",
  "courses": [
    {
      "code": "COMP 2011",
      "name": "Programming with C++",
      "review_count": 319,
      "summary": {
        "overall_rating": 4.1,
        "strengths": ["讲课清晰", "作业有助理解"],
        "weaknesses": ["工作量偏大", "给分后段严"],
        "grading": {"trend": "lenient|fair|strict|mixed", "note": "..."},
        "workload": {"level": "light|medium|heavy|mixed", "note": "..."},
        "assessment": ["midterm", "final", "assignment", "project"],
        "recommendation": "highly_recommended|recommended|mixed|not_recommended",
        "recent_trend": "近 2 学期评论变化（如新生评价更积极）或 null",
        "evidence_note": "样本/矛盾说明，无则空"
      },
      "instructors": [
        {"name": "LI, Xin", "teaching_this_year": true,
         "rating": 4.2, "style": "板书推导细，节奏偏快", "notes": "给分中等"}
      ]
    }
  ]
}
```

- `instructors[]` 覆盖该课全部今年导师；无评论的导师 `rating`/`style` 为 null
- 校验：`scripts/harness/schema_validate.py --target data/review_summary.json`

## 交接

- `data/review_summary.json` → Step 5 合成排名的口碑信号来源
- 同文件在 phase4 报告中作为每门课的"口碑摘要"引用（含证据 hash 可溯源）
