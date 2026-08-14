# COVERAGE_CHECK — 五类别覆盖率硬检查（P3 前门禁）

> 目的：在向用户展示"全部未修课程"并请求 P3 确认**之前**，用硬性逻辑验证
> 清单确实覆盖五大类别：**major / extended_major / minor / school requirement /
> common core**。任何 FAIL 都禁止推进（`ustplan step step1` 后置自动执行，
> 也可手动 `ustplan coverage --session <S>`）。
> 本文件同时是**数据源登记与经验记录**：每个类别去哪搜、地址是什么。

## 运行方式

```bash
python3 scripts/ustplan.py coverage --session 2610     # 手动（0=通过 1=FAIL 2=仅WARN）
python3 scripts/ustplan.py step step1                  # step1 后置自动执行（FAIL 即拦截）
python3 scripts/harness/coverage_check.py --session 2610   # 直接跑
```

## 数据源登记（每类别在哪搜索、地址是什么）

| 类别 | 数据源文件 | 抓取地址 / 命令 |
|---|---|---|
| major / additional_major | `database/curriculum/{AY}/{PROG}.json` | `prog-crs.hkust.edu.hk/ugcourse/{AY}/{PROG}/`；`scripts/prog_crs/build.py --year {AY}` |
| extended_major | `database/curriculum/{AY}/EXTM-{CODE}.json` | 同上 `.../EXTM-{CODE}/`（如 `EXTM-AI`） |
| minor | `database/curriculum/{AY}/MINOR-{CODE}.json` | 同上 `.../MINOR-{CODE}/` |
| school requirement | `database/curriculum/{AY}/SREQ-{SCHOOL}.json` | 同上 `.../SREQ-{SCHOOL}/`（SSCI/SENG/SBM） |
| common core 池 | `data/cc_courses_{SESSION}.json` | `w5.ab.ust.hk/wcq/cgi-bin/{SESSION}/common_core/{GROUP}/{AREA}`；`scripts/wcq/crawler.py --admission-year {AY} --session {SESSION}` |
| common core 区域表 | `database/common-core/areas_{GROUP}.json` | `scripts/wcq/cc_areas.py --admission-year {AY}`（GROUP 按入学年份：CC22/CC25/CC26） |
| **SIS 权威（AR）** | `cache/sis/sis_academic_req.json` | SIS Student Center → Academics → Academic Requirements 页；`scripts/sis/parser.py --fetch` |
| 已修 / 预选 | `data/passed_courses.json` / `data/pre_enrolled.json` | SIS Course History / Enrollment Summary（sis_fetch job） |

## 检查逻辑（硬性，AI 不得豁免）

1. **major**：curriculum 文件存在；SIS AR 中主修组的 `not_taken` 课程必须全部
   被"已考虑"覆盖（未修候选 ∪ 今年未开设移除 ∪ 已修）。
2. **extended_major**：`EXTM-{code}.json` 存在；AR 中 EXT 组 `not_taken` 全覆盖。
3. **minor**：每个副修 `MINOR-{code}.json` 存在（缺失仅 WARN）。
4. **school requirement**：`SREQ-{school}.json` 存在；无 school 桶 = 已全部满足（OK）。
5. **common core**：`cc_courses_{session}.json` 必须存在（否则 CC 缺口无法核算
   → **FAIL**）；AR 显示 CC 未满足但清单无 cc 桶 → **FAIL**。
6. **规则排除登记**：AR `not_taken` 但清单里没有的课，必须能解释——
   - 备选课：出现在某未覆盖 bucket 的 note 里（如 capstone "PHYS 4191 OR
     PHYS 4291 OR (SCIE 3500 AND SCIE 4500)"）
   - 规则排除：`database/course_notes/` 中的 course_notes（ext_capstone_pairing /
     h_course_equivalence / track 限制）——如 EMIA 4991（主修含 capstone 只能
     EMIA 4990）、PHYS 4191（Honors 只能 4291）、SCIE 3500/4500（IRE track 专属）
   - 两者都无法解释 → **FAIL（漏算）**

## 常见 FAIL 与修复

| FAIL | 原因 | 修复 |
|---|---|---|
| CC 课程池缺失 | `wcq_full` 启动时入学年份未知，未抓 CC | `python3 scripts/wcq/crawler.py --admission-year {AY} --session {SESSION}`（subject 页已缓存，秒级） |
| AR 未修 X 未被覆盖 | step1 漏算（如共享课去重、等效课未识别） | 修 buckets.py 后 `step step1 --force` 重跑 |
| 学院/副修桶缺失 | 可能全部满足（WARN）或漏算 | 核对 AR 后人工确认 |

## CC 缺口核算规则（30 学分制 v1/v2，2026-08 用户规则落库）

**口诀：UROP/CTDL 以及 CC 五个类别加起来 18 学分**（12 Broadening + 3 CTDL +
3 UxOP）。官方结构：Foundations 12-15（HMW/E-Comm/C-Comm 必修 + CTDL 选修）、
Broadening 12（home 外 ≥12 学分且 ≥4 个不同区域，不足可补任意区域含 home）、
Experiencing 0-3（UxOP 选修）。

- CTDL 与 UxOP 均为**选修**，未修时缺额由任意其他区域 CC 课程替代
  （SIS AR 明文："CTDL and Experiencing common core courses can be substituted
  by any CTDL, E-Comm (Advanced Communication), C-Comm, Broadening or UxOP
  course"）。
- 脚本行为（`buckets.py` → `cc_substitute_quota` + `cc-extra` 桶）：
  - 区域桶照旧：未满足区域（如 A/H/T）各 quota 1；
  - 新增 `cc-extra` 桶：配额 =（UxOP 未修？1：0）+（CTDL 未修且本年无 CTDL
    开课？1：0），候选 = **全部 CC 池课程（允许搜索已完成区域，如 S/SA 的
    第二门）**；
  - 提示语：优先建议按主修相关区域选择（如 PHYS+AI → T/S，grading 优势）。
- 例（PHYS 2023-24 入学，已修 S/SA）：缺口 = A/H/T 3 门（9 学分）+ cc-extra
  2 门（6 学分）= 15 学分；保守口径 18 学分（Broadening 全量 12 + 替代 6）。
