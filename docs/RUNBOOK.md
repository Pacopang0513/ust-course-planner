# 排障手册（RUNBOOK）

异常处理矩阵与后台任务说明。AI 遇到异常时先查本表，再按固定模板回复用户。

## 1. 后台任务清单（job-id 固定，超时在 config/ustplan.json → jobs）

| job-id | 命令（ustplan job start 自动构建） | 启动时机 | 默认超时 | 产物 |
|---|---|---|---|---|
| wcq_full | `wcq/crawler.py --session … [--admission-year …]`（入学年份已知自动注入，顺带抓 CC 池） | P1 输入收集 + 令牌预检（doctor）OK 后（start 即启动） | 25 分钟 | data/courses_{s}.json + cc_courses_{s}.json |
| buckets_pre | `rank/buckets.py --profile … --track …` | major+track 给出后 | 5 分钟 | data/unmet_courses.json（基架） |
| sis_fetch | `sis/parser.py --fetch` | cookie 到位后 | 10 分钟 | cache/sis/*.json |
| ustspace_pre | `ustspace/crawler.py --codes-file filter_report.json` | P2 提问前 | 15 分钟 | data/ustspace_reviews.json |

- 同 job-id 已 running/done 时 start 被拒绝；重跑 `ustplan job start <id> --force`
- 超时自动击杀并标记 failed(timeout)；机器休眠致 worker 消失 → crashed，start 自动清理
- `ustplan job status/wait <id>` 完成后自动收录产物到 manifest（wcq_full 顺带解析 session）
- 产物收录判定：status/wait 输出含 "done" 或 "完成" 且 exit 0 即收录（2026-08 修复）

## 1.5 学分与 CC 产品规则（2026-08 固化，AI 排课决策前必读）

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

## 2. 异常处理矩阵（固定）

| 情况 | 处理 |
|---|---|
| 选课写入（enrollment-commit）学期未开放 | `cart.py check` 探测 + 产品化告知等待学校通知（26-27 Fall 通常 8 月中下旬）；不重复尝试、不猜测 |
| 选课清单含 TBA 课程 | 不提交，等 Class Schedule 公布时间后重跑 `cart.py build` 补选 |
| 缺少 admlu_session（admlu65 会话） | 引导用户浏览器登录后复制会话 cookie 写入 cookies.txt（AI 不接触明文）；提交始终由用户人工执行 |
| SIS cookie 失效 / 抓取失败 | 固定模板报错（产品化），引导 `cookies_setup.py --listen` 一键刷新（分段式：`--gen-code` 生成连接码 → 连步骤清单告知用户 → 用户确认就绪后 `--listen --code <同一码> --user-ready`；或交互粘贴失效键），回退等待；不猜测数据；major+track 路径继续并行 |
| USTspace cookie 失效 | 同上引导；失败课程标记 failed[]（无评论 API 也返回 error 属正常），继续其余 |
| 扩展报"可见 cookie: (空)" / No host permissions | **不是未登录**：即使未登录，ust.space 也会设置 `XSRF-TOKEN`/`ustspace_session` 访客 cookie——报空说明扩展对该域权限未生效（cookies API 对无权限 URL 静默过滤）。处理：`chrome://extensions`（Edge 同）对该扩展点「重新加载」→ 重启浏览器仍不行则检查扩展「网站访问权限」；扩展代码更新后必须重载才生效 |
| 后台任务 failed(timeout/crashed) | 告知"数据抓取中断，正在重试"，`ustplan job start <id> --force` 重跑；仍失败按上两行；不携带坏数据前进 |
| **后台任务 WinError 193（Windows）** | `.py` 不能直接作为可执行文件启动；jobs.py 已自动加解释器前缀（见 `_run_job`），若再出现检查 cmd[0] 是否为 `.py` 且经 `ustplan job start` 启动（勿绕过 jobs.py 直接 Popen） |
| 本地 curriculum 缺失 | 二次匹配（web-crawl-guide §4）；**优先 `prog_crs/build.py --year` 重建**；2022-23 及更早 prog-crs 已下线无法重建 → `ar_to_unmet.py` 生成基架（**人工工具，不接入 step 合约链**——step1 仍要求本地 curriculum，产物仅供人工核对，不得直接推进） |
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
推荐一键刷新：AI 先 `python3 scripts/cookies_setup.py --gen-code` 生成 4 位
连接码，把端口（默认 8765）与连接码告诉用户 → 用户确认就绪后
`cookies_setup.py --listen --code <连接码> --user-ready --timeout 600` → 浏览器扩展按钮
发送 → 自动验证）；或交互重贴（`cookies_setup.py` 无参数粘贴）；
`--check` 只显示状态不显示值，并提示凭据年龄（TTL，config →
`credentials.ttl_hours` 默认 12 小时）。

**Q: `decisions set` 传 JSON 在 PowerShell 总被引号吃掉？**
用 `--value-file`：把 JSON 存成文件（如 `tmp_p1.json`），
`ustplan decisions set P1 --value-file tmp_p1.json`（自动兼容带 BOM 的 UTF-8）。

**Q: 预选课（pre_enrolled）抓到的学期与目标学期不符？**
SIS 页面 term 由会话决定（URL STRM 不切学期），非选课季可能显示旧学期；
`ustplan job status/wait sis_fetch` 会输出 WARN。此时预选课不视为目标学期
固定选课，P2 展示时向用户说明核对。

**Q: 想清理全部运行数据重新开始？**
`python3 scripts/ustplan.py start --force` 重置 run；产物仍保留，
也可手动清空 data/output/cache（保留各 README.md）。

## 4. 凭据与安全约定

- cookie 文件 `credentials/cookies.txt`：**不要手建**，用 `cookies_setup.py` 获取
  （三种方式等价）：
  1. **一键获取（推荐）**：AI 先 `--gen-code` 生成 4 位连接码，把安装/登录
     步骤清单 + **端口（默认 8765）与连接码** 一起给用户（用户可预填扩展
     设置）→ **用户确认就绪后** → `cookies_setup.py --listen --code <连接码>
     --user-ready --timeout 600` 启动本机接收端（仅 `127.0.0.1` 回环 +
     连接码校验；`--listen --code` 必须带 `--user-ready` 且码为 `--gen-code`
     刚生成，否则拒绝启动——防止 AI 跳过"先给码+教程、等用户确认"）→
     在 SIS / ust.space 登录页各点一次按钮 → 自动写入并验证；
     **必须用户确认后再启动接收端**（用户操作浏览器期间接收端空转会
     超时，造成双方互相等待；连接码提前固定才能让用户预填）；
  2. 交互引导：粘贴（bookmarklet JSON 或 key=value）→ 自动写文件 → 自动验证；
  3. F12 → Network → 复制 Cookie 请求头 → 粘贴（bookmarklet 读不到 httpOnly 时）。
- **凭据有效期（TTL）**：`credentials/meta.json` 记录获取时间；超过
  `config → credentials.ttl_hours`（默认 12h）后 `--check` / `doctor` /
  `ustplan status` 提示"建议刷新"（SIS 会话通常数小时过期，提前提醒避免
  流程中途失败；警告级别，不阻断）。
- **AI 收到用户令牌的固定流程**（见 phase1-input skill）：直接以 `PS_TOKEN=…` /
  `ustspace_session=…` 两行写入 cookies.txt（URL 编码如 `%3D` 先还原）→ `ustplan doctor`
  验证 → 不读文档/代码探索；AI 上下文不得出现 cookie 值
- AI 上下文不得出现 cookie 值；预检只输出状态（OK/EXPIRED/MISSING/UNREACHABLE）；
  SIS 判定用 Student Center 页正特征（icsid 等），无 cookie 时负特征不可靠
- 测试 cookie 放项目外临时目录，用后删除
