---
name: step1-unmet-calculation
description: Step 1 未修课程计算。专业必修（database/curriculum）+ 今年可读 CC（wcq 下拉池，按 admission_year 匹配）− 已修（SIS 课程历史）= 未修列表，AI 解读 Note 语义后按固定结构总结保存为 data/unmet_courses.json。Use when computing which courses a student has not yet taken.
---

# Step 1 — 未修课程计算

## 公式（固定）

```
未修 = 专业必修（database/curriculum/{admissionYear}/{PROG}.json）
     + 今年可读 CC（data/cc_courses_{session}.json，wcq 按入学年份组匹配）
     − 已修（data/passed_courses.json，来自 SIS course history）
     − 预选课（data/pre_enrolled.json，学校已预选/已注册，视为"已确定修读"，不重复推荐）
```

- `database/common-core/{版本}.md` **不是课程来源**，仅提供 CC 结构规则（区域划分、
  home area、学分要求），用于从"可读 CC 池"中筛出该生**必须覆盖的区域**及其课程
- 专业名与本地 curriculum `title`/`program` 完全相符 → 直接用本地；不符/缺失 →
  按 web-crawl-guide §4 二次匹配

## 输入（先确认存在）

| 文件 | 来源 |
|---|---|
| `data/profile.json` | phase2 产物（admission_year / programs / credits_earned） |
| `data/passed_courses.json` | phase2 产物（已修课程，SIS course history 转换） |
| `data/pre_enrolled.json` | phase2 产物（学校预选课，P2 确认） |
| `database/curriculum/{year}/{PROG}.json` | prog-crs 预构建 |
| `data/cc_courses_{session}.json` | `scripts/wcq/crawler.py --admission-year {year}` 产物 |

## 执行步骤

1. 从 profile 取 admission_year → 确认 `cc_courses_{session}.json` 是匹配组的（web-crawl-guide §1b 映射）
2. 读本地 curriculum，展开 block/section/group：
   - **必修组**（required/fundamental/pre_major）→ 全部入列表，category=`major_required`
   - **选修组**（elective/other）→ 入列表，category=`major_elective`
   - 组内候选（pool/alternatives）→ 课程逐个入列表（同组共享 Note）
3. 读可读 CC 池，按 common-core 版本结构规则筛出该生必修区域（如 home area 外 4 区）的课程
   → category=`cc_required` / `cc_elective`
4. 用 passed_courses 排除已修（含 transferred/exempted/audit）
5. 用 `data/pre_enrolled.json` 排除学校预选课（confirmed + pending 均视为将修，
   不重复推荐；如预选课与未修清单同课则标注 `pre_enrolled` 并从推荐中移除）
6. **AI 解读 Note 语义**：OR/AND、计数（"any 2 of"）、跨组互斥 → 写入
   `note_interpretation`，课程归属不清的标记 `review_pending`（下一阶段人工/AI 复核）
7. 120 学分与 credit-reuse 检查：单门课若已计入其他要求组（exclusion/co-list），标注说明

## 总结结构（固定，必须按此写入 data/unmet_courses.json）

```json
{
  "generated_at": "ISO",
  "program": "PHYS",
  "intake_year": "2023-24",
  "graduation_target_credits": 120,
  "courses": [
    {
      "code": "PHYS 4191",
      "name": "Final Year Physics Project",
      "credits": 4.0,
      "category": "major_required|cc_required|major_elective|cc_elective|free_elective",
      "source_groups": [{"block": "...", "section": "...", "group": "...", "note": "Note 原文"}],
      "note_interpretation": "AI 对 Note 语义的解析（必修/候选池/计数）"
    }
  ]
}
```

校验：`scripts/harness/schema_validate.py --target data/unmet_courses.json`

## 确认点 P3（强制中断）— 未修清单确认

**AI 解读 Note 语义并生成未修清单后必须暂停，向用户展示摘要并等待确认：**

```
未修课程统计（{program}，{intake_year} 入学）
- 专业必修 x 门 / CC 必修 x 门 / 专业选修 x 门 / CC 选修 x 门 / 自由选修 x 门
- review_pending：{课程列表}（Note 语义不清，需用户/人工复核）
- 已排除已修 N 门（含 transferred/exempted/audit）
```

- 用户确认 → 进入 Step 2
- 用户指出遗漏/误收（如某门课已修、某组不该算必修）→ 修正 `data/unmet_courses.json`
  后重新校验
- 存在 `review_pending` 时**必须**在本步解决（含问用户），不得带入下一步

## 交接

产物给 Step 2（`scripts/rank/local.py`）作输入。若存在 `review_pending` 课程，先在
step1 阶段解决，不得带入下一步。
