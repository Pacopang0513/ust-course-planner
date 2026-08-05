# scripts/mapper/ — AR↔curriculum 映射

把 SIS Academic Requirements 的**未满足条目**映射到 prog-crs 预构建的候选索引，
给出"这一项还能选哪些课"。语义判断（布尔 OR/AND、计数、条件、track 归属）不在本层，
由 phase3 AI 结合画像解释。

## 用法

```bash
python3 scripts/mapper/run.py --program PHYS \
    --intake-year 2026-27 \
    --ar cache/sis/sis_academic_req.json \
    --output data/mapping_result.json
```

产物：`data/mapping_result.json`（entries / cc_items / unmapped，含置信度）。

## 策略链（按优先级）

| 优先级 | 策略 | 置信度 | 说明 |
|---|---|---|---|
| 1 | override | explicit | `database/mappings/{PROG}.json` 人工/数据规则 |
| 2 | code-intersection | high | AR 相关课程 ∩ curriculum 组课程（含 subject 前缀匹配） |
| 3 | text-match | medium | AR 组名/描述 与 组 note/节名 词重叠（带节类型提示） |
| 4 | structural | low | 按 AR 组序对同节类型条目 |
| 5 | fallback | unmapped | 进 `unmapped` 清单，需人工确认 |
| — | CC 分流 | — | 纯分布要求（Arts/Science/English/Legal）→ `cc_items`，走 database/common-core/ |

## 可扩展性（每系方言）

- **默认通用策略覆盖 90%**：物理系 v1 全通
- **每系 override 文件**：`database/mappings/{PROG}.json`（schema: `templates/schemas/mapping_overrides.schema.json`），新系只需加数据
- **代码插件逃生舱**：非常规系（如 GCS）可加 `scripts/mapper/{prog}.py`
- **年份版本化**：curriculum 按入学年份分目录，override 可带 `intake_year` 约束

## 接入新专业的步骤

1. 预构建已有该专业 curriculum（`scripts/prog_crs/build.py`）
2. 放一份该专业真实 SIS AR 样本 → 跑 mapper → 看 unmapped / 低置信度清单
3. 命中不了的用 override 文件补齐 → 样本存为 fixture → 回归通过
