# 变更记录（CHANGELOG）

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
