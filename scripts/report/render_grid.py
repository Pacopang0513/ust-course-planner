#!/usr/bin/env python3
"""
课程表周历 — scripts/report/render_grid.py
==========================================
把 timetable_plan.json 选定方案渲染为周视图：
  - 终端 ASCII 表格（默认）
  - 单文件 HTML 导出（--html → output/timetable_{plan_id}.html，内联样式）

时间槽解析复用 scripts/wcq/conflict.py 的 parse_slots（多时段/跨天/日期窗口）。

用法:
  python3 scripts/report/render_grid.py --plan 1
  python3 scripts/report/render_grid.py --plan 1 --html
"""

import argparse
import json
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from wcq.conflict import DAY_INDEX, DAY_NAMES, parse_slots  # noqa: E402

GRID_START = 8 * 60
GRID_END = 20 * 60
SLOT_MIN = 30


def load(p: Path) -> dict:
    if not p.exists():
        sys.exit(f"错误: 缺少 {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def short_code(code: str) -> str:
    parts = code.split()
    return "".join(parts[:2]) if len(parts) >= 2 else code


def build_grid(details: list) -> dict:
    """course_details → {(day, start): {code, section, room, instructors, end}}"""
    cells = {}
    for d in details:
        slots = parse_slots(d.get("datetime", ""))
        if not slots:
            continue
        for slot in slots:
            day, s, e = slot[0], slot[1], slot[2]
            if day > 4:
                continue
            cells[(day, s)] = {
                "code": d.get("code", ""),
                "short": short_code(d.get("code", "")),
                "section": d.get("section", ""),
                "room": d.get("room", ""),
                "instructors": ", ".join(d.get("instructors") or []) or "-",
                "end": e,
                "full": d,
            }
    return cells


def _fmt_min(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def render_ascii(cells: dict, details: list, plan: dict = None) -> str:
    days = [d for d in range(5) if any((d, s) in cells for s in
                                       range(GRID_START, GRID_END, SLOT_MIN))]
    if not days:
        days = [0, 1, 2, 3, 4]
    col_w = 15
    def line():
        return "+" + "+".join("-" * col_w for _ in days) + "+"
    head = "|" + "|".join(f"{DAY_NAMES[d]:^{col_w}}" for d in days) + "|"
    out = [line(), head, line()]
    t = GRID_START
    while t < GRID_END:
        row = []
        for d in days:
            cell = cells.get((d, t))
            if cell and cell.get("_span"):
                continue
            if cell:
                span = max(1, (cell["end"] - t) // SLOT_MIN)
                if span > 1:
                    # 记录跨度，后续行跳过
                    for k in range(1, span):
                        cells[(d, t + k * SLOT_MIN)] = {"_span": True}
                text = f"{cell['short']}\n{cell['section']}\n{cell['room'] or ''}"
                lines = text.splitlines()
                block = []
                for i, ln in enumerate(lines[:2]):
                    block.append(ln[:col_w].center(col_w))
                row.append("\n".join(block))
            else:
                row.append(" " * col_w)
        out.append(f"|{_fmt_min(t):>4}" + "|".join(row) + "|")
        t += SLOT_MIN
    out.append(line())
    # 图例：未排时间/冲突提示
    tba = [d.get("code") for d in details if "TBA" in (d.get("section") or "")]
    if tba:
        out.append(f"\n! 无时间（TBA，不计入周历）: {', '.join(tba)}")
    if plan is not None:
        free = plan.get("free_days") or []
        if free:
            out.append(f"\n空闲日: {'、'.join(free)} 无课"
                       f"（每周上课 {len(plan.get('days_used') or [])} 天）")
        elif plan.get("days_used"):
            out.append(f"\n无整天空闲（{', '.join(plan['days_used'])} 均有课）")
        for mc in plan.get("meal_conflicts") or []:
            out.append(f"! {mc['day']} {mc['meal']}（{mc['window']}）被占用: "
                       + "、".join(f"{c['code']}（{c['times']}）" for c in mc.get("courses", [])))
    return "\n".join(out)


def render_html(cells: dict, details: list, plan_id: str, label: str,
                total_credits) -> str:
    days = [0, 1, 2, 3, 4]
    colors = ["#e8f0fe", "#fde7e9", "#e6f4ea", "#fef7e0", "#f3e8fd",
              "#e0f7fa", "#fff3e0"]
    def color_of(code: str) -> str:
        return colors[int(hashlib.md5(code.encode()).hexdigest(), 16) % len(colors)]
    t = GRID_START
    rows = []
    while t < GRID_END:
        tds = []
        for d in days:
            cell = cells.get((d, t))
            if cell and cell.get("_span"):
                continue
            if cell:
                span = max(1, (cell["end"] - t) // SLOT_MIN)
                content = (f"<b>{cell['short']}</b><br>{cell['section']}"
                           f"<br><small>{cell['room'] or ''}<br>"
                           f"{cell['instructors']}</small>")
                tds.append(f"<td rowspan='{span}' "
                           f"style='background:{color_of(cell['code'])};"
                           f"vertical-align:top;padding:4px;"
                           f"border:1px solid #ccc;'>"
                           f"{content}</td>")
            else:
                tds.append("<td style='border:1px solid #eee;'></td>")
        rows.append(f"<tr><td style='text-align:right;padding-right:6px;"
                    f"border:1px solid #ddd;white-space:nowrap;'>"
                    f"{_fmt_min(t)}</td>{''.join(tds)}</tr>")
        t += SLOT_MIN
    tba = [d.get("code") for d in details if "TBA" in (d.get("section") or "")]
    tba_note = (f"<p style='color:#b23c17;'>无时间（TBA）课程: {', '.join(tba)}</p>"
                if tba else "")
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="utf-8"><title>UST 课表 — {label}</title></head>
<body style="font-family:'Segoe UI',Microsoft YaHei,sans-serif;margin:24px;">
<h2>UST 课程表 — {label}</h2>
<p>总学分 {total_credits}</p>
<table style="border-collapse:collapse;width:100%;max-width:960px;font-size:13px;">
<tr style="background:#f5f5f5;">
<td style="border:1px solid #ddd;"></td>
{"".join(f"<th style='border:1px solid #ddd;padding:6px;'>{DAY_NAMES[d]}</th>"
         for d in days)}
</tr>
{''.join(rows)}
</table>
{tba_note}
<p style="color:#888;font-size:12px;">由 ustplan grid --html 生成（单文件，可离线打开）</p>
</body>
</html>"""
    return html


def main():
    ap = argparse.ArgumentParser(description="课程表周历（ASCII / HTML）")
    ap.add_argument("--plan", default="1", help="方案序号（plan-1 → 1）")
    ap.add_argument("--html", action="store_true", help="导出 HTML")
    ap.add_argument("--output", default=None, help="HTML 输出路径（默认 output/timetable_plan-N.html）")
    args = ap.parse_args()

    plans = load(ROOT / "output" / "timetable_plan.json")
    plan = next((p for p in plans.get("plans", [])
                 if p.get("plan_id") == f"plan-{args.plan}"
                 or p.get("plan_id") == args.plan), None)
    if not plan:
        sys.exit(f"错误: 找不到 plan-{args.plan}（可用: "
                 f"{', '.join(p.get('plan_id') for p in plans.get('plans', []))}）")

    details = plan.get("course_details", [])
    cells = build_grid(details)
    label = f"{plan.get('label', plan['plan_id'])}（{plan.get('total_credits')} cr）"
    print(f"\n===== {label} =====")
    print(render_ascii(cells, details, plan))

    if args.html:
        dest = Path(args.output) if args.output else \
            ROOT / "output" / f"timetable_{plan['plan_id']}.html"
        html = render_html(cells, details, plan["plan_id"],
                           label, plan.get("total_credits"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        print(f"\nHTML 已导出 -> {dest}")


if __name__ == "__main__":
    main()
