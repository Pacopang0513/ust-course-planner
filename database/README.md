# database/ — Agent 统一数据库

给 Agent 的事实性参考与课程数据的**唯一数据库**。本库只记录事实与结构化数据，不做分析判断；分析由流程 Agent 依据本库 + 用户资料完成。

由原 `knowledge/`（政策事实库）与 `data/` 中的公开预构建数据合并而来。

## 结构索引

| 子目录/文件 | 内容 | 写入者 | 何时查阅 |
|---|---|---|---|
| `policies/` | UST 政策事实库（grading / registration / graduation） | 开发期人工 | 评价给分、排课策略、毕业要求计算 |
| `common-core/` | Common Core 分入学年份版本（硬开关：admissionYear） | 开发期人工 | 推荐 CC 课、计算 CC 进度 |
| `curriculum/{year}/` | 各专业 major 课程要求候选索引（按入学年份） | `scripts/prog_crs/build.py` | 课程推荐、剩余学分计算 |
| `mappings/` | 每系 AR↔curriculum 覆盖规则 | 开发期人工 | mapper override |
| `build.json` | prog-crs 已构建年份标记 `{year: 构建时间}` | `scripts/prog_crs/build.py` | 判断预构建是否可用 |

> **不预构建 course_catalog**：课程详情（pre-req/exclusion/学分）是动态数据，
> 每个学生、每个目标学期面对不同的 catalog，由运行时抓取的 Class Schedule
> （`data/courses_{session}.json`，wcq/crawler.py，页内联 PRE-REQUISITE）提供；
> 需要单课详情时按需 `scripts/prog_crs/course_catalog.py --subject X --year Y`。

## 权限

- AI 只读，禁止修改（纳入 R1 只读完整性校验）
- `curriculum/`、`build.json`、`mappings/` 仅在构建/开发期由 scripts 或人工写入；`policies/`、`common-core/` 严格只读

## 构建预构建数据

```bash
python3 scripts/prog_crs/build.py --year <YEAR>       # 入学年份（如 2023-24 / 2026-27）
```

- 全量抓取 prog-crs 各专业 curriculum（仅 curriculum；catalog 按需单查，见上）
- 学生跟**入学年份**的 curriculum，由 `data/profile.json` 的 `admission_year` 决定加载哪份
- 课程是否本学年开设以 Class Schedule 为准（https://w5.ab.ust.hk/wcq/cgi-bin/）

## 使用规则（本地优先 + 二次匹配）

- 从画像取得专业（first/second major、minor）与 admissionYear
- 本地查找 `curriculum/{admissionYear}/{PROG}.json`：**SIS 专业名称与本地 `title`/`program` 完全相符 → 直接用本地，无需联网**
- 名称不符 / 本地缺失 / 年份未构建 → 联网抓取 prog-crs 对应专业页与本地二次匹配（课程代码集合、title），确认无误后使用；不一致以网络为准并告警

## 版本说明

- 政策主要基于 2026-27 Academic Regulations（2026 年 7 月更新），官方来源链接见各文件末尾
- Common Core 按入学年份分为 4 个版本文件，格式统一，仅加载与 admissionYear 匹配的版本

## 迁移说明（2026-08 重组）

- 原 `knowledge/`（policies + common-core）整体并入本目录；`knowledge/curriculum.md` 更名为 `policies/graduation.md`
- 原 `data/curriculum/`、`data/course_catalog/`、`data/prog_crs_build.json` 移入本目录；`data/major-curriculum/` 已废弃删除（功能由 `curriculum/` 取代）
- `data/` 仅保留运行时个人产物（profile / passed_courses / course_scores / checkpoint / mapping_result）
