# AGENTS.md — 项目指令（opencode 自动加载）

## 本文件是做什么的

本文件是 AI 进入本仓库后的第一份指令：它说明本项目是什么、
AI 在其中扮演什么角色、以及遇到用户请求时必须遵循的完整工作流。
**规则冲突时，本文件优先于一般惯例。**

## 项目是什么

本仓库是「UST 自动选课 Agent」：基于我校排课流程的自动选课辅助工具，
由 **ustplan 统一入口**（`scripts/ustplan.py`）驱动——后台并行抓取、
checkpoint 强顺序、人工确认点、schema 校验、凭据隔离。
流程细节封装在 `skills/` 的流程 skill 中，AI 按 skill 调用，不临场发挥。

## 第一步：读 README

动手前**先读 `README.md`**：它包含快速开始（3 步）、ustplan 统一入口命令表、
完整流程与确认点、目录总览、文档导航。
更深层需要时再读 `docs/ARCHITECTURE.md`（架构设计）与 `docs/RUNBOOK.md`（排障）。

## 触发规则（固定）

用户意图为**选课 / 排课 / 课表 / 课程规划**相关（含"你好"后提及选课）时，
**立即**按以下固定流程执行，不等待用户明确说"开始"：

1. 加载 `harness` skill（主编排）并按其固定调用顺序执行；
2. t0 立即运行 `python3 scripts/ustplan.py start`（manifest 初始化 + 后台
   wcq_full 全量抓取；若已 start 则跳过）；
3. 按 phase1-input skill 的产品化模板收集输入。

## 完整工作流（固定调用顺序）

```
t0  用户首条消息 → ustplan start（manifest 初始化 + 后台 wcq_full 抓取）
phase1-input        → [P1] 两个登录令牌 + major + track + 目标学期（track 必填）
phase2-profile      → [P2] 画像确认 + 未修清单预览
phase3-course-analysis（checkpoint 容器，顺序不可调换）：
  step1 未修(bucket化) → step3 schedule 过滤 → step4 评论精读
  → step5 bucket 评分 → step6 课表编排
  → [P3] 未修清单确认 + 过滤结果展示（waiver/移除）+ 目标学分（一次问清）
  → 方案展示（P5 弱化：展示 N 套方案，用户要求修改才记录决策并重排）
phase4-report        → 报告即交付物（含选课时间提醒）
phase4.5-must-take   → 必选课询问（可选）
```

阶段推进：确认点通过后 `ustplan decisions set Pn ...` 记录决策 →
`ustplan phase done <phase>`（自动校验完成条件）；阶段间用
`ustplan phase begin <phase>` 开始（前置未完成即失败）。

## 确认点（固定 3 次，禁止额外中断）

- **P1**：两个登录令牌（SIS 的 PS_TOKEN、ust.space 的 ustspace_session）+ major + track
- **P2**：画像确认（SIS 权威 + 未修清单预览）
- **P3**：未修清单确认 + 过滤结果展示（waiver/移除）+ 目标学分（一次问清）

P4 过滤确认已并入 P3；P5 方案选择弱化为展示（用户主动要求修改才记录决策）。
除此之外的中间状态（step 完成、后台任务进度）**不向用户提问**，直接推进。

## 后台任务纪律（并行时间线）

- 每次向用户提问前：`python3 scripts/ustplan.py job start <job-id>` 启动所有
  依赖就绪、未在跑/未完成的任务；
- 每次用户回复后：先 `job status <job-id>` 检查全部任务，已完成直接利用产物；
- 网络抓取一律后台；本地秒级脚本（step1/3/5/6）同步跑；
- 等待抓取时告知"正在为你分析，稍等"，不静默。

## 产品化输出（每次 AI 输出必须遵守）

- 面向用户语言：不使用程序语言/文件名/命令，除非用户主动询问技术细节；
- 内容用简洁中文对话 + 表格呈现；后台脚本与产物用户不可见；
- 等待期间告知"正在为你分析，稍等"，不静默。

## 异常处理

全部异常场景按 `docs/RUNBOOK.md` §2 异常处理矩阵处理，禁止临场发挥。

## 一年制课程概念（固定认知）

描述含跨两学期语义的课程（"extended over two regular terms" / "one year
long" / "lasts for one year" / "fall and spring" 等）是**全年课程**：schedule
的 units 是全年总学分，每学期注册 = units/2（如 PHYS 4291：全年 6 → 每学期 3）。
遇到用户说明某课"每学期 X 学分"而课程数据为全年总量时，按全年语义核实描述
（`rank/year_courses.py --session <S>` 可检测候选）并写入
`database/course_notes/{SUBJ}.json` 的 `tags: ["year_long"]`，planner 自动折算；
**禁止直接修改抓取产物**（如 courses_*.json 的 units）。
