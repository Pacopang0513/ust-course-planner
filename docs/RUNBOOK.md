# 排障手册（RUNBOOK）

异常处理矩阵与后台任务说明。AI 遇到异常时先查本表，再按固定模板回复用户。

## 1. 后台任务清单（job-id 固定，超时在 config/ustplan.json → jobs）

| job-id | 命令（ustplan job start 自动构建） | 启动时机 | 默认超时 | 产物 |
|---|---|---|---|---|
| wcq_full | `wcq/crawler.py --session … [--admission-year …]`（入学年份已知自动注入，顺带抓 CC 池） | t0（start 即启动） | 25 分钟 | data/courses_{s}.json + cc_courses_{s}.json |
| buckets_pre | `rank/buckets.py --profile … --track …` | major+track 给出后 | 5 分钟 | data/unmet_courses.json（基架） |
| sis_fetch | `sis/parser.py --fetch` | cookie 到位后 | 10 分钟 | cache/sis/*.json |
| ustspace_pre | `ustspace/crawler.py --codes-file filter_report.json` | P2 提问前 | 15 分钟 | data/ustspace_reviews.json |

- 同 job-id 已 running/done 时 start 被拒绝；重跑 `ustplan job start <id> --force`
- 超时自动击杀并标记 failed(timeout)；机器休眠致 worker 消失 → crashed，start 自动清理
- `ustplan job status/wait <id>` 完成后自动收录产物到 manifest（wcq_full 顺带解析 session）
- 产物收录判定：status/wait 输出含 "done" 或 "完成" 且 exit 0 即收录（2026-08 修复）

## 1.5 学分与 CC 规则（2026-08 固化）

- **学分软约束**：目标学分默认 15；planner 按目标 / +3 / −3 生成方案，
  >18 或 <12 仅提示（overload 需 Dean 批准 / 低于下限咨询学校），不夹边界不拒绝；
- **必修先排**：phase1 必修全入（不因学分拒绝），0 学分课程靠后；
- **TBA 课程**：有学分 TBA（如 UROP 3200）允许占位排入并计学分；
- **UxOP 不排**：Common Core UxOP 区域（UROP/UTOP/UPOP/UCOP）不生成 bucket、
  不参与排课，该 3 学分由其他 CC 课程替代（用户规则）；
- **一年制课程（year_long，2026-08 固化）**：描述含跨两学期语义的课程
  （"extended over two regular terms" / "one year long" / "lasts for one year" /
  "fall and spring" 等），schedule units 是**全年总学分**，每学期实际注册 =
  units/2（如 PHYS 4291：全年 6 → 每学期 3）。检测：`rank/year_courses.py
  --session X`；确认后写入 `database/course_notes/{SUBJ}.json` 的
  `tags: ["year_long"]`，planner 自动折算（`--credits-override` 手动覆盖优先）。
  用户口头说明的学分口径（如"每学期 3 学分"）应归因为全年课程语义，按描述
  核实后落盘，勿直接改抓取产物；
- **确认点 3 次**：P1 令牌+major/minor/extended_major、P2 画像、P3 未修+过滤+学分；
  P4 并入 P3，P5 弱化为展示（用户要求修改才记录）。

## 2. 异常处理矩阵（固定）

| 情况 | 处理 |
|---|---|
| 选课写入（enrollment-commit）学期未开放 | `cart.py check` 探测 + 产品化告知等待学校通知（26-27 Fall 通常 8 月中下旬）；不重复尝试、不猜测 |
| 选课清单含 TBA 课程 | 不提交，等 Class Schedule 公布时间后重跑 `cart.py build` 补选 |
| 缺少 admlu_session（admlu65 会话） | 引导用户浏览器登录后复制会话 cookie 写入 cookies.txt（AI 不接触明文）；提交始终由用户人工执行 |
| SIS cookie 失效 / 抓取失败 | 固定模板报错（产品化），引导重跑 `cookies_setup.py` 交互粘贴失效键，回退等待；不猜测数据；major+track 路径继续并行 |
| USTspace cookie 失效 | 同上引导；失败课程标记 failed[]（无评论 API 也返回 error 属正常），继续其余 |
| 后台任务 failed(timeout/crashed) | 告知"数据抓取中断，正在重试"，`ustplan job start <id> --force` 重跑；仍失败按上两行；不携带坏数据前进 |
| **后台任务 WinError 193（Windows）** | `.py` 不能直接作为可执行文件启动；jobs.py 已自动加解释器前缀（见 `_run_job`），若再出现检查 cmd[0] 是否为 `.py` 且经 `ustplan job start` 启动（勿绕过 jobs.py 直接 Popen） |
| 本地 curriculum 缺失 | 二次匹配（web-crawl-guide §4）；旧入学年份走 SIS AR 回退（ar_to_unmet.py）；仍失败明确告知不可计算 |
| track 未指定 | 停下询问（track 必填；影响必修/选修 bucket 范围） |
| 用户目标学分 <12 或 >18 | **软约束**：不夹边界、不拒绝，按用户目标 ±3（一门课粒度）编排并提示（<12 建议咨询学校、>18 需 Dean 批准 overload 写入报告） |
| 必修学分超单学期上限 18 | 必修先全排（不因学分拒绝），溢出课程列入 notes 提示 overload |
| 用户指定课程冲突 | 用户取舍（must-take），不擅自决定 |
| 任意 step 产物 schema 校验失败 | 停在本 step 修复产物，不携带坏数据前进（`ustplan step` 自动拦截） |
| step 前置检查失败 | 按提示补决策（`ustplan decisions set …`）或推进阶段（`ustplan phase begin …`） |
| step4 `--finalize` 覆盖 AI 精读 | review_summary_build.py 幂等合并（保留已精读条目），重跑不丢失；若仍异常检查脚本 existing 合并逻辑 |

## 3. 常见问题（FAQ）

**Q: `ustplan step step1` 报"要求当前阶段为 phase3-course-analysis"？**
先 `ustplan phase begin phase3-course-analysis`（phase1/2 需先 done）。

**Q: 会话中断如何续跑？**
`ustplan status` 看阶段/任务/产物 → `ustplan resume` 给出下一步命令 → 按提示继续。
后台任务未完成的用 `ustplan job status <id>` 检查，done 后产物自动收录。

**Q: 产物校验失败（R2）？**
`python3 scripts/harness/schema_validate.py --dir data --dir output` 查看具体错误；
停在本 step 修复后重跑 `ustplan step <N> --force`（或 --finalize 对 step4）。

**Q: 想调评分权重/方案数量/超时？**
编辑 `config/ustplan.json`（scoring/defaults/jobs 节），`ustplan doctor` 校验合法性。
参考 `templates/schemas/config.schema.json`。

**Q: 想固定目标学期而不是 latest？**
`ustplan start --session <SESSION>`，或在 P1 确认时写入 decisions。

**Q: 后台任务进程僵死？**
`python3 scripts/harness/doctor.py` 会报告孤儿记录；
`ustplan job clean <id>` 清理（自动击杀残留进程）。

**Q: cookie 过期？**
`python3 scripts/cookies_setup.py` 交互重贴；`--check` 只显示状态不显示值。

**Q: 想清理全部运行数据重新开始？**
`python3 scripts/ustplan.py start --force` 重置 run；产物仍保留，
也可手动清空 data/output/cache（保留各 README.md）。

## 4. 凭据与安全约定

- cookie 文件 `credentials/cookies.txt`：**不要手建**，用 `cookies_setup.py` 交互引导
  （粘贴 → 自动写文件 → 自动验证）；SIS 用 `PS_TOKEN` 行，USTspace 用 `ustspace_session` 行
- **AI 收到用户令牌的固定流程**（见 phase1-input skill）：直接以 `PS_TOKEN=…` /
  `ustspace_session=…` 两行写入 cookies.txt（URL 编码如 `%3D` 先还原）→ `ustplan doctor`
  验证 → 不读文档/代码探索；AI 上下文不得出现 cookie 值
- AI 上下文不得出现 cookie 值；预检只输出状态（OK/EXPIRED/MISSING/UNREACHABLE）；
  SIS 判定用 Student Center 页正特征（icsid 等），无 cookie 时负特征不可靠
- 测试 cookie 放项目外临时目录，用后删除
