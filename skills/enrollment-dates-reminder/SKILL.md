---
name: enrollment-dates-reminder
description: 查询 UST 目标学期的选课时间（Shopping Cart / Enrollment Appointment / Add-Drop 三期）并作为提醒附加到最终输出末尾。Use when generating the final timetable plan or before finishing the course selection report.
---

# Enrollment Dates Reminder

## 何时使用

在输出最终报告/课程表方案之前调用，将选课时间提醒附加到输出末尾。目标学期默认为用户需求的下一学期（通常为下一 Fall 或 Spring Regular Term）。

## 步骤

1. **确定目标学期与用户年级**：优先读取 `data/profile.json`（如有）；否则询问用户（当前学期 + 入学年份，由 admissionYear 推算年级）。
2. **抓取选课时间**（Academic Registry 公开页面）：
   - Fall: `https://registry.hkust.edu.hk/resource-library/class-enrollment-schedule-ug`
   - Spring/其他: 在 `https://registry.hkust.edu.hk/resource-library/class-enrollment-ug` 中找对应学期版本
3. **提取三期时间**：
   - Validation Period（Shopping Cart 阶段）
   - Enrollment Period（Enrollment Appointment）——按年级分批（Year 4&5 → 3 → 2 → 1），只记录用户年级对应时段
   - Add/Drop Period
4. **按固定模板生成提醒**，附加在最终输出末尾（课程表方案之后）。

## 输出模板（固定格式，禁止更改）

```
## 选课时间提醒（{目标学期}）
- Shopping Cart（Validation）：{日期} {时间} 起
- Enrollment Appointment（Year {年级}）：{日期} {时间}
- Add/Drop 窗口：{起止日期}（每天 07:30-09:30 SIS 维护，不可用）
- 提醒：Enrollment 开始即尽早提交 shopping cart；高年级优先，低年级热门课竞争大；特殊选课（pre-req 豁免、超负荷等）需提前取得教授/学院批准。
```

## 失败处理

- 公开页面抓取失败或无数据：改用 SIS Student Center 的 "Enrollment Dates"（需 PS_TOKEN，经 `scripts/` 读取，AI 不接触 cookie），或提醒用户自行查看。
- 两次尝试均失败：输出提醒为"选课时间以 SIS Student Center 为准"，并在报告中注明。
- 若当前已过 Enrollment 阶段：提醒内容改为 Add/Drop 截止时间与加退课注意事项。
