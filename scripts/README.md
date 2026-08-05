# scripts/

Python 脚本目录，按职责分域组织：

```
scripts/
├── cookies_setup.py            # cookie 获取与预检（--check / 交互引导 / --print-bookmarklet）
├── sis/                        # SIS 抓取解析（学生现状，需 PS_TOKEN cookie）
│   ├── parser.py               #   统一工具：--fetch 抓取（含 Pre-Enroll 预选课）+ 解析 → JSON
│   └── WEBSITE_STRUCTURE.md    #   SIS 系统结构与抓取技术参考
├── prog_crs/                  # prog-crs 公开目录预构建（按入学年份版本化，async 并发）
│   ├── crawler.py             #   抓取 curriculum PDF → cache/prog-crs/raw/{year}/（async）
│   ├── parser.py              #   PDF 文本 → database/curriculum/{year}/{code}.json（候选索引）
│   ├── course_catalog.py      #   ugcourse 课程详情 → database/course_catalog/{year}/{subj}.json（async）
│   ├── build.py               #   一键编排：crawler → parser → course_catalog（--year）
│   └── fixtures/              #   parser selftest 片段
├── wcq/                       # WCQ Class Schedule 抓取 + 时间冲突检测
│   ├── crawler.py             #   公开页抓取 → data/courses_{session}.json（async，含导师/Quota/pre-req）
│   └── conflict.py            #   课程列表 + 学期 → 时间冲突检测（多时段解析）
│   └── README.md
├── ustspace/                  # USTspace 课程评论（需 ustspace_session cookie）
│   └── crawler.py             #   评论抓取 → cache/ustspace/raw/ + data/ustspace_reviews.json
├── report/                    # 运行时产物统计汇总（机械性分析固化）
│   └── stats.py               #   全产物统计：未修/候选/过滤/评论/口碑/排名/方案
├── rank/                      # 候选课程打分链（Step 2/3/5/6）
│   ├── local.py               #   Step 2 本地规则打分（类别/等级/紧迫度）→ Top N 候选（--keep-major 保送必修）
│   ├── ar_to_unmet.py         #   Step 1 回退：SIS AR → 未修基架（curriculum 缺失时；--areas 过滤 CC）
│   ├── filter.py              #   Step 3 过滤（今年未开设 / pre-req 未满足）→ filter_report（--override 用户豁免）
│   ├── final.py               #   Step 5 合成排名（规则分+USTspace 口碑 → 吸引力+置信度）
│   ├── review_summary_build.py#   Step 4 基架：ustspace_reviews → review_summary（AI 精读覆盖关键字段）
│   └── planner.py             #   Step 6 课程表编排（必修强制入池/TBA 计学分/--exclude 备选）
├── mapper/                    # AR↔curriculum 映射
│   ├── run.py                 #   主入口：AR 未满足条目 → 候选课程 + 置信度
│   ├── generic.py             #   策略链（override / 代码交集 / 文本 / 结构 / 回退）
│   └── registry.py            #   每系覆盖规则（database/mappings/{PROG}.json）
├── harness/                   # R1-R6 testcase 基础设施
│   ├── hash_check.py          #   R1 只读完整性检查（snapshot / verify）
│   ├── schema_validate.py     #   R2 产物 schema 校验（basename + 父目录链回退）
│   ├── checkpoint.py          #   R4 阶段顺序检查（begin / done / status / reset）
│   └── test_runner.py         #   R1-R6 testcase 运行器（隔离副本 + 全规则断言）
└── tests/                     # testcase 目录（R1-R6 用）
    ├── demo/                  # demo 用例：模拟 phase1→phase4.5 全流程
    └── rank/                  # rank 用例：Step1→Step5 数据链 + schema 校验
```

## 三个数据源的分工

| 数据源 | 脚本 | 回答的问题 | 认证 |
|---|---|---|---|
| SIS | `sis/` | 学生**现在**修了什么、毕业要求进度、**学校预选课（Pre-Enroll）** | 需 PS_TOKEN cookie（AI 禁碰） |
| WCQ Class Schedule | `wcq/crawler.py` | 今年**开什么课**、导师、Quota、pre-reg | 公开，无需 cookie |
| prog-crs curriculum | `prog_crs/` | 该专业**要求什么**（候选课程 + 规则原文） | 公开，离线预构建 |
| prog-crs ugcourse | `prog_crs/course_catalog.py` | 某门课**能不能选**（pre-req / exclusion） | 公开，离线预构建 |
| USTspace | `ustspace/crawler.py` | 某门课**口碑如何**（评论/热度/导师） | 需 ustspace_session cookie |

## 运行方式

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
python3 scripts/wcq/crawler.py --admission-year 2026-27 --session 2610   # Common Core 课程池
python3 scripts/wcq/conflict.py --session 2610 --courses "COMP 2011:L1" "ACCT 2010:L01"

# USTspace 评论（运行时，需 credentials/cookies.txt 中的 ustspace_session）
python3 scripts/ustspace/crawler.py --codes "COMP 2011" --cookie-file credentials/cookies.txt
python3 scripts/ustspace/crawler.py --codes-file data/candidate_rank.json

# 候选课程打分链（Step 1/2/3/5/6；含 2026-08 实测后新增/改进参数）
python3 scripts/rank/ar_to_unmet.py --session 2610 --areas 23 24 25 28   # AR→未修（curriculum 缺失回退）python3 scripts/rank/local.py --unmet data/unmet_courses.json --top 50 --keep-major
python3 scripts/rank/filter.py --candidates data/candidate_rank.json --session 2610 \
    --override "PHYS 4191" --override "PHYS 4291"     # 系豁免 pre-req → 放回 kept 标 user_overridden
python3 scripts/rank/filter.py --lookup "PHYS 3152" --session 2610  # 本地查课（不联网，O(1) 索引）
python3 scripts/rank/review_summary_build.py --session 2610              # review_summary 基架
python3 scripts/rank/final.py --filter data/filter_report.json --reviews data/ustspace_reviews.json
python3 scripts/rank/planner.py --scores data/course_scores.json --session 2610 \
    --must-take "PHYS 3152" "PHYS 4050" "PHYS 4080" "PHYS 4291" \
    --exclude "PHYS 4191" "PHYS 4811"               # 必修/TBA/备选处理
python3 scripts/rank/filter.py --selftest                       # pre-req 解析器自测

# prog-crs 预构建（按入学年份；harness 按 profile.admission_year 决定年份）
python3 scripts/prog_crs/build.py --year 2026-27
python3 scripts/prog_crs/parser.py --selftest          # 解析器自测

# AR↔curriculum 映射（自动定位 database/curriculum/{year}/{PROG}.json）
python3 scripts/mapper/run.py --program PHYS --intake-year 2026-27 \
    --ar cache/sis/sis_academic_req.json

# 运行时产物统计汇总（机械性分析；--only 单看一项，--scores-top 指定排名条数）
python3 scripts/report/stats.py
python3 scripts/report/stats.py --only filter --scores-top 15

# R1-R6 testcase
python3 scripts/harness/test_runner.py --case scripts/tests/demo
python3 scripts/harness/test_runner.py --case scripts/tests/rank
```

## 约定

- cookie 文件：`credentials/cookies.txt`。**不要手建**，用 `scripts/cookies_setup.py`
  交互引导（粘贴 → 自动写文件 → 自动验证有效性）；`--print-bookmarklet` 输出
  登录页一键复制 cookie 的书签代码（httpOnly 如 PS_TOKEN 可能复制不到，用 F12
  手动复制并只粘贴失效键）。SIS 用 `PS_TOKEN` 行，USTspace 用 `ustspace_session` 行
- 预检：`cookies_setup.py --check` 只输出状态（OK/EXPIRED/MISSING/UNREACHABLE），
  不显示 cookie 值（AI 禁读明文）；SIS 判定用 Student Center 页正特征（icsid 等），
  无 cookie 时 SIS 会返回 200 壳页面，负特征判定不可靠
- WCQ 输出：`data/courses_{session}.json`、`data/cc_courses_{session}.json`（Common Core 课程池）；SIS 输出：`cache/sis/`；prog-crs 原始输出：`cache/prog-crs/raw/{year}/`
- USTspace 输出：`cache/ustspace/raw/{code}.json`（原始 API JSON）+ `data/ustspace_reviews.json`（汇总）+ `data/review_summary.json`（AI 精读总结，Step 4 skill 产出）
- 运行时产物：`data/mapping_result.json`、`data/unmet_courses.json`、`data/candidate_rank.json`、`data/filter_report.json`、`data/course_scores.json`
- 预构建数据：`database/curriculum/{year}/`、`database/course_catalog/{year}/`、`database/mappings/`、`database/build.json`
- **年份版本化**：curriculum/课程目录都按入学年份分目录；schedule 按 session（2610）分文件；构建标记 `database/build.json`
- 只读集（R1）：skills/ database/ templates/ user/ scripts/ opencode.json
- 新脚本按域放入对应子目录；testcase 放 `tests/<case>/`
