---
name: harness
description: 主编排 skill。固定调用顺序 phase1-input → phase2-profile → step1→step3→step4→step5→step6（承载于 phase3-course-analysis）→ phase4-report → phase4.5-must-take；确认点 P1-P3 强制中断（P4 并入 P3、P5 弱化为展示）；后台任务纪律（提问前 start，回复后 status）；异常处理见 docs/RUNBOOK.md。Use when orchestrating the full course planning flow.
---

# Harness — 主编排

## 产品化输出总则（每次 AI 输出必须遵守）

- 面向用户语言：不使用程序语言/文件名/命令，除非用户主动询问技术细节；
- 内容用简洁中文对话 + 表格呈现；后台脚本与产物用户不可见；
- 等待期间告知"正在为你分析，稍等"，不静默；
- **只问 3 次**：① 登录令牌 + major/track；② 画像确认；③ 目标学分。
  其余（过滤结果/方案）随以上确认点顺带展示，不单独中断。

## 固定调用顺序（R4 checkpoint 链 + 确认点 P1-P3）

```
t0  用户首条消息 → ustplan start（manifest 初始化 + 后台 wcq_full 抓取）
phase1-input        → [P1] 两个登录令牌 + major/minor/extended_major（三状态：代码/NA，全必填）+ track + 目标学期
phase2-profile      → [P2] 画像确认 + 未修清单预览
phase3-course-analysis（checkpoint 容器）：
  step1 未修(bucket化) → step3 schedule 过滤 → step4 评论精读
  → step5 bucket 评分 → step6 课表编排
  → [P3] 未修清单确认 + 过滤结果展示（waiver/移除）+ 目标学分，一次问清
  → 方案展示（P5 弱化：展示 N 套方案，用户可要求修改，不强制中断）
phase4-report        → 报告即交付物（含选课时间提醒）
phase4.5-must-take   → 必选课询问（可选）
enrollment-commit    → 选课写入（可选）：方案确认后询问是否写入 admlu65.ust.hk；
                      学期开放检查 → 清单生成（TBA 标注）→ 用户人工提交
```

**确认点（P1-P3，强制中断）**：各 skill 的"确认点"小节规定展示内容；
无用户响应禁止 `phase done` 推进。确认点交互统一用 question 工具结构化收集
（选项含 NA 与自定义输入，不临场组织长文本），后台任务运行期间用户可并行
作答。P4 过滤确认已并入 P3（同回合展示）；
P5 方案选择弱化为展示——方案生成后直接展示，用户主动要求修改时才记录
决策并重排。后台任务不阻塞确认：提问前已 start 的任务在用户答复期间运行，
答复时先 status 取结果（并行时间线）。

**推进方式**：每个确认点通过后 `ustplan decisions set Pn ...` 记录决策 →
`ustplan phase done <phase>`（自动校验完成条件）；阶段间用
`ustplan phase begin <phase>` 开始（前置未完成即失败）。

## 后台任务纪律（并行时间线）

- **每次向用户提问前**：`ustplan job start <job-id>` 启动所有依赖就绪、
  未在跑/未完成的任务（已在跑/已完成会拒绝，`--force` 覆盖重跑）；
- **每次用户回复后**：先 `ustplan job status <job-id>` 检查全部任务，
  已完成直接利用产物（自动收录 manifest），未完成继续跑（不阻塞对话）；
- 网络抓取一律后台（wcq/SIS/USTSPACE）；本地秒级脚本（step1/3/5/6）同步跑；
- 需要结果才能继续时：`ustplan job wait <job-id>`（配"正在为你分析，稍等"）；
- job 清单/超时/孤儿清理见 `docs/RUNBOOK.md` §1。

## 阶段 ↔ 检查点对照

| 检查点 | 执行的 skills | 确认点 | 主要产物 |
|---|---|---|---|
| phase1-input | phase1-input | P1 | manifest/decisions（P1） |
| phase2-profile | phase2-profile | P2 | profile/passed_courses/pre_enrolled |
| phase3-course-analysis | step1→step3→step4→step5→step6 | P3（含过滤展示）+ 方案展示 | unmet/filter/review_summary/course_scores/timetable_plan |
| phase4-report | phase4-report + enrollment-dates-reminder | — | final_report.md |
| phase4.5-must-take | must-take-course-insertion | 用户指定课程 | 调整后 timetable_plan（可选） |
| enrollment-commit | enrollment-commit（可选） | 用户同意写入 | enroll_cart.json + 人工提交流程 |

## 校验（每阶段收尾执行）

```bash
python3 scripts/ustplan.py step <N>        # 合约已内置前后置校验 + schema
python3 scripts/harness/schema_validate.py --dir data --dir output   # 兜底全量
```

全流程完成后再跑 R1-R6（`python3 scripts/harness/test_runner.py --all`，
含单测；可选——正常运行的产物合规由阶段内校验保证）。

## 异常处理

全部异常场景的固定处理见 **`docs/RUNBOOK.md` §2 异常处理矩阵**（cookie 失效 /
后台失败 / curriculum 缺失 / track 未指定 / 学分越界 / 冲突 / schema 失败），
按表处理，禁止临场发挥。
