# 架构设计（ARCHITECTURE）

UST 课表自动选课 harness 的设计说明。核心思想：**流程正确性由代码保证
（合约/检查点/校验），AI 只做三件事——问用户、精读评论、写产品化文案**。

## 1. 三层结构

```
┌─ 表现层：opencode 对话（AI 输出产品化中文 + 表格）
│           skills/ 定义"该做什么"（触发时机/AI 职责/确认点）
├─ 编排层：scripts/ustplan.py（统一入口）
│           contracts.py（step/phase 合约表）→ 前置校验 → 命令 → 后置校验 → 摘要
│           checkpoint.py（阶段强顺序）· jobs.py（后台并行）· manifest.py（产物追踪）
│           decisions.py（确认点审计）· doctor.py（预检）
└─ 执行层：scripts/rank|wcq|sis|ustspace|prog_crs/（抓取/解析/打分/排课脚本）
```

- **合约（contracts.py）**：每个 step 定义 输入(含 schema) → 固定命令（参数从
  运行状态注入）→ 产物(含 schema) → 摘要。AI 只调 `ustplan step <N>`，
  不再从文档猜命令；**学期等运行期状态存 manifest/decisions，文档零硬编码**。
- **检查点（checkpoint.py）**：phase1 → phase2 → phase3 → phase4 → phase4.5，
  begin 校验前置已完成，done 校验完成条件（P 确认 + 产物合法）。
- **并行时间线（jobs.py）**：耗时抓取脱离进程后台运行；提问前 start、回复后
  status；超时自动击杀；孤儿（crashed）在重跑时自动清理。

## 2. 数据流（产物链，每步必须过 schema 才能进下一步）

```
WCQ 全量（courses_{session}.json, cc_courses_{session}.json）
  → step1 buckets.py       → data/unmet_courses.json    （bucket 化未修）
  → step3 filter.py        → data/filter_report.json    （今年开设/pre-req 标记）
  → USTspace 评论           → data/ustspace_reviews.json
  → step4 基架+AI 精读      → data/review_summary.json   （含 D 组件 d_rating）
  → step5 bucket_score.py  → data/course_scores.json    （每栏位 TOP3 + ranked_out）
  → step6 planner.py       → output/timetable_plan.json （N 套方案 + waiver_required）
  → phase4 render.py       → output/final_report.md     （机械段落自动，口碑/建议 AI 填）
  → 周历                   → output/timetable_{plan}.html
```

运行状态：
- `data/manifest.json`：run_id / session / 每产物 sha256 + schema 版本 + 产出任务
- `data/decisions.json`：P1-P5 用户回答（审计 + 断点续跑依据）
- `data/checkpoint.json`：阶段顺序

## 3. 评分公式（Step 5，参数全部来自 config/ustplan.json → scoring）

```
课程得分 = A + B + C + D                        （满分 100，可负分）
A = (课程四维均分 − baseline) / baseline × wA     # 均分<baseline 倒扣；新课 → 0
B = (本学期教授评分综合 − baseline) / baseline × wB
    教授评分综合 = Σ(维度均分 × 维度权重)
    本学期教授总评论数 < min_reviews：每缺 1 条降 weight_penalty_per_missing
    新教授（无评论）→ B=0
C = 评论热度档位（heat_tiers 降序命中；< min_reviews_for_score → 总分直接 0）
D = 本学期任课教授最近 5 条评论 AI 精读（0~25，来自 review_summary.d_rating）

major_required 低阶加分：level_bonus 按课号千位（1xxx +5% / 2xxx +3% / 3xxx +1%）
    （对当前总分，负分不乘）
```

纯函数实现 `scripts/rank/scoring.py`（可单测）；`bucket_score.py` 只做编排。
每栏位取 `top_per_bucket` 门（默认 3）；栏位之间**并列不混排**（防选重/选多，
配额由 planner 消费）；其余进 `ranked_out` 备选池（must-take/多样性换课用）。

## 4. Bucket 化未修（Step 1，2026-08 重构核心）

- 必修：一门一桶（quota=1）；必修 pool（OR 组）一个桶
- 选修：一个 pool 一桶（"2 courses out of 5" → quota=2）
- CC：一区域一桶（A/H/S/T/SA/SUS/HAIC/HMW/E-Comm/C-Comm/CTDL/UxOP…）
- 已修/预选课扣除（精确码匹配）；OR 池已修数 ≥ 配额 → 整桶移除
- 必修 pre-req 引用补录（`prereq_reference: true`，仅参考不排课）
- **CC 区域满足性全脚本判定**（三层）：历史 CC 区域表
  （`database/common-core/areas_{GROUP}.json`）→ AR 条目级 → AR 组级回退；
  AI 不做 CC 逻辑判断（曾看漏 S/SA 已修，已脚本化）
- track 限制（note "can only use X to fulfill"）自动生效；EXTM-* 扩展主修自动合并

## 5. Major curriculum 双来源（本地优先 + SIS AR 回退）

- 本地优先：SIS 专业名与 `database/curriculum/{admissionYear}/` 完全相符直接使用
  （无需联网）；不符/缺失时联网抓 prog-crs 比对（`scripts/prog_crs/README.md`）
- 入学年份硬规则：curriculum / Common Core 框架（4Y/CC22/CC25/CC26）/
  历史 CC 区域表全部按 `profile.admission_year` 决定（buckets.py 缺失即报错）
- AR 回退：2022-23 及更早 prog-crs 下线 → SIS Academic Requirements 作权威
  （`ar_to_unmet.py` 生成未修基架，复杂语义 AI 精读补全）
- **不预构建 course_catalog**：课程详情（pre-req）是动态数据，以运行时
  Class Schedule 页内联 PRE-REQUISITE 为准；单课详情按需
  `course_catalog.py --subject X --year Y` 临时查

## 6. 数据源分工

| 数据源 | 脚本 | 回答的问题 | 认证 |
|---|---|---|---|
| SIS | `sis/` | 学生现在修了什么、AR 进度、Pre-Enroll | PS_TOKEN（AI 禁碰） |
| WCQ Class Schedule | `wcq/crawler.py` | 今年开什么课/导师/Quota/pre-req | 公开 |
| WCQ 历史 CC 池 | `wcq/cc_areas.py` | 已修课属于哪个 CC 区域 | 公开 |
| prog-crs curriculum | `prog_crs/` | 专业要求什么（按入学年份预构建） | 公开 |
| USTspace | `ustspace/crawler.py` | 口碑/热度/导师 | ustspace_session |

## 7. 一致性保证（R1-R6）

| 规则 | 手段 |
|---|---|
| R1 只读完整性 | `hash_check.py`：skills/database/templates/user/scripts/opencode.json 快照比对 |
| R2 产物合规 | `schema_validate.py`：每产物过 schema（含版本号） |
| R3 凭据隔离 | AI 禁读 cookie 明文；产物不得含凭据值；测试用 mock cookie |
| R4 阶段顺序 | `checkpoint.py`：跳阶段即失败 |
| R5 幂等可续 | testcase 两次运行产物一致（去时间戳） |
| R6 环境隔离 | testcase 在隔离副本运行，真实只读集不受影响 |

验证入口：`python3 scripts/harness/test_runner.py --all`
（单测 + demo/rank 用例全部 R1-R6 断言）。
