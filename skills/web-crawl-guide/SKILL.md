---
name: web-crawl-guide
description: 联网抓取规范（固定流程）。AI 需要联网获取 Class Schedule / SIS / USTspace / prog-crs 数据时，必须严格按本 skill 的 URL 模板、参数、cookie 要求与缓存约定执行，禁止临场发挥。Use when fetching course schedule, SIS student data, USTspace reviews, or prog-crs data.
---

# Web Crawl Guide — 联网抓取规范（固定流程）

> 原则：**AI 永不接触 cookie 明文**。所有带认证的抓取由 `scripts/` 统一执行
> （经 `--cookie-file` 读取 `credentials/cookies.txt` 或临时文件）；AI 只消费
> `cache/` 与 `data/` 中的解析产物。先查缓存，再联网。解析产物必须过 schema。
>
> **执行入口**：运行期抓取统一经 `scripts/ustplan.py job start/status/wait`
> （wcq_full / sis_fetch / ustspace_pre / buckets_pre，超时与产物见
> `docs/RUNBOOK.md` §1）；本文件仅作为 URL 模板/参数/cookie/解析规范参考，
> 禁止在 skill 流程中直接拼命令抓取。

## 1. WCQ Class Schedule（公开，无需 cookie）

**用途**：Step 3 过滤（今年是否开设 / pre-reg / 仅限专业）+ Step 4 导师 + Step 6 冲突检测。

| 项 | 值 |
|---|---|
| URL 模板 | `https://w5.ab.ust.hk/wcq/cgi-bin/{session}/`（session 如 `2610` = 2026-27 Fall；`26`=学年 `10`=Fall） |
| **session 自动检测** | `--session latest`：抓 `https://w5.ab.ust.hk/wcq/cgi-bin/` 索引页，正则 `cgi-bin/(\d{4})/` 取**数字最大** = 最近学期（harness t0 默认使用） |
| 索引页 | 同上，含全部 subject 链接 `href="/wcq/cgi-bin/{session}/subject/{SUBJ}"` |
| subject 页 | `https://w5.ab.ust.hk/wcq/cgi-bin/{session}/subject/{SUBJ}`（如 `/subject/COMP`） |
| 方法 | GET，无 cookie，UA: `Mozilla/5.0 (course-arranger build script)` |
| 关键词/锚点 | 课程块 `<div class="course">`；课号 `<a name="ACCT3010">`；标题行 `<div class='subject'>`；属性 `<tr><th>PRE-REQUISITE/EXCLUSION/...`；section 行 `mainRow`（新 section）+ `otherRow`（同 section 附加时段，**必须合并**）；跳过 `mobileInstructorRow` / `mobileViewDetail`；导师 `<a href=".../instructor/...">NAME</a>` |
| 缓存 | `cache/wcq/raw/{session}/{SUBJ}.html` |
| 产物 | `data/courses_{session}.json`（course 级：code/number/title/units/attributes；section 级：section/datetime/room/instructors/quota/enrol/avail/wait；datetime 多时段逗号合并） |
| 本地匹配 | 后续匹配一律用产物 JSON 建 `规范化课号 → course` 索引（O(1)），**禁止**对 cache/wcq/raw/ 原始 HTML 正则（爬虫已预处理归一，重复正则反而慢）；课号规范化=大写+去空格/点+**保留字母后缀**（1416C/4981H）；CC 区域页与 subject 页重复收录 → 去重取 subject 页版本。临时查课用 `filter.py --lookup "PHYS 3152"` |
| 脚本 | `scripts/wcq/crawler.py --session <SESSION>`（`--force` 重抓、`--list-only` 列 subject） |

### 1b. Common Core 课程匹配（同一页面下拉）

索引页 "Select Common Core Course" 下拉按**入学年份组**分类：
`4Y`（2021-22 前，36 学分制）/ `CC22`（2022-2024）/ `CC25`（2025）/ `CC26`（2026 起）——
与 `database/common-core/` 四版本一一对应。

| 项 | 值 |
|---|---|
| 下拉结构 | 组链接路径单段 `/wcq/cgi-bin/{session}/common_core/{GROUP}`；区域链接两段 `.../common_core/{GROUP}/{code}`（code 47-60） |
| 区域页 | `GET .../common_core/{GROUP}/{code}` → 该区域**今年开设**的全部 CC 课程（跨 subject，复用 div.course 解析） |
| 404 语义 | 该区域今年无课（如 UxOP-UPOP/UCOP）→ 记录 EMPTY，不重试 |
| 入学年份映射 | ≤2021→4Y；2022-2024→CC22；2025→CC25；≥2026→CC26（`admission_to_group`） |
| 产物 | `data/cc_courses_{session}.json`（每区域：area_code/**area（含 requirement 标签，如 Common Core (A)）**/course_count/courses 全字段同 schedule） |
| 脚本 | `python3 scripts/wcq/crawler.py --admission-year <YEAR> --session <SESSION>`（自动选组）或 `--cc-group CC26` |

**使用**：Step 1 从 profile 取 admission_year → 抓对应组 → 得"今年可读 CC 课程池"。
**每个区域的 `area` 标签即该栏位满足的 requirement 项**（HMW/E-Comm/C-Comm/CTDL =
基础层；A/H/S/T/SA/SUS = Broadening 区域；UxOP-* = Experiencing）——
buckets.py 据此归档：基础层 → cc_required，其余 → cc_elective，每区域一个 bucket；
与 `database/common-core/{版本}` 的分布要求（如 home area 外 4 区 12 学分）对照复核配额。

### 1c. 历史 CC 区域表（课程码 → 区域归属，CC 满足性判定的第二数据源）

**背景（2026-08 实测）**：SIS AR 页面对部分 CC 区域（如 S/SA）不渲染明细（折叠
空壳），"已修 X 学分"无法从 AR 归因到具体区域；而当年开课学期所在的 wcq CC
区域页（公开、历史 session 仍在线）明确列出课程归属。把多个历史学期的区域页
并集为静态表，供 buckets.py 判定"已修课程属于哪个区域"（**CC 满足性全脚本化，
无 AI 判断**——例：SOSC 1969 → SA 区、PHYS 1007 → S 区）。

| 项 | 值 |
|---|---|
| 脚本 | `scripts/wcq/cc_areas.py --admission-year 2023-24`（默认：入学年起至最新全部 Fall/Spring/Summer；`--sessions` 指定、`--force` 重抓） |
| 缓存 | `cache/wcq/raw/{session}/common_core/{GROUP}-{area}.html`（与 1b 同目录复用） |
| 产物 | `database/common-core/areas_{GROUP}.json`（areas[] + code_area 课程码→区域码映射；构建期写入 database/，运行时只读） |
| 消费 | `buckets.py` 自动检测 `database/common-core/areas_{GROUP}.json`（`--cc-areas` 可覆盖） |
| 防呆 | 旧学期（≤2022-23 session）索引/区域页全部返回同一份通用页 → 脚本比对"页面=索引页"即判无效跳过；**4Y 组（36 学分制）无真实区域页**（本学期为空、历史不提供）→ 不构建 areas_4Y.json，4Y 学生 CC 满足性走 SIS AR 判定 |

## 2. SIS 学生数据（需 PS_TOKEN cookie）

**用途**：Step 1 已修课程（Course History）+ 毕业要求进度（Academic Requirements）。

| 项 | 值 |
|---|---|
| 根 URL | `https://sisprod.psft.ust.hk/psc/SISPROD/EMPLOYEE/HRMS/c` |
| Student Center | `GET /SA_LEARNER_SERVICES.SSS_STUDENT_CENTER.GBL`（提取隐藏字段 `ICSID`、`ICStateNum`——**每次动态提取，禁止硬编码**） |
| 下拉导航 | `POST` 同 URL，参数 `ICAction=DERIVED_SSS_SCL_SSS_GO_1`、`ICSID`、`ICStateNum`（来自页面）、`DERIVED_SSS_SCL_SSS_MORE_ACADEMICS={dropdown}` |
| dropdown 值 | course_history=2050、academic_requirements=3010、class_schedule=1002、grades=1030、transcript=2035、transfer_credit=2025 |
| cookie | 仅需 `PS_TOKEN`（CAS 签发令牌）；**必须用 requests.Session 保持**（POST 依赖 GET 下发的 PS_TOKENEXPIRE） |
| 关键词 | 课程行 `CRSE_NAME$N` / `CRSE_GRADE$N`；AR 分组 `<td class='PAGROUPDIVIDER'>`；状态 `Not Satisfied` / `Satisfied`；Transcript：CGA / Overall GPA 字段、每学期课程与成绩 |
| **AR 学分/条目明细**（2026-08 新增） | 组级 `GROUPBOX2$N` div（含组名）+ `SAA_DESCRLONG_03$N`（状态）+ `04$N`（`Units/Courses: X required, Y taken, Z needed`）；条目级 `GROUPBOX3$M` 折叠锚点（title 含区域名）+ `05$M` + `06$M`。**注意**：部分区域（HMW/E-Comm/C-Comm/S/SA 等）为折叠空壳无条目数据——组级 03/04 才是可靠数据；区域满足性判定见 1c（历史 CC 区域表） |
| 缓存 | `cache/sis/raw_*.html` → `cache/sis/sis_{student_info,course_history,academic_req,transcript,pre_enroll}.json` |
| 脚本 | `scripts/sis/parser.py --fetch` |

### 2c. Pre-Enroll（学校预选课，HKUST 定制 Enrollment Summary）

**用途**：Phase 2 获取学校为学生预选的课程（Confirmed/Pending），Step 1 排除推荐、
Step 5 评分按 pre_enroll_boost 加权（默认 +40%）、Step 6 占用其 section 时段 + drop 建议。

| 项 | 值 |
|---|---|
| URL | `https://sisprod.psft.ust.hk/psc/SISPROD/EMPLOYEE/HRMS/c/SA_LEARNER_SERVICES.ZR_SSENRL_SUM_CMP.GBL?Page=ZR_SSENRL_SUM_PG&Action=A&ACAD_CAREER=UGRD&EMPLID=&ENRL_REQUEST_ID=&INSTITUTION=HKUST&STRM={session}` |
| 结构 | `Confirmed Enrollment` 网格前缀 `ZR_ENRL_SUMC_VW`、`Pending Enrollment` 前缀 `ZR_ENRL_SUMP_VW`；字段 `ZR_CRSE_CODE/COURSE_TITLE_LONG/UNT_TAKEN/SECTION_NAME`（`$N` 行索引）；`Total Unit Load: x (Confirmed: y Pending Add: z Pending Drop: w)`；页尾 `Consolidate Timetable: View in Timetable Planner` |
| **空状态（2026-08 实测）** | 未预选/非预选季时两网格均**无行**（页面仅 "Enrollment Summary" 标题 + `Total Unit Load: 0 (Confirmed: 0 ...)`）；浏览器可能展示 "You are not enrolled in classes" 提示，解析产物为空数组，属正常，不算失败 |
| **STRM 必填（2026-08 实测）** | URL 的 STRM 必须为有效 term code（如 2610），否则页面返回 JS 空壳、**无网格无数据**（`ZR_ENRL_SUMC_VW` 出现 0 次）；`sis_fetch` job 已知真实 session 时自动注入 `--session` |
| 注意 | **term 由会话决定，URL STRM 仅触发渲染不切学期**（2026-08 实测：STRM=2610 时页面显示 SIS 当前默认学期，如 2025-26 Summer）；选课季通常即目标学期；`EMPLID` 可选（会话可识别用户） |
| 产物 | `cache/sis/sis_pre_enroll.json` + **`data/pre_enrolled.json`（同步写入，同构同 schema，step1/5/6 直接消费）**（term/confirmed[]/pending[]/total_unit_load） |

> 会话建立：`--fetch` 先 GET Student Center 两次（首次拿 JSESSIONID，第二次带 PS_TOKEN 生效）再抓各页。

### 2b. Transcript（入学年份 / CGA 权威来源）

**用途**：Phase 2 判断新生/老生与入学年份（最准确方式，优先于 course history 推断）。

| 项 | 值 |
|---|---|
| 导航 | 同 §2：dropdown `transcript=2035` → 目标页 |
| 判断规则 | **无 CGA 记录 = 大一新生 → 入学年份=当年**；有 CGA → 取最早上课学期推断入学年份 |
| 关键字段 | CGA（Overall GPA）、最早 term、各学期课程记录 |
| 产物 | `cache/sis/sis_transcript.json`（CGA / earliest_term / 状态） |
| 降级 | 抓取失败 → course history 最早学期推断 → USTSPACE settings → 问用户（phase2-profile skill） |

> 注意：Transcript 页面可能为 JS/分学期加载，若单页解析不全，用 grades=1030 逐学期
> 页面补充（缓存 `cache/sis/raw_grades_{term}.html`）。

## 3. USTspace 课程评论（需 ustspace_session cookie）

**用途**：Step 4 评论分析（热度 + 导师口碑）。

| 项 | 值 |
|---|---|
| 课程页 | `GET https://ust.space/review/{CODE}`（CODE = subject+number 无空格，如 `COMP2011`）；仅用于提取 `meta[name=csrf_token]` |
| **数据 API** | `GET https://ust.space/review/{CODE}/get`，Query 参数（**固定**）：`single=false` `composer=false` `preferences[sort]=0` `preferences[filterInstructor]=0` `preferences[filterSemester]=0` `preferences[filterRating]=0` |
| 请求头 | `X-CSRF-Token: {csrf_token}`（每会话获取一次；返回 `{"error":true}` 时刷新重试） |
| cookie | `ustspace_session`（加密会话） |
| 响应 | JSON：`course`（含 rating_content/teaching/grading/workload、review_count、instructors、prerequisites/exclusions）+ `reviews[]`（hash/semester/instructors/author/date/title/comment_content/rating_*/upvote_count/vote_count/comment_count/has_midterm/final/quiz/assignment/essay/project/attendance/reading/presentation） |
| 热度 | `vote_count` 降序取 top5；导师维度按 `instructors[].name` 分组取 top5 |
| **导师统计** | `instructor_stats`：每导师 {review_count, ratings 四维均值}（评分公式 B 组件输入） |
| **导师最近评论** | `instructor_recent`：每导师按时间排序（date 降序）最近 5 条（评分公式 D 组件输入） |
| 缓存 | `cache/ustspace/raw/{CODE}.json`（完整 API JSON） |
| 产物 | `data/ustspace_reviews.json`（紧凑：ratings、heat_top5、instructor_top5、instructor_stats、instructor_recent、review_count） |
| 脚本 | `scripts/ustspace/crawler.py --codes "COMP 2011" --cookie-file credentials/cookies.txt`（`--codes-file data/filter_report.json` 批量） |
| 注意 | 2000+ 级课程评论需 contributor 等级；数据仅供教学分析，抓取限速（并发 ≤ 4）；**`{"error":true}` = 该课无评论数据（正常，非失败）**，记入 failed[] 继续；**AI 禁止直接 webfetch ust.space 页面**（需登录返回空壳）——统一走 crawler.py |

## 3.5 本地查课（勿重复构建）

- 课程是否开设 / pre-req / EXCLUSION / 时间槽：`python3 scripts/rank/filter.py --lookup "COMP 4471" --session <S>`
  （本地读 courses_{session}.json，O(1)，不联网）
- 课程代码存疑时**先 `--lookup` 确认课号是否存在**，再决定是否抓取/排课

## 4. prog-crs 预构建（公开，无需 cookie）

**用途**：专业 curriculum 候选索引（按入学年份）——离线预构建。**课程详情
（pre-req 等）不预构建**：它是动态数据，每个学生/目标学期不同，以运行时
Class Schedule（wcq）页内联 PRE-REQUISITE 为准；需要单课详情时按需
`course_catalog.py --subject X --year Y` 临时查（产物落 cache/，不入库）。

| 项 | 值 |
|---|---|
| 根 URL | `https://prog-crs.hkust.edu.hk/ugprog/{year}/`（year=入学年份；**索引取 `/ugprog/{year}/`，勿用主 `/ugprog`**——主索引只列当前年份） |
| 年份可用性 | 2023-24 起公开且本地已预构建；2022-23 及更早为 archive 已下线（401）→ 无法重建，`ar_to_unmet.py` 可从 SIS AR 生成基架（**人工工具，不接入 step 合约链**） |
| PDF 提取 | 专业页内 "Major Requirements" 链接 → 下载 PDF → `pdftotext -layout` |
| 课程详情（按需） | `https://prog-crs.hkust.edu.hk/ugcourse/{year}/{SUBJ}/` |
| 缓存 | `cache/prog-crs/raw/{year}/` |
| 产物 | `database/curriculum/{year}/{CODE}.json` |
| 脚本 | `scripts/prog_crs/build.py --year {year}`（仅 curriculum；2022-23 及更早报错提示走 AR 回退） |

## 5. 通用规则

1. **顺序**：先查 `cache/` 是否已有 → 有则跳过；无则按上表 URL 抓取
2. **失败重试**：单 URL 最多 3 次（30-60s 超时）；连续失败记录到产物 `failed` 字段，不静默
3. **产物落盘**：解析结果写入 `data/` 或 `database/`，原始 HTML/JSON 只进 `cache/`
4. **凭据**：AI 上下文不得出现 cookie 值；cookie 的获取/写入/有效期预检统一走
   `scripts/cookies_setup.py`：
   - `--check` 只输出状态（OK/EXPIRED/MISSING/UNREACHABLE）+ TTL 提醒；
   - `--listen` 一键获取（本机回环 + 连接码，浏览器扩展 `extensions/ust-cookie`
     按钮推送，可读 httpOnly 的 PS_TOKEN）；bookmarklet / F12 粘贴为降级通道；
   - TTL（config → credentials.ttl_hours，默认 12h）超期时引导 `--listen` 刷新；
   测试 cookie 放项目外临时目录，用后删除
5. **版本化**：schedule 按 session（2610）、curriculum 按入学年份（2026-27）
6. **运行时产物链（固定）**：`data/unmet_courses.json`（bucket 化）→
   `data/filter_report.json`（pre-req 只标记不移除）→ `data/ustspace_reviews.json`
   → `data/review_summary.json`（含 D 组件）→ `data/course_scores.json`
   （每栏位 TOP3 + ranked_out 备选池）→ `output/timetable_plan.json`
   （含 waiver_required）；每一步产物必须过 schema（R2）才能进下一步
