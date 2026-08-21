# scripts/

Python 脚本目录，按职责分域组织。

> **产品化运行一律走 `scripts/ustplan.py` 统一入口**（init/doctor/start/status/resume/
> step/phase/job/plan/report/grid/decisions，命令表见 `docs/DEVELOPER.md`）——
> AI 与用户流程不直接拼底层命令。本文档是**开发/调试视角**的脚本索引。

```
scripts/
├── ustplan.py                  # 统一入口（产品化运行唯一入口）
├── cookies_setup.py            # cookie 获取与预检（--check 含 TTL / --listen 一键接收 / 交互引导 / --print-bookmarklet）
├── credentials.py              # 凭据统一模块（load/save/filter/meta/TTL；二期 DPAPI 加密插槽）
├── sis/                        # SIS 抓取解析（学生现状，需 PS_TOKEN cookie）
│   ├── parser.py               #   统一工具：--fetch 抓取（含 Pre-Enroll 预选课）+ 解析 → JSON
│   ├── build_profile.py        #   画像基架：course_history → profile/passed_courses（phase2 机械转换）
│   └── WEBSITE_STRUCTURE.md    #   SIS 系统结构与抓取技术参考
├── prog_crs/                   # prog-crs 公开目录预构建（按入学年份版本化，async 并发）
│   ├── crawler.py              #   抓取 curriculum PDF → cache/prog-crs/raw/{year}/（async）
│   ├── parser.py               #   PDF 文本 → database/curriculum/{year}/{code}.json（候选索引）
│   ├── course_catalog.py       #   ugcourse 课程详情 → database/course_catalog/{year}/{subj}.json（按需单查）
│   ├── build.py                #   一键编排：crawler → parser → course_catalog（--year）
│   └── fixtures/               #   parser selftest 片段
├── wcq/                        # WCQ Class Schedule 抓取 + 时间冲突检测（公开，无需 cookie）
│   ├── crawler.py              #   全量抓取 → data/courses_{session}.json（导师/Quota/pre-req；latest_session 自动检测；--subjects-file 按名单抓取）
│   ├── history_fetch.py        #   历史学期课表抓取（wcq_history job 执行体：前两学期 × 候选 subject）
│   ├── cc_areas.py             #   历史 CC 区域表抓取（按入学年份组 4Y/CC22/CC25/CC26）
│   ├── conflict.py             #   课程 + 学期 → 时间冲突检测（多时段解析）
│   └── README.md               #   抓取/解析/冲突判定细节
├── ustspace/                   # USTspace 课程评论（需 ustspace_session cookie）
│   └── crawler.py              #   评论抓取 → cache/ustspace/raw/ + data/ustspace_reviews.json
├── report/                     # 报告渲染与统计
│   ├── render.py               #   final_report.md 模板渲染（机械段落自动，口碑/建议 AI 填）
│   ├── render_grid.py          #   课程表周历（终端 ASCII / 单文件 HTML）
│   └── stats.py                #   全产物统计：未修/候选/过滤/评论/口碑/排名/方案
├── rank/                       # 候选课程打分链（产品化 step1/3/4/5/6）
│   ├── buckets.py              #   step1 未修计算（bucket 化；副修 MINOR-* 合并 + 描述性级别池；track 过滤 + 已修/预选扣除 + CC 三层判定；未修学分按 bucket 配额聚合）
│   ├── ar_to_unmet.py          #   回退：SIS AR → 未修基架（curriculum 缺失时；--areas 过滤 CC）
│   ├── note_eval.py            #   Note 语义求值（AND/OR/方括号/any N of，step1 消费）
│   ├── filter.py               #   step3 过滤（今年未开设 / pre-req 标记 / EXCLUSION）→ filter_report
│   ├── review_summary_build.py #   step4 基架：ustspace_reviews → review_summary（AI 精读覆盖关键字段）
│   ├── review_scope.py         #   step4 精读范围：必修全读 + 其余按评论数 TOP N → scope + digest
│   ├── bucket_score.py         #   step5 评分合成（A+B+C+D，预选课按 pre_enroll_boost 加权）
│   ├── scoring.py              #   评分公式纯函数（可单测）
│   ├── cc_status.py            #   CC 区域满足性核查（已修/未修 + Broadening 12 学分 4 区域）
│   ├── history_compare.py      #   step5.5 历史学期教授对照：往期教授口碑明显更优 → 降权 + 延后建议（step6 消费）
│   ├── planner.py              #   step6 课程表编排（必修强制 / TBA 计学分 / must-take / waiver / 历史降权 score_effective / defer_advice）
│   ├── year_courses.py         #   全年课程检测（year_long 语义，planner 折算消费）
│   └── local.py / final.py     #   [legacy] 旧打分链——仅 scripts/tests/rank 用例使用，产品化流程不消费
├── enroll/                     # 选课写入（enrollment-commit skill）
│   └── cart.py                 #   方案 → 选课清单（TBA 标注）/ admlu65 可达探测 / 提交引导
├── harness/                    # 编排基础设施（ustplan.py 内部组件）
│   ├── contracts.py            #   step/phase 合约表（输入 schema → 命令 → 产物 schema → 摘要）
│   ├── checkpoint.py           #   阶段强顺序（begin / done / status / reset）
│   ├── jobs.py                 #   后台并行任务（超时击杀 / 孤儿清理）
│   ├── manifest.py             #   产物追踪（run_id / sha256 / schema 版本）
│   ├── decisions.py            #   确认点决策审计（P1-P5）
│   ├── doctor.py               #   预检（依赖/配置/cookie/database/schema）
│   ├── config.py               #   产品参数加载与校验（config/ustplan.json + schema）
│   ├── schema_validate.py      #   R2 产物 schema 校验
│   ├── hash_check.py           #   R1 只读完整性检查
│   └── test_runner.py          #   R1-R6 testcase 运行器
└── tests/                      # testcase 目录（R1-R6 用）
    ├── demo/                   # 产品化全流程用例：模拟 phase1→phase4.5，写 schema 合规产物
    ├── rank/                   # 旧脚本链数据用例（unmet → local → filter → 评论 → final）
    └── unit/                   # 单测（评分公式 / planner / note_eval / pre-req / 合约 / 配置）
```

## 数据源分工

见 `docs/ARCHITECTURE.md` §6（唯一权威，避免双份漂移）。

## 运行方式（开发/调试视角）

```bash
# cookie 获取与预检（产品化由 phase1 引导；调试时手动执行）
python3 scripts/cookies_setup.py --check                # 预检（OK/失效/缺失 + TTL 提醒）
python3 scripts/cookies_setup.py --listen               # 一键获取：本机接收端（扩展按钮推送）
python3 scripts/cookies_setup.py                        # 交互：粘贴 → 写入 → 自动验证
python3 scripts/cookies_setup.py --print-bookmarklet    # 登录页一键复制 cookie 的书签（读不到 httpOnly）

# SIS（需 credentials/cookies.txt 中的 PS_TOKEN）
python3 scripts/sis/parser.py --fetch --cookie-file credentials/cookies.txt
python3 scripts/sis/parser.py --selftest            # 解析器自测（含 pre-enroll）
python3 scripts/sis/build_profile.py --session <S>  # 画像基架（phase2：course_history → profile/passed_courses）

# WCQ Class Schedule（公开；session 如 2610 = 2026-27 Fall）
python3 scripts/wcq/crawler.py --session <SESSION>
python3 scripts/wcq/crawler.py --admission-year <YEAR> --session <SESSION>  # 顺带抓 Common Core 池
python3 scripts/wcq/crawler.py --session 2540 --subjects-file data/history_subjects.json  # 按名单抓
python3 scripts/wcq/history_fetch.py --session 2610 --subjects-file data/history_subjects.json  # 前两学期
python3 scripts/wcq/conflict.py --session 2610 --courses "COMP 2011:L1" "ACCT 2010:L01"

# USTspace 评论（需 ustspace_session cookie；AI 禁止直接 webfetch 该站，统一走本脚本）
python3 scripts/ustspace/crawler.py --codes-file data/filter_report.json

# rank 打分链（产品化经 ustplan step；调试可直接调用）
python3 scripts/rank/buckets.py --profile data/profile.json --session 2610 --track <TRACK> \
    --passed data/passed_courses.json [--pre-enrolled data/pre_enrolled.json]   # step1
python3 scripts/rank/filter.py --session 2610 --passed data/passed_courses.json \
    [--override "PHYS 4191"]                       # step3（--lookup "CODE" 本地查课）
python3 scripts/rank/review_scope.py --filter data/filter_report.json --reviews data/ustspace_reviews.json \
    --session 2610                                 # step4 精读范围（必修全读 + 其余 TOP N）
python3 scripts/rank/review_summary_build.py --session 2610              # step4 基架
python3 scripts/rank/bucket_score.py --session 2610 [--pre-enrolled data/pre_enrolled.json]  # step5
python3 scripts/rank/history_compare.py --session 2610   # step5.5 历史学期教授对照（前两学期课表就绪时）
python3 scripts/rank/cc_status.py --passed data/passed_courses.json \
    --admission-year <AY> --major <MAJOR>          # CC 区域满足性核查（P2/P3 用）
python3 scripts/rank/planner.py --scores data/course_scores.json --session 2610 \
    [--must-take "COMP 3111"] [--exclude "COMP 4021"] [--target 15]      # step6
python3 scripts/rank/year_courses.py --session 2610    # 全年课程检测（year_long 候选）

# prog-crs 预构建（按入学年份；harness 按 profile.admission_year 决定年份）
python3 scripts/prog_crs/build.py --year <YEAR>

# 报告与统计
python3 scripts/report/stats.py [--only filter --scores-top 15]
python3 scripts/report/render.py --plan plan-1      # final_report.md 渲染（产品化经 ustplan report）

# 选课写入（enrollment-commit skill；session 由运行中 ustplan status 决定）
python3 scripts/enroll/cart.py check --session <SESSION>
python3 scripts/enroll/cart.py build --plan output/timetable_plan.json --session <SESSION>

# R1-R6 testcase（demo=产品化全流程；rank=旧脚本链；unit=单测）
python3 scripts/harness/test_runner.py --case scripts/tests/demo
python3 scripts/harness/test_runner.py --case scripts/tests/rank
```

## 约定

- **产品化流程不直接调用底层脚本**：参数（session/track/学分/豁免/硬插）由
  `ustplan` 从 manifest/decisions 注入，详见 `docs/DEVELOPER.md` 命令表
- 输出路径：WCQ → `data/courses_{session}.json`、`data/cc_courses_{session}.json`；
  SIS → `cache/sis/`（预选课同时写 `data/pre_enrolled.json`）；prog-crs 原始 →
  `cache/prog-crs/raw/{year}/`；USTspace → `cache/ustspace/raw/` + `data/ustspace_reviews.json`
- 运行时产物：`data/unmet_courses.json`、`data/filter_report.json`、
  `data/review_summary.json`、`data/course_scores.json`、`data/history_compare.json`、
  `output/timetable_plan.json`、`output/enroll_cart.json`
- 预构建数据：`database/curriculum/{year}/`、`database/course_catalog/{year}/`、
  `database/course_notes/`、`database/build.json`
- **年份版本化**：curriculum/课程目录按入学年份分目录；schedule 按 session（4 位代码）
  分文件；构建标记 `database/build.json`
- 只读集（R1）：skills/ database/ templates/ user/ scripts/ opencode.json
- cookie 凭据约定见 `docs/RUNBOOK.md` §4（AI 禁碰明文，预检只输出状态）
- 新脚本按域放入对应子目录；testcase 放 `tests/<case>/`
