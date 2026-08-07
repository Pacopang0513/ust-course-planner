#!/usr/bin/env python3
"""
一年制课程检测 — scripts/rank/year_courses.py
================================================
识别"全年课程"（学分按学期拆分）的候选：课程描述含跨两学期语义
（one year / two regular terms / fall and spring 等），且 units>0
（0 学分课程无折算意义，仅提示）。这类课程的 schedule units 是全年总学分，
每学期实际注册 = units/2（如 PHYS 4291：全年 6 学分 → 每学期 3 学分）。

用法:
  python3 scripts/rank/year_courses.py --session <SESSION>          # 列出候选
  python3 scripts/rank/year_courses.py --session <SESSION> --note-file database/course_notes/PHYS.json
      # 输出含写入 course_notes 的建议（tags.year_long）

确认后的课程在 database/course_notes/{SUBJ}.json 标 tags: ["year_long"]，
planner 自动按 units/2 折算学期学分（--credits-override 手动覆盖仍优先）。
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 全年语义模式（描述措辞多样，多模式覆盖；避免误中 "one-credit" 等）
YEAR_PATTERNS = [
    r"\b(?:extended|spread|conducted)\s+over\s+(?:two|2)\s+regular\s+terms\b",
    r"\b(?:over|across|for|during)\s+(?:two|2)\s+regular\s+terms\b",
    r"\blasts?\s+for\s+one\s+year\b",
    r"\bone\s+year\s+long\b",
    r"\bone\s+year\s+course\b",
    r"\bfull\s+year\b",
    r"\bacademic\s+year\b",
    r"\bfall\s+and\s+spring\b",
    r"\bspring\s+and\s+fall\b",
]
RE_YEAR = re.compile("|".join(f"(?:{p})" for p in YEAR_PATTERNS), re.I)


def detect(session: str, data_dir: Path = None) -> list:
    """courses_{session}.json → [{code, title, units, per_semester, matched}]"""
    p = (data_dir or ROOT / "data") / f"courses_{session}.json"
    if not p.exists():
        sys.exit(f"错误: 找不到 {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for c in data.get("courses", []):
        desc = (c.get("attributes") or {}).get("DESCRIPTION", "")
        m = RE_YEAR.search(desc)
        if not m:
            continue
        code = f"{c.get('code', '')} {c.get('number', '')}".strip()
        units = c.get("units")
        out.append({
            "code": code, "title": c.get("title", ""), "units": units,
            "per_semester": round(units / 2, 1) if isinstance(units, (int, float)) and units > 0 else None,
            "matched": m.group(0),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="一年制课程检测（学分按学期拆分）")
    ap.add_argument("--session", default="")
    ap.add_argument("--data-dir", default="")
    args = ap.parse_args()
    if not args.session:
        sys.exit("错误: 缺少 --session（学期代码；运行中的学期可由 ustplan status 查询）")

    hits = detect(args.session, Path(args.data_dir) if args.data_dir else None)
    if not hits:
        print(f"（{args.session}）未检测到描述含全年语义且 units>0 的课程")
        return
    print(f"（{args.session}）全年课程候选 {len(hits)} 门：")
    for h in hits:
        if h["per_semester"] is not None:
            print(f"  {h['code']:12} | {h['title'][:38]:38} | 全年 {h['units']} 学分"
                  f" → 每学期 {h['per_semester']} | 匹配: {h['matched']}")
        else:
            print(f"  {h['code']:12} | {h['title'][:38]:38} | units={h['units']}"
                  f"（0 学分无折算意义）| 匹配: {h['matched']}")
    print("\n确认后写入 database/course_notes/{SUBJ}.json 的 tags: [\"year_long\"]，"
          "planner 自动按 units/2 折算学期学分")


if __name__ == "__main__":
    main()
