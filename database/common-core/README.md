# curriculum/ — Common Core 分版本记录

## 硬性开关：入学年份（admissionYear）

| 入学年份 | 适用的 Common Core 文件 | 学分制 |
|---|---|---|
| 2021-22 及以前 | `cc-2021-and-earlier.md` | 36 学分制 |
| 2022-23 ~ 2024-25 | `cc-2022-2024.md` | 30 学分制 v1 |
| 2025-26 | `cc-2025.md` | 30 学分制 v2（含 SUS） |
| 2026-27 及以后 | `cc-2026-onward.md` | 30 学分制 v3（含 HAIC） |

**使用规则**：先读取用户画像中的 admissionYear → 据此仅加载对应的一个 CC 版本文件，其他版本不加载（避免歧义与 token 浪费）。Major 课程要求为预构建数据，存放于 `../curriculum/{year}/`（由 `scripts/prog_crs/build.py` 构建）。

## 区域与 home area 速查（AI 决策前直接查，不重复推导）

| 项目 | 结论 |
|---|---|
| 区域代码 | 20=CTDL（选修，可替代）、21=HMW、22=E-Comm、23=C-Comm、24=A、25=H、26=S、27=T、28=SA、29-32=UxOP（UROP/UTOP/UPOP/UCOP，选修） |
| Foundations | HMW + E-Comm + C-Comm 必修（各 ≥1 门）；CTDL 选修（缺额可由其他区域补） |
| Broadening | **home area 之外 ≥12 学分且覆盖 ≥4 个不同区域**（A/H/S/T/SA）；不足可补任意区域（含 home） |
| home area 映射 | SSCI 全部→S；SENG 多数→T；BIEN/CENG/EEEN→S+T；COSC/COMP→T；SBM 多数→SA；GCS→H+SA；QSA→SA；EVMT→SA；ISDN→T |
| Experiencing | UxOP 四选一（选修 0-3 学分）；UROP 需预备课 + UROP 3200 |
| 通用 | 课程须在列出的学年内修读才计入 CC；跨区域课只能计入一个区域；计入 School/Major 的课程不可重复计 CC（credit reuse） |

**核查脚本（不用 AI 手写比对）**：`python3 scripts/rank/cc_status.py --passed data/passed_courses.json
--admission-year <AY> --major <MAJOR>` → 输出各区域已修/未修 + Broadening 12 学分
4 区域结论（含 1 学分课 12 学分下限提示）；区域表 `areas_{GROUP}.json` 的
`code_area` 为课程→区域唯一映射。
