# AGENTS.md — 项目指令（opencode 自动加载）

## 本文件是做什么的

- AI 进入本仓库的第一份指令：项目是什么、AI 角色、必须遵循的完整工作流。
- **规则冲突时，本文件优先于一般惯例。**

## 项目是什么

- 「UST 自动选课 Agent」：基于我校排课流程的自动选课辅助工具。
- 由 **ustplan 统一入口**（`scripts/ustplan.py`）驱动：后台并行抓取 / checkpoint
  强顺序 / 人工确认点 / schema 校验 / 凭据隔离。
- 流程细节封装在 `skills/` 的流程 skill 中：AI 按 skill 调用，不临场发挥。

## 第一步：读 README

- 动手前先读 `README.md`（学生用户：简介/使用说明/工作流）与
  `docs/DEVELOPER.md`（开发者：快速开始 3 步 / 命令表 / 流程与确认点 /
  目录总览 / 文档导航）。
- 更深层需要时再读 `docs/ARCHITECTURE.md`（架构设计）与 `docs/RUNBOOK.md`（排障）。

## 触发规则（固定）

用户意图为**选课 / 排课 / 课表 / 课程规划**相关（含"你好"后提及选课）时，
**立即**按以下固定流程执行，不等待用户明确说"开始"：

1. 加载 `harness` skill（主编排）并按其固定调用顺序执行；
2. 先按 phase1-input skill 的产品化模板**收集 P1 输入**（专业字段 + 登录
   令牌/获取方式），不等待用户明确说"开始"；
3. 用户作答、令牌预检（doctor）OK 后，才运行 `python3 scripts/ustplan.py
   start`（manifest 初始化 + 后台 wcq_full 全量抓取；若已 start 则跳过），
   再记录 P1 决策推进。

## 完整工作流（固定调用顺序）

```
t0  用户首条消息 → 先收集 P1 输入（专业字段 + 令牌方式）→ 令牌预检 OK 后
    ustplan start（manifest 初始化 + 后台 wcq_full 抓取）
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

## 确认点（固定 3 次，question 工具内联提问，不截断流程）

- 交互机制：AI 在流程思维到达关键信息点时，用 **question 工具**结构化提问
  （选项 + 自由回答；opencode UI 在思维过程中暂停展示问题，用户作答后**同一轮
  对话内继续推进**，不依赖用户另开回合、不做流程截断等待）。
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

## 特殊规则知识库（固定认知）

选课/学分存在大量"就事论事"的特殊规则，**每次流程 AI 必须过一遍**
`database/course_notes/`（含全局 `RULES.json` 与分 subject 文件）再决策，
禁止凭常识臆断：

| 规则 | 内容 | 消费方 |
|---|---|---|
| `year_long` 全年课程 | schedule units 为全年总学分，每学期注册 = units/2（PHYS 4291：全年 6 → 每学期 3） | planner 自动折算 |
| `h_course_equivalence` Honors 等价 | COMP 2012H = COMP 2011 + COMP 2012 组合替代（5 学分 vs 8 学分，差额需自由选修补足 120）；2711H/3111H/3711H = 单门升级等价 | note_eval + planner EXCLUSION |
| `double_count` 双主修 | 课程可同时计入两个主修，但 additional major 至少 20 学分 single-counted（COSC 2023-24）；未修学分统计会因 double count 高估，P3 展示说明，以 AR 学位审计为准 | P3 展示 |
| `ext_capstone_pairing` | EXT 顶点 4990/4991 选择取决于主修是否含 major_capstone（如 PHYS 4291） | buckets 规则消费 |
| `grading_prereq` | pre-req 可含成绩要求（如 PHYS 1314 要求 PHYS 1312 达某成绩），不达标需 waiver | filter 运行时解析 + step6 waiver |
| `major_capstone` | 主修顶点课程标记（4291/4191 等） | 触发 EXT 顶点规则 |

**新增规则流程**：发现新的特殊规则 → 上网核实官方来源 → 写入
`database/course_notes/{SUBJ}.json` 或 `RULES.json`（rules[] 带机器可读 logic）
→ 需要脚本消费的同步实现，禁止只写文档不消费。

## 预选课（Pre-Enroll）概念（固定认知）

- 学校为部分学生（尤其低年级）预选课程（SIS Enrollment Summary 页，
  Confirmed/Pending 两档）。预选课视为**已确定**。
- sis_fetch job 自动抓取并同步写 `data/pre_enrolled.json`
  （`cache/sis/sis_pre_enroll.json` 同构）；未到预选季时为空列表，属正常；
  **注意 SIS 页面 term 为会话默认学期**——若与目标学期不符，预选课不视为
  目标学期固定选课（ustplan 会 WARN，P2 需核对）。
- step1 不重复推荐（计入已确定）；step5 评分按 `pre_enroll_boost` 加权
  （config → scoring，默认 +40%，可追溯进 score_reason）；step6 视为固定选课
  （占用其 section 时段、不重复入排）。
- 若预选课即便加权后优先级仍很低（低于方案已选最低分），输出
  pre_enroll_advice 建议 drop；**必修预选课（major_required，如 FYP）不提示
  drop**。须提前告知学生风险：学校一般不建议 drop 预选课，坚持 drop 需申请
  waiver，且可能影响下学期预选资格。

## 一年制课程概念（固定认知）

- 描述含跨两学期语义（"extended over two regular terms" / "one year long" /
  "lasts for one year" / "fall and spring" 等）的课程是**全年课程**：schedule
  units 为全年总学分，每学期注册 = units/2（如 PHYS 4291：全年 6 → 每学期 3）。
- 检测：`rank/year_courses.py --session <S>`；确认后写入
  `database/course_notes/{SUBJ}.json` 的 `tags: ["year_long"]`，planner 自动折算
  （`--credits-override` 手动覆盖优先）。
- 用户口头说明"每学期 X 学分"而课程数据为全年总量时，按全年语义核实后落盘；
  **禁止直接修改抓取产物**（如 courses_*.json 的 units）。
