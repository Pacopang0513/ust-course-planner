# UST 课表 — 自动选课 Agent Harness

基于我校排课流程的自动选课辅助工具（opencode skills + Python 脚本混合实现）。

## 快速开始（3 步）

```bash
# 1. 装依赖（Windows 上用 python 或 py 代替 python3）
python3 -m pip install requests jsonschema

# 2. 配置 cookie（AI 不接触明文；交互引导 → 粘贴 → 自动验证）
python3 scripts/cookies_setup.py --print-bookmarklet   # 可选：登录页一键复制书签
python3 scripts/cookies_setup.py                       # 粘贴 PS_TOKEN / ustspace_session

# 3. 开始流程（由 harness skill 主编排，从 phase1-input 起）
#    在 opencode 中发起任务即可；流程含 5 个人工确认点（P1-P5），
#    无确认不推进（见 skills/harness/SKILL.md）
```

> Windows 提示：本仓库命令统一写 `python3`，Windows 一般用 `python`（或 `py`）代替。
> 依赖仅 `requests`（抓取）与 `jsonschema`（R2 校验）。

## 目录总览

| 目录 | 用途 | git |
|---|---|---|
| `user/` | 用户输入资料（major 手册、CC Curriculum） | 忽略 |
| `credentials/` | cookie 凭据（加密，AI 不可读） | 忽略 |
| `database/` | Agent 统一数据库（政策/CC/课程预构建） | 跟踪 |
| `skills/` | 流程 skills（harness → phase1/2/4 → step1-6） | 跟踪 |
| `scripts/` | Python 脚本（抓取/解析/打分/校验/harness/统计） | 跟踪 |
| `cache/` | 原始抓取缓存 | 忽略 |
| `data/` | 运行时个人产物（交付态为空，真实运行从 phase1 重建） | 忽略 |
| `output/` | 课程总结与课程表方案 | 忽略 |
| `templates/` | 通用输出模板（JSON schemas） | 跟踪 |

## 流程

`harness` skill 主编排（固定顺序，checkpoint 强制）：

```
phase1-input → phase2-profile（画像：Transcript 权威优先）→ phase3-course-analysis
  （step1 未修 → step2 Top50 → step3 schedule 过滤 → step4 评论分析 → step5 合成排名
   → step6 课表编排）→ phase4-report（+ 选课时间提醒）→ phase4.5-must-take（可选）
```

**Major curriculum 双来源（本地优先 + SIS AR 回退）**：
- 本地优先：SIS 专业名与 `database/curriculum/{admissionYear}/` 本地文件完全相符时直接使用（无需联网）；
  不符/缺失时联网抓取 prog-crs 与本地比对确认（`scripts/prog_crs/README.md`）。
- **AR 回退**：旧入学年份（如 2023-24）prog-crs 已下线、本地也无预构建时，改用
  **SIS Academic Requirements**（学生本人学位审计，`cache/sis/sis_academic_req.json`）
  作权威来源，由 `scripts/rank/ar_to_unmet.py` 生成未修清单（复杂语义交给 AI 精读补全）。

数据获取规范（URL 模板/cookie 约定/产物）见 `skills/web-crawl-guide/SKILL.md`；
各步骤的固定执行与总结结构见对应 step skills（`skills/stepN-*/SKILL.md`）。

## 脚本改进记录（2026-08 运行实测后）

本次真实运行暴露并修复的问题，及对应的脚本化改进：

| 问题 | 修复/改进 | 脚本 |
|---|---|---|
| 顶层脚本 ROOT 多跳一层，读错 credentials | `parents[2]` → `parents[1]` | `scripts/cookies_setup.py` |
| `pre_enrolled.json` 无 schema 映射，R2 跳过 | FILE_SCHEMA 补 `pre_enrolled.json` | `scripts/harness/schema_validate.py` |
| 4xxx 级必修课被低年级 CC 池挤出 Top-N 候选池 | `--keep-major`：必修/选修强制保送入池（不破坏分数序） | `scripts/rank/local.py` |
| 旧学年 curriculum 缺失无回退路径 | `--areas` 过滤 + 从 SIS AR 生成未修基架 | `scripts/rank/ar_to_unmet.py`（新增） |
| 系/教授豁免 pre-req 需手工放回 removed | `--override CODE`：硬删课程按用户豁免放回 kept，标 `user_overridden` | `scripts/rank/filter.py` |
| planner 选课池丢必修；TBA 课程（如 Capstone Research）无法入排计学分 | 池强制含全部必修；TBA 课程计入学分并占位；`--exclude` 排除备选（如未选 Capstone） | `scripts/rank/planner.py` |
| review_summary 需 80 门逐条手写 | 自动基架（评分→档位+今年导师名单），AI 精读仅覆盖关键字段 | `scripts/rank/review_summary_build.py`（新增） |
| 产物查看/统计靠临时内联命令 | 机械性分析固化为统一统计（未修/候选/过滤/评论/口碑/排名/方案） | `scripts/report/stats.py`（新增） |
| 冗余 flag / 死代码（2026-08 清理） | 删冗余 flag（`--schedule`/`--cc`/`--jsessionid`/`--ps-token`/`--raw-dir`/`--output-dir`）、死函数（`extract_emplid`/`load_cookies_from_raw`/`_fmt_slots`/`CATEGORIES`）、去重 `build_pool`/`diversity_swap` 重复逻辑 | `scripts/sis/parser.py`、`scripts/rank/{planner,filter,final,ar_to_unmet,review_summary_build}.py`、`scripts/wcq/conflict.py` |

**学分负荷例外**：`templates/schemas/timetable_plan.schema.json` 限制 `total_credits ≤ 18`（对应政策 12-18）。
用户指定 19 学分 overload（如 6 学分 Capstone Research + 2 门 CC）时，机器产物仍保持 ≤18 的合规方案，
19 学分与 Dean 批准要求以 `output/final_report.md` 文字说明（不破坏产物 schema）。

## 运行方式（常用命令）

```bash
# cookie 获取与预检（phase1 先跑 --check；交互模式引导粘贴并自动验证）
python3 scripts/cookies_setup.py --check
python3 scripts/cookies_setup.py                # 交互：粘贴 → 写入 → 自动验证
python3 scripts/cookies_setup.py --print-bookmarklet   # 登录页一键复制 cookie 的书签

# SIS（运行时，需 credentials/cookies.txt 中的 PS_TOKEN）
python3 scripts/sis/parser.py --fetch --cookie-file credentials/cookies.txt
python3 scripts/sis/parser.py --selftest            # 解析器自测（含 pre-enroll）

# WCQ Class Schedule（公开，无需 cookie；2610 = 2026-27 Fall）
python3 scripts/wcq/crawler.py --session 2610
python3 scripts/wcq/crawler.py --admission-year 2023-24 --session 2610   # Common Core 课程池
python3 scripts/wcq/conflict.py --session 2610 --courses "PHYS 3152:L1" "PHYS 4050:L1"

# USTspace 评论（运行时，需 credentials/cookies.txt 中的 ustspace_session）
python3 scripts/ustspace/crawler.py --codes "PHYS 4050" --cookie-file credentials/cookies.txt
python3 scripts/ustspace/crawler.py --codes-file data/filter_report.json

# 候选课程打分链（Step 1-6；含本次新增/改进的参数）
python3 scripts/rank/ar_to_unmet.py --session 2610 --areas 23 24 25 28   # 新增：AR→未修（curriculum 缺失回退）
python3 scripts/rank/local.py --unmet data/unmet_courses.json --top 50 --keep-major   # 改进：必修保送
python3 scripts/rank/filter.py --candidates data/candidate_rank.json --session 2610 \
    --override "PHYS 4191" --override "PHYS 4291"                          # 改进：用户豁免放回
python3 scripts/rank/filter.py --lookup "PHYS 3152" --session 2610        # 本地查课（AI 核对今年是否开设/导师/时间/配额，不联网）
python3 scripts/rank/review_summary_build.py --session 2610                # 新增：review_summary 基架
python3 scripts/rank/final.py --filter data/filter_report.json --reviews data/ustspace_reviews.json
python3 scripts/rank/planner.py --scores data/course_scores.json --session 2610 \
    --must-take "PHYS 3152" "PHYS 4050" "PHYS 4080" "PHYS 4291" \
    --exclude "PHYS 4191" "PHYS 4811"                                      # 改进：必修/备选/TBA 处理
python3 scripts/rank/filter.py --selftest                       # pre-req 解析器自测

# 运行时产物统计汇总（机械性分析：未修/候选/过滤/评论/口碑/排名/方案）
python3 scripts/report/stats.py
python3 scripts/report/stats.py --only filter --scores-top 15   # 只看某节 / 指定排名条数

# prog-crs 预构建（按入学年份；harness 按 profile.admission_year 决定年份）
python3 scripts/prog_crs/build.py --year 2026-27
python3 scripts/prog_crs/parser.py --selftest          # 解析器自测

# AR↔curriculum 映射（自动定位 database/curriculum/{year}/{PROG}.json）
python3 scripts/mapper/run.py --program PHYS --intake-year 2023-24 \
    --ar cache/sis/sis_academic_req.json

# R1-R6 testcase
python3 scripts/harness/test_runner.py --case scripts/tests/demo
python3 scripts/harness/test_runner.py --case scripts/tests/rank
```

各脚本的完整参数与约定见 `scripts/README.md`。

## 约定

- cookie 文件：`credentials/cookies.txt`。**不要手建**，用 `scripts/cookies_setup.py`
  交互引导（粘贴 → 自动写文件 → 自动验证有效性）；`--print-bookmarklet` 输出
  登录页一键复制 cookie 的书签代码（httpOnly 如 PS_TOKEN 可能复制不到，用 F12
  手动复制并只粘贴失效键）。SIS 用 `PS_TOKEN` 行，USTspace 用 `ustspace_session` 行
- 预检：`cookies_setup.py --check` 只输出状态（OK/EXPIRED/MISSING/UNREACHABLE），
  不显示 cookie 值（AI 禁读明文）；SIS 判定用 Student Center 页正特征（icsid 等），
  无 cookie 时 SIS 会返回 200 壳页面，负特征判定不可靠
- WCQ 输出：`data/courses_{session}.json`、`data/cc_courses_{session}.json`（Common Core 课程池）；SIS 输出：`cache/sis/`；prog-crs 原始输出：`cache/prog-crs/raw/{year}/`
- USTspace 输出：`cache/ustspace/raw/{code}.json`（原始 API JSON）+ `data/ustspace_reviews.json`（汇总）+ `data/review_summary.json`（AI 精读总结，可由 `review_summary_build.py` 生成基架后 AI 覆盖）
- 运行时产物：`data/unmet_courses.json`、`data/candidate_rank.json`、`data/filter_report.json`、`data/course_scores.json`
- 预构建数据：`database/curriculum/{year}/`、`database/course_catalog/{year}/`、`database/mappings/`、`database/build.json`
- **年份版本化**：curriculum/课程目录都按入学年份分目录；schedule 按 session（2610）分文件；构建标记 `database/build.json`
- 只读集（R1）：skills/ database/ templates/ user/ scripts/ opencode.json
- 新脚本按域放入对应子目录；testcase 放 `tests/<case>/`
