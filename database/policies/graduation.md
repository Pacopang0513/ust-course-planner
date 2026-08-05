# graduation.md — 毕业要求与课程结构

> 来源：Academic Regulations 2026-27 (AR 4)、Program & Course Catalog 2026-27、CLE (cle.hkust.edu.hk)
> 重要：课程结构按**入学年份（admissionYear）**版本执行。Common Core 各版本见 `../common-core/` 子目录（硬开关：入学年份），Major 课程要求见 `../curriculum/{year}/` 预构建数据。

## 1. 学士学位总体要求（AR 4.1）

1. 至少 **120 学分**（approved courses 或转学分）
2. 完成 **University Common Core Program**
3. 完成 **University English Language Requirement**
4. 完成 **University Legal Education Requirement**（2022-23 及以后入学）——不计学分，无 timetable 占用，学校自动 pre-reg，无需 AI 处理
5. 完成 School/AIS 要求（如有）
6. 完成至少一个 Major（或 School general degree 要求）

附加：
- 至少 60 个 HKUST 课程学分 + 至少 2 年 HKUST 全日制学习
- 在线课程学分最多计 9 学分（2025-26 及以前入学仅限 SPO 课程；2026-27 起含所有经批准在线学分）
- 学生须按入学年份对应的 Curriculum 完成学业

## 2. Common Core

按入学年份选择 `../common-core/` 下的对应版本文件（**只加载与 admissionYear 匹配的一个**）：

- 2021-22 及以前 → `../common-core/cc-2021-and-earlier.md`（36 学分制）
- 2022-23 ~ 2024-25 → `../common-core/cc-2022-2024.md`（30 学分制 v1）
- 2025-26 → `../common-core/cc-2025.md`（30 学分制 v2，含 SUS）
- 2026-27 及以后 → `../common-core/cc-2026-onward.md`（30 学分制 v3，含 HAIC）

## 3. English Language Requirement（2024-25 及以后入学）

全部学生：**LANG 1402（3 学分）** + 学院指定后续课：

| 学院 | 后续课程 |
|---|---|
| SBM | LANG 1406 |
| SENG | LANG 1407 |
| SHSS | LANG 1408 |
| SSCI | LANG 1409（OST 专业另需 LANG 3025/4010；IRE 另需 LANG 3027） |
| AIS | LANG 1406/1407/1408/1409 任选（ISD 另需 LANG 4032/4036） |

- 2022-23/2023-24 入学与 2021-22 及以前入学有不同 pathway（见 CLE 网站）
- 修完要求后可选修高级沟通课（Advanced Communication）

## 4. Major / Minor / 附加学位结构

- **Major 课程要求**：预构建数据，存放于 `../curriculum/{year}/{PROG}.json`（由 `scripts/prog_crs/build.py` 构建；用户导入 `user/` 的特殊资料可经 AI 总结补充）
- **Minor**：≥18 学分指定课程；需经 Minor 协调员批准注册
- **Additional Major**：≥20 学分 single-counted 课程（不可用于其他毕业要求，除 120 学分外）
- **Extended Major（Major+X）**：≥21 学分指定课程，且这些课程平均绩点 ≥2.15
- **Major 注册时限**：最迟在修满 60 学分所在学期结束时注册 Major；换 Major 需协调员批准
- **学位类型**：BSc / BEng / BBA；双学位需满足两个学位全部要求
- 规范学制 4 年；可经批准延长最多 1 年；学期：Fall（9-12 月）、Spring（2-5 月）为 Regular Term，另有 Winter、Summer

## 5. 来源链接

- Academic Regulations: https://registry.hkust.edu.hk/resource-library/academic-regulations-governing-ug-studies-2026-27
- Program Catalog: https://prog-crs.hkust.edu.hk/ugprog
- Common Core 各版本: https://uce.ust.hk/web/courses_2025/curriculum.html / https://uce.ust.hk/web/courses_2026/curriculum.html / https://uce.ust.hk/web/courses/course_curriculum.html
- English Pathways: https://cle.hkust.edu.hk/courses/pathways
