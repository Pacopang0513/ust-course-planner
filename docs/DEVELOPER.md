# UST 课表 — 自动选课 Agent（开发者文档）

> 本文件由原 `README.md` 迁移而来（2026-08），内容面向**开发者**（命令表、
> 目录结构、schema 校验等）；面向学生用户的使用说明见根目录 `README.md`。

基于我校排课流程的自动选课辅助工具（opencode skills + Python 脚本混合实现），
由 **ustplan 统一入口**驱动：后台并行抓取、checkpoint 强顺序、人工确认点、
schema 校验、凭据隔离。

## 快速开始（3 步）

```bash
# 1. 装依赖
python3 -m pip install -r requirements.txt

# 2. 初始化 + 预检（doctor 只报状态，不接触明文）
python3 scripts/ustplan.py init
python3 scripts/ustplan.py doctor          # 依赖/配置/cookie/database/schema 全查

# 3. 开始新一轮运行（先收集 P1 输入，令牌预检 OK 后才后台抓取 WCQ 全量）
#    AI 按 phase1-input 模板收集 P1 → 令牌写入 + doctor 预检 OK → 才执行下面命令
python3 scripts/ustplan.py start
# 之后按确认点 P1→P3 逐项与 AI 确认即可；断点续跑用 `ustplan status / resume`
```

> Windows：命令统一写 `python3`，Windows 用 `python`（或 `py`）代替。

## 统一入口（AI 与用户共用，不再直接拼底层命令）

| 命令 | 作用 |
|---|---|
| `ustplan.py init / doctor` | 环境初始化 / 预检 |
| `ustplan.py start / status / resume` | 开始运行 / 总览（阶段+任务+产物+决策+下一步）/ 断点续跑建议 |
| `ustplan.py step <step1/3/4/5/6> [--finalize]` | Step 合约执行（前置校验→命令→后置校验→摘要） |
| `ustplan.py phase begin/done <phase>` | 阶段推进（确认点通过后，含数据检查） |
| `ustplan.py job start/status/wait/clean <job-id>` | 后台任务（并行时间线，超时/孤儿自动处理；`wcq_history` = 前两学期课表抓取，step5 后启动） |
| `ustplan.py plan [--must-take …] [--target N]` | 重排（硬插/备选/学分覆盖，自动记录决策） |
| `ustplan.py report [--plan plan-N]` | 渲染 final_report.md（机械段落自动填） |
| `ustplan.py grid [--plan 1] [--html]` | 课程表周历（终端 ASCII / 单文件 HTML 导出） |
| `ustplan.py decisions set/show` | 用户决策日志（P1-P5 审计；`set` 支持 `--value-file <json>` 读文件，绕开 shell 引号） |
| `sis/build_profile.py` | Phase 2 画像基架（course_history → profile/passed_courses，机械转换固化） |
| `rank/cc_status.py` | CC 区域满足性核查（已修/未修 + Broadening 12 学分 4 区域） |
| `rank/history_compare.py` | Step 5.5 历史学期教授对照（前两学期开课 + 授课教授口碑 → 降权与延后建议） |
| `rank/review_scope.py` | Step 4 精读范围（必修全读 + 其余按评论数 TOP N）→ scope + digest |

## 流程与确认点（P1-P3，question 工具内联提问；P4 并入 P3、P5 弱化为展示）

```
P1 输入收集 → 令牌预检 OK → start → 后台 wcq 全量抓取（--session latest）
phase1-input   [P1] 两个登录凭证 + major + track + 目标学期
phase2-profile [P2] 画像确认 + 未修清单预览（后台 SIS/USTSPACE 并行）
phase3-course-analysis（step1 未修(bucket化，含副修合并) → step3 过滤 → step4 评论精读
  → step5 bucket 评分 A+B+C+D → step5.5 历史学期教授对照（后台 wcq_history 抓取
  前两学期课表，缺失优雅降级）→ step6 课表编排）
               [P3] 未修清单确认 + 目标学分 + 过滤结果（一次问清）
               [P5 弱化] 方案展示（用户要求修改才记录决策并重排）
phase4-report  最终报告（含选课时间提醒）→ phase4.5-must-take 必选课（可选）
```

- 后台任务不阻塞确认：提问前 `ustplan job start`，用户回复后 `status` 取结果；
- 无确认不推进 checkpoint（`ustplan phase done` 会校验完成条件）；
- 全部参数（评分权重/TOP N/超时/学分上下限）在 `config/ustplan.json`，改配置即改行为。

## 目录总览

| 目录 | 用途 | git |
|---|---|---|
| `config/` | 统一产品参数（评分权重/超时/默认学分） | 跟踪 |
| `user/` | 用户输入资料（major 手册、CC Curriculum） | 忽略 |
| `credentials/` | cookie 凭据（AI 不可读） | 忽略 |
| `database/` | Agent 统一数据库（政策/CC/curriculum 预构建） | 跟踪 |
| `skills/` | 流程 skills（harness → phase1/2/4 → step1-6） | 跟踪 |
| `scripts/` | Python（ustplan 入口/抓取/解析/打分/合约/校验/统计） | 跟踪 |
| `cache/` | 原始抓取缓存 | 忽略 |
| `data/` | 运行时个人产物（交付态为空，真实运行从 phase1 重建） | 忽略 |
| `output/` | 课程总结、课程表方案、周历 HTML | 忽略 |
| `templates/` | 产物 schema（版本化）+ 报告模板 | 跟踪 |
| `docs/` | 架构设计与排障手册 | 跟踪 |

## 文档导航

- 架构设计（并行时间线/评分公式/bucket 化/数据源分工）：`docs/ARCHITECTURE.md`
- 排障（异常矩阵/后台任务表/常见问题）：`docs/RUNBOOK.md`
- 变更记录：`CHANGELOG.md`
- 脚本索引（开发调试视角，底层命令）：`scripts/README.md`
- 流程 skills 索引：`skills/README.md`（各 skill 详见 `skills/*/SKILL.md`）
- 联网抓取规范：`skills/web-crawl-guide/SKILL.md`
