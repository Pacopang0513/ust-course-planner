---
name: phase1-input
description: Phase 1 输入准备。确认前置条件（credentials/cookies、user 资料、SIS 可用性、目标学期）并初始化 data/checkpoint.json（phase1 检查点），输出目标学期与 session 代码。Use when starting the course planning run.
---

# Phase 1 — 输入准备

## 目的

正式流程的第一步：确认所有前置输入齐备、确定目标学期，并启动检查点链
（R4 阶段顺序由此开始）。

## 前置检查清单（逐项确认，缺一即停）

| 项 | 要求 | 不满足时的处理 |
|---|---|---|
| `credentials/cookies.txt` | `python3 scripts/cookies_setup.py --check` 输出 **SIS 与 USTspace 均 OK** | 引导用户运行 `scripts/cookies_setup.py`（交互粘贴，自动验证；`--print-bookmarklet` 可一键复制） |
| `user/` | major 手册 / CC 资料（如有则参考） | 可选，缺省用 database/ 预构建 |
| `cache/sis/sis_course_history.json` | SIS 已抓取（或本次 phase2 抓取） | 交由 phase2 执行 `sis/parser.py --fetch` |
| 目标学期 | 用户指定（如 2026-27 Fall）或默认"下一学期" | 询问用户 |
| `database/build.json` | 目标入学年份已预构建 curriculum | 未构建 → `scripts/prog_crs/build.py --year {admission_year}` |

## 目标学期 → session 代码（固定映射）

| 学期 | session 后缀 | 示例 |
|---|---|---|
| Fall | `{YY}{YY+1}0` | 2026-27 Fall → `2610` |
| Winter | `{YY}{YY+1}5` | 2026-27 Winter → `2615` |
| Spring | `{YY}{YY+1}20` | 2026-27 Spring → `2620` |
| Summer | `{YY}{YY+1}30` | 2026-27 Summer → `2630` |

（YY = 学年首两位；wcq 页面同一学期下拉可核对）

## 确认点 P1（强制中断）— cookie 预检 + 目标学期确认

**AI 在 begin phase1-input 后必须暂停，等待用户动作，不得直接 done：**

1. **cookie 预检**（AI 不读明文，只跑脚本看状态）：
   ```bash
   python3 scripts/cookies_setup.py --check
   ```
   - 输出 **SIS (PS_TOKEN) [OK]** 与 **USTspace (ustspace_session) [OK]** → 通过
   - 有 `MISSING / EXPIRED` → 告知用户运行 `python3 scripts/cookies_setup.py`
     （交互引导：粘贴 cookie → 自动写入并验证；`--print-bookmarklet` 可获取
     "登录页点一下复制到剪贴板"的书签代码；只需重贴失效的键）
   - 等用户完成后重跑 `--check`，两项全 OK 才继续
2. **目标学期确认**（用户确认）：
   - 展示：目标学期、session 代码（固定映射表）、`database/build.json` 预构建状态
   - 说明：CC 入学年份组（4Y/CC22/CC25/CC26）依赖入学年份，将在 **P2 画像确认**
     时一并确定（phase1 时 admission_year 尚未从 SIS 提取）
   - 用户确认或修改后，把确认结果写入本阶段临时说明

**未完成上述两项确认，不得 `checkpoint.py done phase1-input`。**

## 执行（固定）

```bash
# 初始化/重置检查点（首次运行或新任务）
python3 scripts/harness/checkpoint.py reset
python3 scripts/harness/checkpoint.py begin phase1-input
# → 确认点 P1：等用户提供 cookie + 确认目标学期（见上节）
# ... 完成前置确认后
python3 scripts/harness/checkpoint.py done phase1-input
```

确认结果写入本阶段临时说明（供用户核对）：目标学期、session 代码、
预构建状态。CC 入学年份组（admission_year → 4Y/CC22/CC25/CC26）在 P2 与画像一并确认。

> 中断恢复：任意确认点/阶段可随时中断；重跑时先 `checkpoint.py status` 查看进度，
> 从进行中的阶段继续（`begin` 已完成阶段允许重入）。

## 交接

- 目标学期 + session 代码 → phase2（画像）与各 step（wcq session 参数）
- 检查点 `phase1-input` done → phase2-profile 可 begin
