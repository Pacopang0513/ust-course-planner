---
name: phase1-input
description: Phase 1 输入准备。t0 立即 ustplan start（manifest + 后台 wcq 抓取）；产品化模板收集 2 个登录凭证 + major/minor/extended_major（三状态：代码/NA，全部必填）+ track（必填）+ 目标学期确认；预检通过后 done。Use when starting the course planning run.
---

# Phase 1 — 输入准备

## 触发

- t0：用户首条消息即执行 `ustplan start`（若已 start 则跳过）；
  若用户中途进入，先 `ustplan status` 检查运行状态。

## 执行（ustplan）

```bash
python3 scripts/ustplan.py start                 # 新运行 + 后台 wcq_full（--session latest）
python3 scripts/ustplan.py doctor                # 环境预检（cookie 状态等）
python3 scripts/ustplan.py job status wcq_full   # 用户回复后查抓取进度
```

- wcq_full 完成后 session 自动检测并写入 manifest（`job status/wait` 时自动收录），
  P1 需与用户确认目标学期。

## AI 职责

1. 首次输出（固定产品化模板，无程序语言）：
   - 问候 + 说明：可以帮你排下学期的课；
   - 要**两个登录令牌**：SIS 的 **PS_TOKEN** 与 ust.space 的 **ustspace_session**
     （登录对应网站后复制粘贴即可；明文仅用于本次抓取，不会读取显示）——
     直接给令牌名字，验证结果只反馈 OK/失效/缺失；
   - 要**程序三字段**（防漏读，全部必填，三状态：填入课程代码 / NA=没有 /
     空置不通过）：
     - **major**（第一主修，必填）
     - **minor**（副修；没有填 NA）
     - **extended_major**（扩展主修；没有填 NA）
     - 课程代码选项可从本地 curriculum 即时提取（database/curriculum/{入学年}/）；
       本轮交互用结构化问题收集（question 工具，选项含 NA 与自定义输入），
       不临场组织长文本；
   - 要 **track**（track 必填，影响必修/选修范围）；
   - 告知已在后台整理本学期课程数据。
2. 用户回复后（固定动作，禁止读文档/代码探索）：
   a. 把用户给的两个令牌写入 `credentials/cookies.txt`（两行，AI 不打印明文）：
      ```
      PS_TOKEN=<用户给的 SIS 令牌>
      ustspace_session=<用户给的 ust.space 令牌>
      ```
      令牌若带 URL 编码（如 `%3D`）先还原为原值；无需手工验证格式，
      写入后统一由脚本校验；
   b. `python3 scripts/ustplan.py doctor` 复查 cookie（输出 OK/失效/缺失）；
   c. `python3 scripts/ustplan.py job status wcq_full` 取 session 并展示确认。
   异常（cookie 失效/网络不可达）按 RUNBOOK §2 引导重贴，不猜测、不重复探索。
3. **记录到 decisions 时三字段必须齐全**：`major`/`minor`/`extended_major`
   一律显式写入（无则 `"NA"`）；缺任一字段 `phase done phase1-input` 会被
   contracts 校验拦截（空置不通过）。

## 确认点 P1（强制中断）

- 前置：两个凭证预检 OK + major/minor/extended_major 三字段齐备（代码或 NA）
  + track 给出 + 目标学期确认
- 记录：`ustplan decisions set P1 major=... minor=... extended_major=... track=... session=... semester=...`
- 推进：`ustplan phase done phase1-input`
- 期间后台任务持续运行，不阻塞；异常按 RUNBOOK §2（cookie 失效引导重贴）。

## 交接

P1（manifest session + decisions.major/minor/extended_major/track）→ phase2-profile
及全部 steps（profile.programs 同步写入三字段，minor=NA 时置空数组）。
phase1 done 后 phase2 可 begin。
