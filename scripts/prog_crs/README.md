# scripts/prog_crs/ — prog-crs 预构建

公开静态数据（Program & Course Catalog），离线批量构建一次，phase3 运行时只读消费。

## 年份版本化（重要）

curriculum 与课程目录都**按入学年份**版本化——学生跟的是**入学年份**那份，
不是当年。目录结构：

```
cache/prog-crs/raw/{year}/{code}.txt         # 原始文本（year = 入学年份，如 2026-27）
cache/prog-crs/{year}.manifest.json          # 该年份全量清单
database/curriculum/{year}/{code}.json       # 候选索引
database/course_catalog/{year}/{subj}.json   # 课程详情
database/build.json                          # 已构建年份标记 {year: 构建时间}
```

构建时用 `--year` 指定年份；harness 按 `profile.admission_year` 决定构建/读取哪份。
同一台机器可同时保留多个年份版本（多用户/换专业）。

## 模块

| 脚本 | 功能 | 产物 |
|---|---|---|
| `crawler.py` | 索引 → 各专业页提取 "Major Requirements" PDF href → 下载 → pdftotext | `cache/prog-crs/raw/{year}/` |
| `parser.py` | curriculum 文本 → 候选索引（块/节/组/课程，Note 原文保留） | `database/curriculum/{year}/` |
| `course_catalog.py` | ugcourse 课程详情（pre-req/exclusion/学分/描述） | `database/course_catalog/{year}/` |
| `build.py` | 一键编排 crawler + parser + course_catalog | `database/build.json` 标记 |
| `fixtures/` | parser selftest 片段（覆盖 edge case） | — |

## 解析器设计（parser.py）

- **只还原结构，不做语义判断**：Note（布尔 OR/AND、计数、条件、跨组互斥）一律原文保留，由 phase3 AI 解释
- 产物是"候选索引"：每个要求组 = 候选课程 + Note 原文 + 学分范围
- 组内备选课靠"相对缩进比组头深"判定（不依赖绝对列宽，跨文档缩进不同）
- 覆盖的 PDF 结构：Pre-major / Fundamental / Required / Elective / Track / Option / Other(s)、Area 子列表、无 subject 组头、纯散文组、页脚与 Remarks

## 构建

```bash
python3 scripts/prog_crs/build.py                      # 默认 2026-27
python3 scripts/prog_crs/build.py --year 2025-26       # 其他入学年份
python3 scripts/prog_crs/parser.py --selftest          # 回归自测
```

## 与 SIS AR 的关系

curriculum 是权威**结构**（按入学年份固定），SIS Academic Requirements 是官方**进度**（每年 10 月更新）。
两者以课程代码 join；结构对不齐时以 curriculum 为准并告警。

## 运行时使用策略（本地优先 + 二次匹配）

1. phase3 从画像取得专业（first/second major、minor）与 `admissionYear`
2. 本地查找 `database/curriculum/{admissionYear}/{PROG}.json`（`build.json` 记录已构建年份）
3. **SIS 专业名称与本地文件 `title`/`program` 完全相符** → 直接用本地文件，无需联网
4. 否则（名称不符 / 本地缺失 / 年份未构建）→ 联网抓取 prog-crs 对应专业 curriculum，与本地比对（课程代码集合、title），确认无误后使用；不一致以网络为准并记录告警
