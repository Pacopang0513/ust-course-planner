# curriculum/ — Common Core 分版本记录

## 硬性开关：入学年份（admissionYear）

| 入学年份 | 适用的 Common Core 文件 | 学分制 |
|---|---|---|
| 2021-22 及以前 | `cc-2021-and-earlier.md` | 36 学分制 |
| 2022-23 ~ 2024-25 | `cc-2022-2024.md` | 30 学分制 v1 |
| 2025-26 | `cc-2025.md` | 30 学分制 v2（含 SUS） |
| 2026-27 及以后 | `cc-2026-onward.md` | 30 学分制 v3（含 HAIC） |

**使用规则**：先读取用户画像中的 admissionYear → 据此仅加载对应的一个 CC 版本文件，其他版本不加载（避免歧义与 token 浪费）。Major 课程要求为预构建数据，存放于 `../curriculum/{year}/`（由 `scripts/prog_crs/build.py` 构建）。
