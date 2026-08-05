# scripts/wcq/ — WCQ 上课时间抓取与冲突检测

基于公开 Class Schedule & Quota 页面（w5.ab.ust.hk/wcq，无需 cookie），
做选课前的**抓取**与**时间冲突检测**。抓取流程见 `skills/web-crawl-guide/SKILL.md`。

## crawler.py — 抓取（新增）

```bash
python3 scripts/wcq/crawler.py --session 2610          # 全量抓取 96 个 subject
python3 scripts/wcq/crawler.py --session 2610 --subject COMP
python3 scripts/wcq/crawler.py --session 2610 --force  # 强制重抓
python3 scripts/wcq/crawler.py --list-only             # 只列 subject
python3 scripts/wcq/crawler.py --selftest              # 解析器自测

# Common Core 课程（按入学年份组 4Y/CC22/CC25/CC26）
python3 scripts/wcq/crawler.py --admission-year 2026-27 --session 2610   # 自动选组
python3 scripts/wcq/crawler.py --cc-group CC26 --session 2610            # 显式指定组
```

- 原始 HTML → `cache/wcq/raw/{session}/{SUBJ}.html`（断点续抓，已存在跳过）
- 汇总 → `data/courses_{session}.json`（course 级：code/number/title/units/attributes[PRE-REQUISITE/EXCLUSION/...]；section 级：section/datetime/room/instructors/quota/enrol/avail/wait）
- **多时段合并**：`mainRow`（section 头）+ 后续 `otherRow`（同一 section 附加时段）合并为一个 section 的 datetime（逗号连接）
- 数据同时供：Step 3 过滤（开设/pre-reg/仅限专业）、Step 4 导师配对、Step 6 冲突检测

## Common Core 课程（新增）

索引页 "Select Common Core Course" 下拉按入学年份分组（4Y/CC22/CC25/CC26，与
`database/common-core/` 四版本一致），每区域页列出**今年开设**的 CC 课程（跨 subject）：

- 区域页 → `cache/wcq/raw/{session}/common_core/{GROUP}-{code}.html`
- 汇总 → `data/cc_courses_{session}.json`（area_code/area/course_count/courses）
- **404 = 该区域今年无课**（如 UxOP-UPOP/UCOP），记录 EMPTY 不重试
- 入学年份映射：≤2021→4Y；2022-2024→CC22；2025→CC25；≥2026→CC26

用法：Step 1 读 profile.admission_year → 抓对应组 → 得"今年可读 CC 课程池"。

## conflict.py — 时间冲突检测

```bash
# 指定 section（推荐）
python3 scripts/wcq/conflict.py --session 2610 \
    --courses "ACCT 2010:L02" "COMP 2011:L1" "MATH 2352"

# 不指定 section → 自动取该课第一个 section
python3 scripts/wcq/conflict.py --session 2610 --courses "COMP 2011" "PHYS 3152"

# 数据目录覆盖（默认 data/）
python3 scripts/wcq/conflict.py --session 2610 --courses "COMP 2011" --data-dir data

# 解析器自测
python3 scripts/wcq/conflict.py --selftest
```

退出码：0 = 无冲突；1 = 有冲突。

### datetime 解析设计（关键）

每门课 section 的时间字符串被解析为**多个槽** `(day, start_min, end_min)`：

| 输入格式 | 槽数 | 说明 |
|---|---|---|
| `TuTh 01:30PM - 02:50PM` | 2 | 多天前缀展开（Tu + Th 各一槽） |
| `Mo 04:00PM - 05:20PM, Fr 10:00AM - 11:20AM` | 2 | **不同天不同时段**（crawler 合并多时段后即此格式） |
| `01-SEP-2026 - 17-OCT-2026We 04:00PM - 05:50PM` | 1 | 日期窗口前缀忽略 |
| `TBA` / `TBD` | 0 | 无时间，标记提醒 |

冲突判定：两个槽**同一天**且时间区间重叠（`a.start < b.end and b.start < a.end`）。
