# scripts/tests/ — Testcase 目录

每个 testcase 一个子目录，由 `scripts/harness/test_runner.py` 驱动：

```
<case>/
├── run.py                  # 必选：模拟/驱动被测流程（cwd = 隔离副本根目录）
└── fixtures/
    ├── cookies.txt         # 可选：mock cookie → 副本 credentials/cookies.txt
    └── user/*              # 可选：mock 用户输入 → 副本 user/
```

约束（实现见 `scripts/harness/test_runner.py`，全部规则必须通过）：
- R1 只读完整性 — 副本与真实项目只读集（skills/database/templates/user/scripts/opencode.json）哈希前后一致
- R2 产物合规 — data/ output/ 产物及 database/ 预构建 JSON 过 templates/schemas/ 校验
- R3 凭据隔离 — 真实 credentials/ 不被触碰；mock 值不泄漏到产物
- R4 阶段顺序 — checkpoint 链完整（phase1→phase2→phase3→phase4→phase4.5）；跳阶段负向用例必须失败
- R5 幂等可续 — 两次运行产物（去时间戳）一致
- R6 环境隔离 — 运行在临时副本，真实项目不受影响

## 现有用例

- `demo/` — 产品化全流程用例：模拟 phase1→phase4.5，写 schema 合规产物；
  `--tamper` 可演示 R1 失败
- `rank/` — 旧打分链数据用例（unmet → local 打分 → filter 过滤 → 评论 → final
  合成排名）；该链为历史实现，产品化流程（step1/3/4/5/6，见 contracts.py）不消费
- `unit/` — 单测：评分公式边界 / planner 硬约束 / note_eval / pre-req 解析 / 合约 / 配置
