---
name: enrollment-commit
description: 选课写入（Enrollment Commit）。工作流收尾：用户确认最终方案并订好时间表后，询问是否写入 admlu65.ust.hk 选课系统；学期开放检查 → 生成选课清单（TBA 课标注不可提交）→ 人工确认提交流程。Use when finalizing the timetable plan and the user wants to enroll the courses.
---

# Enrollment Commit — 选课写入

## 触发

- phase4.5-must-take 之后（或方案最终确认后），向用户提供"写入课表"选项；
  用户同意才执行本 skill（选课是高风险操作，全程人工确认）。

## 概念

- 选课系统：`https://admlu65.ust.hk/`（HKUST 选课入口，Microsoft Entra ID
  SSO 登录）。登录后的 Shopping Cart / Enrollment 页（PeopleSoft
  `SSR_SSENRL_CART.GBL`）用于加入课程并提交。
- **学期开放**：目标学期（如 2610 = 2026-27 Fall）未到开放期时 Shopping Cart
  不可用。26-27 Fall 通常 8 月中下旬开放（以学校通知为准）；未开放 → 告知
  等待，不做无谓尝试。session 代码与真实学期对应，真正运行时取用户目标学期
  （本次方案为 2610）；测试可用历史/其他 session 验证流程。
- **TBA 课程不可提交**：上课时间未公布的课程（如 PHYS 4291）无法写入，
  需等 Class Schedule 更新后补选。
- **最终提交由用户人工确认**：脚本只生成清单与引导（自动提交依赖 SIS Class
  Search 的 class_nbr 会话，框架预留；未验证前不代提交）。

## 执行（ustplan）

```bash
python3 scripts/enroll/cart.py check --session <S>     # 可达性探测（未开放/维护会提示）
python3 scripts/enroll/cart.py build --plan output/timetable_plan.json \
    --plan-id <plan-N> --session <S>                   # 方案 → 选课清单
python3 scripts/enroll/cart.py submit --session <S>    # 提交引导（需 admlu_session）
```

- admlu65 会话 cookie：用户浏览器登录后复制，写入 `credentials/cookies.txt`
  的 `admlu_session=<值>` 行（可选键；AI 不接触明文，只反馈有无）。
- 输出：`output/enroll_cart.json`（清单，含 TBA 标记）。

## AI 职责

1. 方案确认后询问：是否现在写入选课系统？（产品化措辞；用户可能选择
   等学期开放/先不写）
2. 同意后先 `check`：可达 → 展示学期开放注意事项；不可达 → 提示未开放/维护，
   建议等通知，不重复尝试；
3. `build` 生成清单并展示（表格：课程/时段/学分/TBA 标记）；
4. `submit` 引导：缺 `admlu_session` → 引导用户复制会话 cookie（不打印明文）；
   含 TBA → 提示等时间公布；就绪 → 展示核对清单与 Shopping Cart 入口，
   **用户自行在浏览器完成最终提交**；
5. 提交后提醒：在 SIS 确认 Enrollment 状态；冲突/失败按 RUNBOOK §2 处理。

## 确认点

- 无独立确认点；唯一强制：**提交动作由用户人工执行**，AI 不代提交。

## 交接

- 产物：`output/enroll_cart.json` → 供用户在 Shopping Cart 核对。
- 记录：用户在 P5 决策中追加 `enroll_intent: true/false`（可选，审计用）。
