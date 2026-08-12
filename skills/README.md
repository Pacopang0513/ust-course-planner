# skills/

流程 skills 目录（按调用顺序组织）。统一五段式：**触发 → 执行（ustplan）→
AI 职责 → 确认点 → 交接**。命令一律走 `scripts/ustplan.py`，产物校验由合约自动完成。

当前已有（按调用顺序）：

- `harness` 主编排（固定顺序 + 确认点 P1-P3（P4 并入 P3、P5 弱化为展示）+ 后台任务纪律 + 异常矩阵指引）
- `phase1-input` Phase 1（t0 ustplan start + 后台 wcq；P1 凭证 + major + track + 学期）
- `phase2-profile` Phase 2（SIS 权威画像 + 后台并行；P2 画像 + 未修预览）
- `step1-unmet-calculation` Step 1（bucket 化未修；CC 满足性全脚本三层判定；P3 未修 + 学分 + 过滤结果同回合展示）
- `step3-schedule-filter` Step 3（今年开设过滤；pre-req 只标记 → waiver；过滤结果并入 P3 展示）
- `step4-review-analysis` Step 4（USTspace 评论精读；基架 + AI 覆盖 + D 组件；--finalize）
- `step5-score-fusion` Step 5（Bucket 评分 A+B+C+D，参数在 config/ustplan.json）
- `step6-timetable-planning` Step 6（目标学分编排 + L+T 组件 + waiver 清单；方案展示，P5 弱化）
- `phase4-report` Phase 4（模板渲染机械段落 + AI 补口碑/建议 + 选课时间提醒）
- `enrollment-dates-reminder` 选课时间提醒（报告末尾固定模板）
- `must-take-course-insertion` Phase 4.5 强制选课（ustplan plan --must-take 硬插重排）
- `web-crawl-guide` 联网抓取规范（URL 模板/cookie/缓存约定参考；执行走 ustplan job）

**确认点（P1-P3，question 工具内联提问，不截断流程）**：关键信息点统一用
question 工具结构化提问（选项 + 自由回答；opencode UI 在思维过程中暂停展示，
用户作答后同一轮对话内继续推进）——P1 凭证+major+track+学期 / P2 画像 /
P3 未修+学分+过滤结果，一次问清；P4 并入 P3，P5 方案弱化为展示。
无确认不得推进 checkpoint；确认后写 `ustplan decisions set Pn ...` 并
`ustplan phase done <phase>`。
**后台计算与用户回答并行**（提问前 job start，回复后 job status），不互相阻塞。

- 写入者：开发阶段人工维护
- 权限：AI 读取调用
- gitignore：否（跟踪）
