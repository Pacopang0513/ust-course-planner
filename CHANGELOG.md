# 变更记录（CHANGELOG）

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
