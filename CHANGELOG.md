# 变更记录（CHANGELOG）

## 2026-08-14（五）— 报告末尾新增"关闭开发者模式"安全提醒 + 环境清理

| 变更 | 说明 | 文件 |
|---|---|---|
| **安全提醒固定段落** | 报告模板末尾（选课时间提醒之后）新增固定段落：提醒用户自行关闭浏览器"开发者模式"（扩展已不再需要，预防风险），附 1-2-3 操作步骤（chrome://extensions 关开关 / 可选移除扩展），并说明不影响已生成方案 | templates/reports/final_report.md.tpl |
| **skill 同步** | phase4-report AI 职责第 3 条：末尾提醒含"开发者模式关闭提醒"（不可删除，用户面输出同样带）；harness 流程行与对照表同步 | skills/phase4-report/SKILL.md, skills/harness/SKILL.md |
| **环境清理** | 删除测试遗留 `credentials/connect_code.json`、全部 `__pycache__`，恢复无产物状态（data/cache/output 为 gitignore 目录，运行前不存在） | 仓库清理 |

## 2026-08-14（五）— cookies_setup.py 专业重构轮（统一职责、删除冗余）

| 变更 | 说明 | 文件 |
|---|---|---|
| **职责分离统一** | 语法层与语义层各管一事：`--listen` 必带 `--code`/`--user-ready` 由解析器强制（usage 错误）；`listen_gate` 只校验"码等于最近一次 `--gen-code` 生成的码"（顺序门禁），删除其重复的 user_ready 检查 | scripts/cookies_setup.py |
| **指引文案单源** | 分段式流程说明收敛为常量 `SEGMENTED_FLOW`，--gen-code 输出 / 解析器报错 / 门禁报错三处共用，消除三份重复表述 | scripts/cookies_setup.py |
| **删除冗余** | ①未使用常量 `REQUIRED_KEYS`（credentials.py 已有）删除；②`run_listen` 的 `code` 改为必填参数并删除 None 抛错兜底与 `token` 临时变量（修一处残留 `{token}` 引用）；③`meta_update` 冗余 `Path()` 包装删除 | scripts/cookies_setup.py |
| **文案订正** | 文档头模式数"七种"→"六种"；run_check 失败提示不再裸写 `--listen`（该形态已被语法层禁用） | scripts/cookies_setup.py |
| **配套单测** | 删除 listen_gate 的 user_ready 用例（已归解析器），gate 测试与纯函数签名同步；全量 168 例通过 | scripts/tests/unit/test_cookies.py |

## 2026-08-14（五）— 裸 --listen 禁用（根治"未先给码+教程就直接启动接收端"复发）

| 变更 | 说明 | 文件 |
|---|---|---|
| **裸 --listen 从语法层删除** | 根因：`--listen` 不带 `--code` 走"独立模式"随机生成新码并打印，完全绕过 `--gen-code` + `--user-ready` 门禁——AI 反复直接启动接收端、用户看不到码、双方互等的 bug 源头。改为**语法层强制**：`--listen` 必须同时带 `--code` 与 `--user-ready`，缺失即解析器 usage 错误（exit 2），运行时不存在裸 listen 分支；`run_listen` 不再生成/兜底连接码（传入 None 直接抛错）；`--code` 必须等于最近一次 `--gen-code` 生成的码且带 `--user-ready` 的校验保留为顺序门禁（先取码 → 告知 → 确认 → 才启动） | scripts/cookies_setup.py |
| **--gen-code 输出步骤清单** | `--gen-code` 除 4 位码外，一并输出"先告知用户 → 停下等确认 → 才 --listen"的固定步骤提醒，AI 直接转发给用户 | scripts/cookies_setup.py |
| **配套单测** | 原"无 --code 独立模式不受影响"用例反转为"裸 --listen 解析器拒绝（exit 2）"；新增"有 --code 缺 --user-ready 同样语法拒绝"；--gen-code 输出含步骤清单断言 | scripts/tests/unit/test_cookies.py |
| **排障文案同步** | 扩展 README"连接码不正确"行：裸 `--listen` 不存在合法调用形态，一律以 AI 告知的码为准 | extensions/ust-cookie/README.md |

历史 CHANGELOG 旧条目（含"无 --code 独立模式不受影响"）如实保留。

## 2026-08-14（五）— 一键扩展流程复查统一轮（消除残存矛盾表述）

| 变更 | 说明 | 文件 |
|---|---|---|
| **超时数值统一** | phase1-input 禁启说明原"300s 超时"与命令 `--timeout 600`、脚本默认 120 均不符 → 改 600s | skills/phase1-input/SKILL.md |
| **扩展弹窗文案** | 标签/校验提示原"连接码（--listen 终端显示）"会误导用户去找 AI 终端；分段式流程中码由 AI 提前生成并直接告知 → 改"连接码（AI 会告诉你 4 位数字，保存一次即可）" | extensions/ust-cookie/popup.html, popup.js |
| **GUIDE 顺序统一** | 交互引导原"运行 --listen 后用扩展按钮"（先收后发）→ 改为分段式："先告诉用户该怎么做（--gen-code + 步骤清单，扩展预填）→ 等用户备好码确认就绪 → --listen --code <同一码> --user-ready → 用户点按钮获取" | scripts/cookies_setup.py |
| **简写引导补全门禁** | RUNBOOK 异常矩阵 SIS cookie 失效行、web-crawl-guide TTL 超期引导补分段式（--gen-code → 告知 → --user-ready），与完整版一致 | docs/RUNBOOK.md, skills/web-crawl-guide/SKILL.md |
| **docstring 用法行** | `--listen` 用法行补 `[--user-ready]` | scripts/cookies_setup.py |

历史 CHANGELOG 旧条目（无 --user-ready 的旧命令、300s 历史描述）如实保留。

## 2026-08-14（五）— 一键扩展门禁加固（根治"AI 跳过教程+连接码直接启动接收端"）

| 变更 | 说明 | 文件 |
|---|---|---|
| **脚本硬门禁（防复发核心）** | 原 `--listen --code` 可被 AI 直接启动：不传 `--code` 时随机生成并打印（用户看不到终端），跳过"先给码+教程、等用户确认"也不会报错（静默空转超时）。新增：`--gen-code` 将码写入状态文件 `connect_code.json`（随 cookie 文件目录）；`--listen --code` 必须满足①码等于最近一次 `--gen-code` 生成的码、②显式传 `--user-ready`，否则拒绝启动并输出分段式流程提示。独立交互模式（`--listen` 不带 `--code`）不受影响 | scripts/cookies_setup.py |
| **skill 矛盾表述清除** | 根因：phase1-input SKILL.md 原句"AI 才运行 `--listen --code <同一连接码>` 给出连接码，再引导用户点按钮"把"给出连接码"接在 `--listen` 之后，读作"先跑接收端再给码"。重写为固定三步：(1) `--gen-code` 取码；(2) 完整步骤清单+端口+**4 位码本体**一次告知用户，停下用 question 问"准备好了？"；(3) 确认后才 `--listen --code <同一码> --user-ready --timeout 600`。另禁止"只说生成一个连接码你点按钮即可"的缩略话术 | skills/phase1-input/SKILL.md, skills/harness/SKILL.md, skills/web-crawl-guide/SKILL.md, docs/RUNBOOK.md, scripts/README.md, extensions/ust-cookie/README.md |
| **思维自检清单加项** | harness"输出前思维自检"新增"一键扩展门禁"：连接码+端口是否已随清单显式告知（码本体写出来）？用户是否已确认"准备好了"？未确认禁止 `--listen` | skills/harness/SKILL.md |
| 配套单测 | 新增 10 例（状态文件写读 2 / gate 纯函数 4 / CLI 子进程门禁 4：缺 --user-ready 拒绝、未 --gen-code 拒绝、码不一致拒绝、无 --code 独立模式不受影响）；test_cookies 共 27 例通过，全量 167 例通过 | scripts/tests/unit/test_cookies.py |

## 2026-08-14（五）— 一键扩展连接码提前生成（分段式流程补齐：端口+连接码随步骤清单先给用户）

| 变更 | 说明 | 文件 |
|---|---|---|
| **`--gen-code` / `--listen --code`** | 原流程连接码只能在 `--listen` 启动时随机生成，用户无法提前在扩展里预填，导致"AI 启动接收端 → 用户还在装扩展/登录 → 空转超时、双方互等"。新增：`--gen-code` 输出 4 位连接码（AI 提前生成）；`--listen --code NNNN` 固定使用该码（不传则维持随机）；`validate_code` 校验格式。端到端验证：固定码两源 POST 均 200 写盘 | scripts/cookies_setup.py |
| **分段式流程更新** | AI 流程改为：先 `--gen-code` 拿连接码 → **步骤清单 + 端口（默认 8765）+ 连接码一次告知**（用户可提前装扩展、预填保存、登录两站）→ 停下问"准备好了" → 确认后才 `--listen --code <同一码> --timeout 600`；修复用户不知如何获取扩展/不知端口连接码的问题 | skills/phase1-input/SKILL.md, skills/web-crawl-guide/SKILL.md, skills/harness/SKILL.md, README.md, docs/RUNBOOK.md, extensions/ust-cookie/README.md, scripts/README.md |
| 配套单测 | `validate_code` 新增 2 例（4 位数字接受 / 空、位数错、非数字、None 拒绝），test_cookies 共 17 例通过 | scripts/tests/unit/test_cookies.py |

## 2026-08-14（五）— 扩展 cookie 读取权限修复（"可见 cookie: (空)"误报）

| 变更 | 说明 | 文件 |
|---|---|---|
| **权限缺失误报修复** | 根因：`chrome.cookies.getAll({url})` 在扩展缺少该域 host permission 时**静默返回空数组**，被误报为"未登录"。修复：改为逐键 `cookies.get({url,name})`（权限缺失时明确抛错）+ 发送前 `permissions.contains` 预检 + catch 归一化提示"重载扩展/重启浏览器"；`detectSource` 改精确域名匹配；manifest 补 `https://*.ust.space/*`（覆盖子域）。实测未登录的 ust.space 也会设置 `XSRF-TOKEN`/`ustspace_session` 访客 cookie，"可见 cookie: (空)" 基本可断定是权限未生效 | extensions/ust-cookie/popup.js, manifest.json, README.md（排障表）, docs/RUNBOOK.md（异常矩阵） |

## 2026-08-14（五）— 一键扩展获取改分段式交互 + 连接码 4 位

| 变更 | 说明 | 文件 |
|---|---|---|
| **一键扩展改分段式** | 用户选择扩展方式后，AI 先输出安装/登录步骤清单（装扩展 → 登录 SIS → 登录 ust.space）→ 停下用 question 工具等用户确认"装好了" → **确认后才启动 `--listen` 接收端**；修复原流程"AI 直接启动接收端、用户仍在操作浏览器 → 300s 空转超时、双方互相等待"的交互 bug | skills/phase1-input/SKILL.md, skills/web-crawl-guide/SKILL.md, skills/harness/SKILL.md, README.md, docs/RUNBOOK.md |
| **连接码 6 位 → 4 位** | `make_token()` 改 4 位（`10**4`/`:04d`），扩展端校验 `^\d{4}$`、输入框 maxlength=4，测试与文档同步（test_make_token_four_digits，15 例通过） | scripts/cookies_setup.py, extensions/ust-cookie/popup.js, popup.html, scripts/tests/unit/test_cookies.py, docs/RUNBOOK.md, extensions/ust-cookie/README.md |

## 2026-08-13（二）— cookie 一键获取 + 凭据有效期（TTL）提醒

| 变更 | 说明 | 文件 |
|---|---|---|
| **浏览器扩展一键获取** | 新增 `extensions/ust-cookie/`（Chrome/Edge Manifest V3，unpacked 加载）：`chrome.cookies` 读取当前站点 cookie（**含 httpOnly 的 PS_TOKEN**，bookmarklet 做不到）→ 仅经本机回环 POST 到接收端；cookie 不落扩展存储；只发送当前站点已知键（SIS: PS_TOKEN/JSESSIONID/PS_TOKENEXPIRE；USTspace: ustspace_session） | extensions/ust-cookie/*（新） |
| **`cookies_setup.py --listen` 接收端** | 绑定 127.0.0.1 + 随机 token（4 位连接码，secrets 生成），收齐 SIS+USTspace 两源或超时自动退出；协议纯函数 `handle_submit_payload`（连接码校验 → 按源过滤已知键 → 写盘 + meta）；错误响应不携带 cookie 值；bookmarklet / F12 粘贴保留为降级通道；`--token-test` 离线自测（用临时文件，不触碰真实凭据） | scripts/cookies_setup.py |
| **凭据有效期（TTL）提醒** | 新增 `credentials/meta.json`（fetched_at/sources，跟随 cookie 文件目录）；`config → credentials.ttl_hours`（默认 12h，schema 同步）；`--check` / `doctor` / `ustplan status` 输出"凭据已 X 小时，建议刷新"（警告级别不阻断）；失效引导指向 `--listen` | scripts/credentials.py（新）, config/ustplan.json, templates/schemas/config.schema.json, scripts/ustplan.py, harness/doctor.py |
| **统一凭据模块** | 收敛三处重复 load_cookies（cookies_setup / ustspace crawler / sis parser）→ `scripts/credentials.py`（load/save/filter_known/meta/TTL；utf-8-sig 兼容 BOM；写盘后 icacls 收窄当前用户权限）；接口按可替换存储后端设计（二期 DPAPI 加密插槽） | scripts/credentials.py（新）, scripts/ustspace/crawler.py, scripts/sis/parser.py |
| 文档同步 | README 使用说明改推荐一键方式；RUNBOOK §2/§4（获取三方式 + TTL）；web-crawl-guide 通用规则；phase1-input skill（P1 收集支持一键/粘贴两种） | README.md, docs/RUNBOOK.md, skills/web-crawl-guide, skills/phase1-input |

配套：单测新增 15 例（load/save 往返、BOM、按源过滤、meta 跟随/合并、TTL 过期/
新鲜/无 meta、协议 6 例：错码拒收/未知源/过滤/合并保留/空 cookie 拒收/连接码格式）；
全量 155 例通过；`--listen` 端到端验证（子进程启动 → 解析端口/连接码 → 模拟扩展
提交两源 → 写盘 + meta 落位 → 自动退出）；config schema / doctor 回归通过。

## 2026-08-13 — minor 合并修复 + 未修学分按桶聚合 + 历史学期教授对照

| 变更 | 说明 | 文件 |
|---|---|---|
| **副修（minor）漏读修复** | 根因三处：① 文件名按 `{m}.json` 查（实际 `MINOR-{m}.json`）永远报缺失；② 找到也只打印不合并（"二期增强"从未实现）；③ MINOR-MATH/AERO/BDT 等 courses=[] 仅描述性 note，旧 `RE_LEVEL_POOL` 匹配不上 → 空组跳过。修复：按 `MINOR-{m}.json` 读取并**合并要求桶**（prefix `min`，新类别 `minor_required`/`minor_elective`）；新增 `_level_pool_spec` 描述性级别范围解析（"courses at 1000- and 2000- level (except courses coded from 1000 to 1600)" / "at 3000- level or above"）从本学年课表生成真实候选（级别带语义 1000-2999、排除段剔除、subject 过滤）；学分描述池按 credits/3 推导配额（MINOR-MATH 18 学分 → 6 门）；P3 展示副修计数与 double-count 提示 | rank/buckets.py, templates/schemas/unmet_courses.schema.json, report/stats.py, report/render.py, skills/step1 |
| **未修学分统计修复（误算 300）** | 原逐课程累加：3 学分选修池 100 门候选 → 300。改按 bucket 配额聚合：`bucket_credits = quota × 桶内学分中位数`（`config → defaults.unmet_credit_mode: median/min`）；学分缺失课程按桶计数；新增 `buckets.bucket_credit_sum()` 纯函数（可单测）；schema 描述同步 | rank/buckets.py, config/ustplan.json, harness/config.py, templates/schemas/unmet_courses.schema.json |
| **历史学期教授对照（历史感知排课）** | 新后台 job `wcq_history`（crawler 新增 `--subjects-file`，新脚本 `wcq/history_fetch.py` 逐前序学期抓取候选 subject）；新脚本 `rank/history_compare.py`（step5.5，产物 `data/history_compare.json` + 新 schema）：对照前两学期开课与授课教授（`harness.config.previous_sessions()`：Fall→2540/2530 等），用 USTspace 评论算该教授在**这门课**的评分（raw 优先、限定该学期，回退全部）；往期最高 − 本学期 ≥ `history.threshold`（默认 0.5）→ 本年度评分按 `penalty_pct`（默认 10%）降权（`score_effective`，仅影响排序，原始分保留）+ 延后建议（`defer_advice[]` + notes："可考虑下个同序学期（四学期循环）再修"，如去年 Spring → 今年 Spring）；前序数据缺失优雅降级，job 完成后 `step step6 --force` 重跑即可 | rank/history_compare.py（新）, wcq/history_fetch.py（新）, rank/planner.py, wcq/crawler.py, harness/config.py, harness/contracts.py, ustplan.py, templates/schemas/history_compare.schema.json（新）, templates/schemas/timetable_plan.schema.json, config/ustplan.json, skills/harness, skills/step6 |
| **planner 类别/输出扩展** | CATEGORY_ORDER 增加 minor_required/minor_elective；方案新增 `minor_credits` 与 `defer_advice[]` 字段（schema 可选）；stats/render 同步展示 | rank/planner.py, templates/schemas/timetable_plan.schema.json, report/stats.py, report/render.py |
| **多栏位同课重复入排修复** | 三用户 mock 提取验证发现：同一课程同时满足多个栏位（主修 + 副修/第二主修 double count，如 MATH 2411 同在主修与 addCOSC 桶）且课程有多 section 或 TBA 时，此前两桶各选一次（COMP 2011 L1+L2 计 6 学分）。修复：`try_add` 全局课程唯一（同 code 已入选 → 不重复选取 + note）；顺带修复 filter `eval_one` 未开设课程 UnboundLocalError（info 未定义，必修未开设时真实触发） | rank/planner.py, rank/filter.py |

配套：单测新增 33 例（学分聚合 7 / 级别池规格 4 / minor 合并 4 / previous_sessions 6 /
next_occurrence 3 / sem_matches 4 / history compute 3 / planner 历史池 2 / 多栏位去重 2）；全量 140 例通过；
config schema 校验通过；smoke 验证：MINOR-MATH 合并 3 门（1011 被 1000-1600 排除段剔除）、
MATH 2023 往期教授提升 +1.12 → 降权 10% + 延后建议 2026-27 Spring。
三用户 mock 提取验证（COMP+minor MATH / PHYS P&M track+预选课 / MATH General track+第二主修 COSC）：
step1 三次均 exit 0，未修学分逐桶验算与产物一致（97.5/66.5/79.5），minor 桶 quota=6、
级别池 11 门、track 限制、预选课登记、pre-req 引用补录均正常。

## 2026-08-09（六）— 排课偏好：整天空闲优先 + 正餐时段避让

| 变更 | 说明 | 文件 |
|---|---|---|
| **排课偏好（config → planner）** | `prefer_day_off`（高权重：section 组合优先复用已有上课日，压缩每周上课天数、尽力空出整天空闲；无法压缩时 notes 说明）+ `prefer_meal_free`（低权重：同等天数下优先避开午餐/晚餐保护时段，默认 12:00-14:00 / 18:00-20:00，`meal_windows` 可调）；`place_course`/`_place_variant` 从"首组可行解"改为全组合枚举按偏好取优（天数字典序 → 正餐冲突数 → section 名序，确定性可复现） | config/ustplan.json, rank/planner.py, templates/schemas/config.schema.json |
| **方案舒适度输出** | 每套方案新增 `days_used`（有课天，含预选课占用）/ `free_days`（无课工作日，空 = 无法整天空闲）/ `meal_conflicts`（占用正餐时段的 天×餐次×课程 清单）；notes 前置"整天空闲/未实现"提示、追加用餐冲突提醒；控制台、ASCII 周历、最终报告同步展示（GBK 控制台用纯文本，弃 ✓ 字符） | rank/planner.py, report/render.py, report/render_grid.py, templates/schemas/timetable_plan.schema.json |
| **step6 skill 同步** | 展示方案时**必须向用户说明空闲日与用餐冲突**（free_days 空 = 无法实现整天空闲） | skills/step6-timetable-planning/SKILL.md |

配套：单测新增 5 例（复用已有日空出整天 / 同天数避午餐 / 无备选时餐冲突可接受 / emit 三字段与 notes / 五天有课无法空闲）；106 例全过。

## 2026-08-09（五）— 松弛度修复（学期语义统一）+ 环境清理

| 变更 | 说明 | 文件 |
|---|---|---|
| **学期编码修正（重要，两轮）** | 第一轮实测 wcq subject 页误判（模板固定显示当前学期）；第二轮以 wcq **索引页学期下拉**逐项确认（2026-08-09 复核，用户质疑触发）：**2610=2026-27 Fall(10)、2520=2025-26 Winter(20)、2530=2025-26 Spring(30)、2540=2025-26 Summer(40)** → 正确映射 **Fall=10/Winter=20/Spring=30/Summer=40**（config 原 Fall:0 错误，且首轮"修正"的 Winter:5/Spring:20 亦错）；subject 页模板不可作为学期依据 | config/ustplan.json, harness/config.py |
| **学期语义统一** | 新增 `harness.config.semester_of_session()`（config semesters 映射唯一权威）；buckets `estimate_semesters_left` 与 report `semester_label` 弃用硬编码尾号字典，改调该函数（支持明年 2710/2720 等任意学年，未知尾号如 2540 安全降级） | harness/config.py, rank/buckets.py, report/render.py |
| **学分上下限/默认参数统一** | planner MAX/MIN_CREDITS（原硬编码 12/18）、--target/--plans/--top 默认值全部改从 config defaults 读取（credits_min/max/target_credits/plans/candidate_pool）；buckets `graduation_target_credits`（原硬编码 120）改读 config `defaults.graduation_credits`（schema 同步） | rank/planner.py, rank/buckets.py, templates/schemas/config.schema.json |
| **SIS fetch 学期探测** | sis/parser.py 帮助文本修正（原"默认 2610"与 default="" 不符）；`--fetch` 未指定 session 时自动从 wcq 探测最近学期（Pre-Enroll STRM 必须有效），探测失败降级提示；补 scripts/ 到 sys.path | scripts/sis/parser.py |
| **环境清理** | 删除全部运行时产物（credentials/cache/data/output/user 恢复为仅 README；含开发用 cookie 与 SIS 个人数据如姓名/成绩单）、__pycache__；扫描确认无测试痕迹残留（仅 fixtures 中的 mock 占位） | 运行时目录（gitignored） |

配套：单测新增 5 例（明年 session 回归 + semester_of_session + 未知尾号安全）；101 例全过；doctor 全绿（cookie 缺失为预期——凭据已按要求删除）。

## 2026-08-09（四）— 学分指导 + 特殊规则知识库 + pre-req 成绩要求

| 变更 | 说明 | 文件 |
|---|---|---|
| **未修学分统计（P3 目标学分参考）** | step1 产物新增 `unmet_credits`（未修学分总和）/ `estimated_semesters_left`（剩余学期估算，4 年制 8 学期含当前）/ `credits_per_semester_estimate`（平均每学期建议）；P3 问目标学分前展示建议值，目标明显偏低时提示毕业风险（Agent 指导义务；双主修 double count 会高估，以 AR 为准）；报告模板第 2 节同步展示 | rank/buckets.py, templates/schemas/unmet_courses.schema.json, report/render.py, skills/step1-unmet-calculation |
| **特殊规则知识库（RULES.json）** | 全局规则落盘：`h_course_equivalence`（COMP 2012H = 2011+2012 组合等价，学分差额补足；2711H/3111H/3711H 单门升级等价）、`double_count`（COSC 双主修 20 single-counted）、`year_long`（PHYS 4291）、`ext_capstone_pairing`（EMIA 4990/4991）、`grading_prereq`（PHYS 1314 需 1312 成绩）；AGENTS.md 固定认知 + harness skill 检查清单（每次流程 AI 必须过一遍知识库）；course_notes schema 支持全局文件（subject 空） | database/course_notes/RULES.json, templates/schemas/course_notes.schema.json, AGENTS.md, skills/harness |
| **pre-req 成绩要求（grading）** | filter 解析 "Grade X or above in CODE" / "Pass grade in CODE"（三状态：不存在 / 需要某 grading / 未填入需复核）；对照 passed_courses.json 成绩逐条判定（等级序 A+>A>…>Pass）；**成绩判定与 OR/AND 分支绑定**（分支内不达标不影响已满足分支；未修课程的成绩要求由课程层面覆盖）；不达标 → `grading_not_met` 标记 + step6 waiver 提醒"成绩不达标需豁免"；grading 沿 filter → bucket_score → planner 透传（prereq_grading） | rank/filter.py, rank/bucket_score.py, rank/planner.py, templates/schemas/filter_report/course_scores/timetable_plan, skills/step3-schedule-filter |
| schema_validate 漏检 course_notes 目录（RULES/EMIA/PHYS 从未过 schema） | DIR_SCHEMA 增加 course_notes | harness/schema_validate.py |

配套：单测新增 11 例（剩余学期 5 + grading 7 中 6 例与既有合并后共 96 例全过）；
filter selftest 更新（grading 用例）；demo R1-R6 全绿；RULES.json schema 校验通过。

## 2026-08-09（三）— 报表复核修复（对照外部错误报表逐项核实）

| # | 报表问题 | 核实结果 | 处理 |
|---|---|---|---|
| 1 | sis/parser.py fetch_pre_enroll NameError（emplid 未定义） | **已修复**（2026-08-07，URL 已去变量） | 无 |
| 2 | wcq latest 抓 0 门课 | **已修复**（main 先 latest_session() 再 run） | 无 |
| 3 | planner `--must-take` 重复 flag 只保留最后一个（nargs="+" + store 静默吞值） | **真实存在** | `--must-take/--exclude/--credits-override` 改 `action="append"` + 扁平化，兼容单次多值与重复 flag |
| 4 | "MATH 2000-level" 假课 + "Any 3 courses of" 配额误判 1 | 假课**已修**（B1 负向前瞻）；配额句式**真实存在** | `RE_ANY_N` 支持 `any N courses of`；**级别池（SUBJ N000-level or above）从本学年课表生成真实候选**（限定 subject、排除必修占用），根治 MATH/COSC 选修池静默缺失；嵌套级别池（2000/3000/4000）自动合并为最低级别池 + P3 复核提示 |
| 5 | 已修抵扣没过滤 subject（COMP 课计进 MATH 池） | 我们仓库生成时按 subject 过滤 + 排除必修占用，**无此问题**；新生成逻辑已内置该防护 | 无（防护随 #4 实现） |
| 6 | COSC 选修被波段过滤丢 3xxx/4xxx | **不存在**（无波段过滤代码）；级别池生成全量（≥N 千位） | 无 |
| 7 | doctor cookie 全绿报 FAIL | **已修复**（按 EXPIRED/MISSING/UNREACHABLE 关键词判定） | 无 |
| 8 | 双专业不支持 | **已修复**（2026-08-09 二轮 B4） | 无 |
| 9 | pre_enroll.json 命名不一致 | **不存在**（统一 pre_enrolled.json） | 无 |
| 10 | top_per_bucket=3 截候选、must-take 救不回 | must-take 可从 ranked_out 硬插（build_pool extra），**不成立**；放宽属调参 | 无 |

配套：新增单测 9 例（配额句式 5 + 级别池 4）；84 例全过；demo R1-R6 全绿。
另修：级别池生成 1 门候选时误走 single 分支（quota 退化为 1）→ 强制 pool 分支；
空组警告引用残留 note 变量（显示上一组的 note）→ 用当前组 note。

## 2026-08-09（二）— 普适性问题修复（COSC+MATH 场景）

| 问题 | 修复 | 文件 |
|---|---|---|
| **note 课程码误提取**：`_note_courses`/`RE_CODE` 把描述性课号 "COMP 2000-level" 提成假课 COMP 2000（`RE_VALID_CODE` 恰好放行）→ 假课进清单 | 课号正则加负向前瞻（`-level`/`or above`/`or below`/`or equivalent` 不提取）；filter.py 的 RE_CODE（pre-req/EXCLUSION 提取）同步加固 | rank/buckets.py, rank/filter.py |
| **空课程池静默跳过**：COSC 选修池 courses=[] 且 note 无真实课码 → 整组跳过且无警告（18 学分专业选修静默缺失） | 空组跳过时显式警告（含组名与 note 摘要）；提取补录课仍校验描述性课号 | rank/buckets.py |
| **status 不过滤**：passed_set 把 incomplete（挂科需重修）/audit/unknown 当已修扣除 → 挂科课漏出清单 | 白名单 PASSED_STATUSES（taken/transferred/exempted/in_progress）；planner 的 passed 计算同步走白名单（原为独立实现不过滤）；phase2 skill 转录规则同步 | rank/filter.py, rank/planner.py, skills/phase2-profile |
| **单主修限制**：buckets 只加载 first_major，double major（COSC+MATH）第二主修全部漏算；minor 仅提示 | P1 major/minor 改数组（schema 兼容旧单值）；contracts 校验改数组；buckets 加载 additional_major[]（prefix `add{CODE}` 防 bucket_id 冲突，track 分支按无分支）；phase1/phase2 skills 同步 | templates/schemas/decisions.schema.json, harness/contracts.py, rank/buckets.py, skills/phase1-input, skills/phase2-profile |
| **School Requirement 缺失**：SENG 无 SREQ 预构建（SBM/SSCI 四年齐全、SENG 全缺）；COSC 专业页无 SENG 入门池 | 从 COMP.json 提取 SENG 入门课池 + LANG 2030 → 生成 SREQ-SENG.json（2023-24/2024-25；2025-26 起官方取消 SENG 入门课，实测 PDF 确认改版，不生成）；buckets 按 profile.school 加载 SREQ-{SCHOOL}.json 并**与专业课程去重**（COMP 学生不重复），缺失时提示以 AR 为准 | database/curriculum/{year}/SREQ-SENG.json, rank/buckets.py |
| **池配额误判**：`_group_quota` 只认 "any N of"/"N courses out of M"，学院池 "8 courses from the specified list" 被误判 quota=1 | 增加 "N courses from" 模式 | rank/buckets.py |
| planner 缺少 rank 目录 sys.path（测试环境 `from filter import` 失败，顺带暴露 year_long 折算在测试环境从未生效） | planner 补 `sys.path.insert(0, scripts/rank)`；credits-override 单测改用非全年课 | rank/planner.py, scripts/tests/unit/test_fixes_20260807.py |

配套：单测 75 例全过（demo R1-R6 全绿）；COSC+MATH mock 全链路验证
（SREQ 去重合并 16 门、第二主修合并 15 门、incomplete 挂科课保留在未修清单、
已修 school req 桶正确移除）；filter selftest 通过。

## 2026-08-09 — 预选课（Pre-Enroll）全链路固化

| 变更 | 说明 | 文件 |
|---|---|---|
| SIS 预选课定位验证 | 用真实 PS_TOKEN 实测 Enrollment Summary 页：STRM 必须为有效 term code（空 STRM 返回 JS 空壳无网格）；未预选时网格无行 + `Total Unit Load: 0`（浏览器提示 "You are not enrolled in classes"），解析为空列表属正常 | skills/web-crawl-guide §2c, sis/parser.py |
| 扫描即落盘 | sis_fetch job 抓取预选课后**同步写 `data/pre_enrolled.json`**（与 cache 版同构同 schema），phase2 不再人工手写；job 已知真实 session 时自动注入 `--session`（STRM 有效） | sis/parser.py, harness/contracts.py, ustplan.py |
| step1 登记 bucket 归属 | buckets 记录预选课到 unmet `pre_enrolled[]`（带 bucket_id/category；课程池外记空桶）——预选课仍计入已确定，不重复推荐 | rank/buckets.py, templates/schemas/unmet_courses.schema.json |
| **评分 +20%** | step5 对预选课评分 ×（1+`scoring.pre_enroll_boost`，默认 0.2），加入所在栏位排名（无归属 → 独立 "pre_enrolled" 栏位）；score_reason/score_components 可追溯 | rank/bucket_score.py, rank/scoring.py, config/ustplan.json, templates/schemas/course_scores.schema.json, harness/contracts.py |
| **低优先级 drop 建议** | step6：预选课不重复入池（固定选课、占用时段）；若预选课即便 +20% 加权后评分仍低于方案已选最低分 → `pre_enroll_advice[]` 建议 drop，**提前告知风险**（学校一般不建议 drop 预选课，坚持需 waiver，可能影响下学期预选资格）；报告模板新增小节 | rank/planner.py, templates/schemas/timetable_plan.schema.json, report/render.py, templates/reports/final_report.md.tpl |
| 概念固化 | AGENTS.md 新增"预选课（Pre-Enroll）概念（固定认知）"；harness/phase2/step5/step6/phase4 skills 同步 | AGENTS.md, skills/* |

配套：`_pre_summary` 修复（读 confirmed/pending 格式）；新增单测（预选课加分 /
drop 建议）；rank testcase 增加预选课 mock 数据。

## 2026-08-07 — 全流程实测第二轮修复（PHYS+EXT AI 实排）

| 问题 | 修复 | 文件 |
|---|---|---|
| **漏读 Extended AI**（P1 只收 major+track，EXT AI 需求组未被纳入清单） | P1 三字段强校验：major/minor/extended_major 三状态（代码/NA/空置不通过）；`_phase1_checks` 缺任一字段即拦截；skill 模板同步；phase2 发现 AR 未声明需求组需回问 | templates/schemas/decisions.schema.json, harness/contracts.py, skills/phase1-input, skills/harness, skills/phase2-profile |
| EXT 顶点 4990/4991 选择错误（planner 自动选 3 学分 4991，但官方限定"无主修 FYP 才可用"） | 新增 `database/course_notes/` 课程语义落盘（EMIA/PHYS）；buckets 消费 `ext_capstone_pairing` 规则：主修含顶点课程（PHYS 4291）→ 自动移除 EMIA 4991 | database/course_notes/*, templates/schemas/course_notes.schema.json, rank/buckets.py |
| ustspace job 恒 failed（无评论课程 `{"error":true}` 计失败 exit 1） | 无评论数据记 `no_data`（正常），仅网络/登录等真实失败置非 0 | ustspace/crawler.py |
| manifest session 卡 "latest"（首次空跑产物干扰，`if not m.get("session")` 不更新） | `_newest_session` 数字 session 按文件名取最大；检测到真实数字 session 即更新 manifest | ustplan.py |
| PHYS 4291 全年 6 学分按学期 3 学分需手改抓取产物 | planner `--credits-override CODE=学分` 正式覆盖通道（contracts 从 P5.credits_overrides 注入） | rank/planner.py, harness/contracts.py, decisions.schema |
| `--must-take/--exclude` 多值被 argparse 覆盖（只留最后一个） | contracts step6 cmd 改为 `["--must-take", *values]` 单参数多值 | harness/contracts.py |
| EXT 选修配额 quota=1（AR `credits_mentioned` 未解析） | buckets 从 AR credits_mentioned 取学分 → quota（9 学分 → 3 门） | rank/buckets.py |
| 481X 系列（不同月份）被误判时间冲突 | conflict.py 日期窗口参与冲突判定（窗口不相交不冲突）；slot 升级 5 元组 | wcq/conflict.py, rank/planner.py, report/render_grid.py |
| diversity_swap 跨桶换课破坏配额（CC A 区换 T 区致双课） | 换入桶必须未满（配额硬约束） | rank/planner.py |
| wcq_full 抓 0 subject（`--session latest` 未解析） | crawler 新增 `latest_session()` 自动检测（cc_areas 同步受益） | wcq/crawler.py |
| SIS Pre-Enroll 抓取 NameError（`emplid` 未定义） | URL 去掉未定义变量（EMPLID 可选） | sis/parser.py |
| doctor cookie 汇总恒 FAIL（OK 行被当错误） | check_cookies 仅非 0 退出/失效状态才报告 | harness/doctor.py |
| minor 无处理 | buckets 收集+校验+提示（二期合并排课） | rank/buckets.py |
| **一年制课程无通用机制**（4291 学分靠用户口头说明+手改覆盖；其他全年课（如 IEDA 4960）无法识别） | 新增 `rank/year_courses.py` 全年课程检测（描述跨两学期语义：two regular terms/one year long/lasts for one year/fall and spring）；course_notes `year_long` tag → planner 自动 units/2 折算（手动 `--credits-override` 优先）；RUNBOOK/AGENTS 概念固化 | scripts/rank/year_courses.py, rank/planner.py, database/course_notes/*, docs/RUNBOOK.md |
| 无选课写入能力（最终方案需提交 admlu65.ust.hk） | 新增 `enroll/cart.py`（build 清单生成含 TBA 标注 / check 学期开放探测 / submit 人工确认提交流程）+ `enrollment-commit` skill 挂入 harness 收尾（可选）；admlu65 为 Microsoft SSO 选课入口，真实提交依赖用户会话与 SIS class_nbr（框架预留，人工确认） | scripts/enroll/cart.py, skills/enrollment-commit/SKILL.md, skills/harness/SKILL.md, docs/RUNBOOK.md |

配套：新增 `scripts/tests/unit/test_fixes_20260807.py`（11 例：P1 三字段/session 数字优先/学分覆盖/ext 顶点规则/ctx 传递）；全量单测 64 例通过；doctor 全绿。

## 2026-08-05（晚）— 全流程实测问题修复轮

| 问题 | 修复 | 文件 |
|---|---|---|
| Step 1 Note 语义无固化工具，AI 手写求值器踩方括号坑 | 新增 `note_eval.py`（OR/AND/圆方括号/any N of 表达式解析+求值）；复杂 Note 整桶满足判定改走表达式（只修 COMP 1991 实习不再误判 FYP 桶满足）；`buckets[].note_semantics` 固化表达式形状 | rank/note_eval.py, rank/buckets.py |
| Step 6 方案多样性失效（全必修换不了课，3 套全同） | phase2 取课按方案变体轮转（分数/CC 优先/按桶轮转）；换课失败降级 `vary_sections` 换不同 section 时段 | rank/planner.py |
| Step 2 EXCLUSION 未被利用（MATH 2411/2421 同排） | filter 解析 EXCLUSION → `exclusion` 字段 + `excluded_by_passed` 标记；planner 排课强制互斥检查（对已修/预选/已排） | rank/filter.py, rank/planner.py |
| pre_enrolled.json ↔ pre_enroll.schema.json 校验 SKIP | 单文件校验模式接入 FILE_SCHEMA 映射；planner 改读 confirmed/pending（旧 courses 兜底）；空文件不再触发"未匹配"噪音 | harness/schema_validate.py, rank/planner.py |
| 0 学分必修（COMP 1991）TBA 警告/占桶 | `zero_credit` 预标注：无时间 section 仅占位不占排课时间；必修先排时零学分靠后，同桶真实学分课先占配额 | rank/planner.py |

配套：schema 增加 `exclusion`/`zero_credit`/`note_semantics` 字段；新增单测
`test_note_eval.py`、`test_planner_fixes.py`（互斥/零学分/多样性/预选冲突）；
step1/step3/step6/must-take skill 同步固化。

## 2026-08-05 — 产品化改造（架构统一）

harness 从"AI 背文档执行"升级为"统一入口 + 合约驱动"：

- **新增 `scripts/ustplan.py` 统一入口**：init/doctor/start/status/resume/step/
  phase/job/plan/report/grid/decisions；AI 不再直接拼底层命令
- **新增 `scripts/harness/contracts.py`**：step/phase 合约表（输入 schema →
  命令 → 产物 schema → 摘要）；运行期状态（session/track/学分/豁免/硬插）从
  manifest/decisions 注入，消灭 skill 文档 17 处硬编码 `--session 2610`
- **新增 `config/ustplan.json`**：评分权重 A/B/C/D、热度档位、降权步长、TOP N、
  学分上下限、job 超时全部参数化（附 config.schema.json，doctor 校验）；
  `bucket_score.py` 改为读配置；评分公式纯函数抽取到 `scoring.py`（可单测）
- **新增运行状态**：`data/manifest.json`（run_id/产物 sha256/schema 版本）、
  `data/decisions.json`（P1-P5 用户决策审计 + 断点续跑依据）
- **schema 版本化**：全部 16 个 schema 加 `$id` + `version`，validator 输出版本
- **报告产品化**：`report/render.py` 按模板 `templates/reports/final_report.md.tpl`
  自动渲染机械段落（画像/未修/过滤/评分/方案/waiver），AI 只补口碑与建议；
  `report/render_grid.py` 周历（终端 ASCII + 单文件 HTML 导出）
- **测试**：新增 `scripts/tests/unit/`（39 例：评分公式边界/planner 硬约束/
  pre-req 解析/时间槽/合约/配置）；`test_runner.py --all` 一键跑单测 + 全部用例
- **文档**：README 拆分（快速开始 / docs/ARCHITECTURE / docs/RUNBOOK / CHANGELOG）；
  确认点统一编号 **P1-P5**（P1 凭证+major+track+学期 / P2 画像 / P3 未修+学分 /
  P4 过滤 / P5 方案），harness 时间线同步修正（原 P1-P4 与 step skills 编号矛盾）
- **环境清理**：清除测试/运行残留（data/output/cache/credentials/user 恢复空
  交付态，保留 README；__pycache__/Zone.Identifier 全清）
- 新增 `requirements.txt` 固定依赖；`doctor.py` 一键预检
- cookies 仍为明文文件（可后续升级 DPAPI 加密，接口已预留 --cookie-file 统一契约）

## 2026-08 — 脚本改进记录（bucket 化重构运行实测后）

| 问题 | 修复/改进 | 脚本 |
|---|---|---|
| 顶层脚本 ROOT 多跳一层 | `parents[2]` → `parents[1]` | cookies_setup.py |
| pre_enrolled.json 无 schema 映射 | FILE_SCHEMA 补录 | schema_validate.py |
| 4xxx 必修被低年级 CC 池挤出 Top-N | 废弃 Top50 → bucket 化并列评分（每栏位独立 TOP3） | rank/buckets, bucket_score.py |
| 旧学年 curriculum 缺失无回退 | --areas 过滤 + SIS AR 生成未修基架 | rank/ar_to_unmet.py |
| pre-req 需手工放回 removed | pre-req 不再删除 → 保留+标记+waiver 清单；--override 仍可用 | rank/filter.py |
| planner 丢必修；TBA 无法计学分 | 池强制含全部必修；TBA 计学分占位；--exclude 排除 | rank/planner.py |
| planner 固定三档、不响应学分 | --target-credits（默认 15）+ bucket 配额 + 低阶必修先排 + waiver_required[] | rank/planner.py |
| 排课只考虑 lecture | 组件型 section（L/T/LA/R 分组，每组件各选一节，L+T 都要） | rank/planner.py |
| curriculum 只有 2026-27 | 按入学年份预构建 2023-24/2024-25/2025-26；buckets.py 硬校验 admission_year | prog_crs/*, rank/buckets.py |
| 历史 CC 区域表只有 CC22 | 补齐 CC25/CC26；4Y 组确认无区域页走 SIS AR；cc_areas 防呆"页面=索引页" | wcq/cc_areas.py |
| review_summary 80 门逐条手写 | 自动基架（档位+今年导师+D 占位），AI 精读仅覆盖关键字段 | rank/review_summary_build.py |
| 产物统计靠临时命令 | 统一统计（未修/过滤/评论/口碑/评分/方案） | report/stats.py |
| session 手写 | `--session latest` 自动检测 | wcq/crawler.py |
| B 组件缺教授统计 | summarize 增加 instructor_stats + instructor_recent | ustspace/crawler.py |
| prog-crs OR 链解析残留 | OR 链续行识别；"N courses out of M" 配额解析；已修满足 → 整桶移除 | prog_crs/parser.py, rank/buckets.py |
| CC 区域满足性靠 AI 判断 | 全脚本化三层判定（AR 条目 + 历史区域表 + AR 组回退） | sis/parser.py, wcq/cc_areas.py, rank/buckets.py |
| track 限制需人工改桶 | note "can only use X" 自动解析限定桶内课程 | rank/buckets.py |
| 扩展主修需手工加桶 | EXTM-* curriculum 自动合并 + AR not_taken 过滤 | rank/buckets.py |
| SIS 抓取 NameError | Pre-Enroll URL EMPLID 置空 | sis/parser.py |
| 冗余 flag/死代码 | 清理 --schedule/--cc/--jsessionid 等与死函数 | sis/parser.py, rank/*, wcq/conflict.py |
