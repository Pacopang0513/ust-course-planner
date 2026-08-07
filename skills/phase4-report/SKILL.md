---
name: phase4-report
description: Phase 4 总结报告。ustplan report 按模板自动渲染机械段落（画像/未修/过滤/评分/方案/waiver），AI 精读 review_summary 补口碑摘要与下一步建议，附加选课时间提醒（enrollment-dates-reminder），输出 output/final_report.md。Use when producing the final course selection report.
---

# Phase 4 — 总结报告

## 触发

- phase3 done + P5 选定方案后（`ustplan phase begin phase4-report`）。

## 执行（ustplan）

```bash
python3 scripts/ustplan.py report --plan plan-1    # 按模板渲染机械段落
python3 scripts/ustplan.py grid --plan 1 --html    # 周历 HTML 一并交付（可选）
```

- 模板：`templates/reports/final_report.md.tpl`（画像/未修栏位/过滤说明/评分总表/
  方案明细/waiver 清单自动填充；第 4 节口碑摘要与第 7 节建议留占位）。

## AI 职责

1. 精读 `data/review_summary.json` 填第 4 节"候选口碑摘要"
   （每栏位 TOP3：综合评分/推荐度/给分/工作量/今年导师口碑）；
2. 填第 7 节"下一步建议"：选定方案锁定（validation period 尽早提交
   shopping cart）；waiver 申请（课程 + missing pre-req）；overload/低学分说明；
3. **末尾附加选课时间提醒**（enrollment-dates-reminder 固定模板，不可删除）；
4. 产物仅引用 artifact 数据（可追溯），不写脚本运行细节。

## 确认点

- 报告即交付物（无强制确认点）；用户确认后推进：
  `ustplan phase done phase4-report`。

## 交接

final_report.md + timetable_plan.json → phase4.5-must-take 询问必选课；
无必选课 → 流程结束。
