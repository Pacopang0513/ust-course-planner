#!/usr/bin/env python3
"""
WCQ 时间冲突检测器 — conflict.py
================================
给定学期 + 课程列表，从已抓取的课程数据（courses_{session}.json）解析上课时间，
检测各课之间的时间冲突（time crash）。

数据来源（默认）：父目录 CourseArranger/data/courses_{session}.json
（由父目录 crawler.py 抓取；--data-dir 可覆盖）。

datetime 解析设计（关键）：
  - 拆成多个槽 (day, start_min, end_min)
  - 多天前缀展开：'TuTh 01:30PM - 02:50PM' → Tu 与 Th 各一个槽
  - 多时段兼容（不同天不同时间）：'Mo 04:00PM - 05:20PM, Fr 10:00AM - 11:20AM'
    → Mo 与 Fr 两个不同时间的槽（旧逻辑只认"两天同一时段"）
  - 忽略日期窗口前缀：'01-SEP-2026 - 17-OCT-2026Mo 03:00PM - 04:50PM'
  - TBA/TBD 无时间 → 无法判定，标记提醒

用法:
  python3 scripts/wcq/conflict.py --session 2610 --courses "ACCT 2010:L02" "COMP 2011:L1" "MATH 2352"
  python3 scripts/wcq/conflict.py --session 2610 --courses "COMP 2011" "MATH 2352" --data-dir ../data
  python3 scripts/wcq/conflict.py --selftest          # 解析器自测
"""

import argparse
import json
import re
import sys
from pathlib import Path

DAY_INDEX = {"Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

DATE_WINDOW = re.compile(
    r"\d{2}-[A-Z]{3}-\d{4}\s*-\s*\d{2}-[A-Z]{3}-\d{4}\s*"
)
SLOT = re.compile(
    r"((?:Mo|Tu|We|Th|Fr|Sa|Su)+)\s+(\d{1,2}):(\d{2})(AM|PM)"
    r"\s*-\s*(\d{1,2}):(\d{2})(AM|PM)"
)
NO_TIME = re.compile(r"(TBA|TBD|BYAPT|TBC)", re.IGNORECASE)


def _to_min(h: int, m: int, ap: str) -> int:
    if ap == "AM":
        h = 0 if h == 12 else h
    else:
        h = h if h == 12 else h + 12
    return h * 60 + m


def parse_slots(dt: str) -> list:
    """datetime 字符串 → [(day_int, start_min, end_min), ...]；无有效时间返回 []"""
    if not dt:
        return []
    # 逐段剔除 TBA/TBD 等无时间片段（如 "Mo 09:00AM - 10:20AM, TBA"），保留有效段
    text = ", ".join(
        seg.strip() for seg in dt.split(",") if not NO_TIME.search(seg)
    ).strip()
    if not text:
        return []
    text = DATE_WINDOW.sub("", text)
    slots = []
    for m in SLOT.finditer(text):
        start = _to_min(int(m.group(2)), int(m.group(3)), m.group(4))
        end = _to_min(int(m.group(5)), int(m.group(6)), m.group(7))
        if end < start:
            end += 24 * 60  # 跨午夜防御
        days = m.group(1)
        i = 0
        while i < len(days):
            day = days[i:i + 2]
            if day in DAY_INDEX:
                slots.append((DAY_INDEX[day], start, end))
            i += 2
    return slots


def _overlap(a, b) -> bool:
    """两个槽 (day, s, e) 是否冲突"""
    if a[0] != b[0]:
        return False
    return a[1] < b[2] and b[1] < a[2]


def load_courses(session: str, data_dir) -> dict:
    p = Path(data_dir) / f"courses_{session}.json"
    if not p.exists():
        sys.exit(f"错误: 找不到数据文件 {p}（先运行父目录 crawler.py 或 --data-dir）")
    return json.loads(p.read_text(encoding="utf-8"))


def _fmt(slots) -> str:
    return "; ".join(
        f"{DAY_NAMES[d]} {s//60:02d}:{s%60:02d}-{e//60:02d}:{e%60:02d}"
        for d, s, e in slots
    )


def find_course(data, code: str, number: str):
    for c in data["courses"]:
        if c["code"].upper() == code.upper() and str(c["number"]).upper() == number.upper():
            return c
    return None


def resolve(course_spec: str, data) -> dict:
    """'CODE NUMBER[:SECTION]' → {course, section}。未指定 section 取第一个。"""
    spec, _, sec = course_spec.partition(":")
    parts = spec.strip().split()
    if len(parts) < 2:
        sys.exit(f"错误: 课程格式应为 'CODE NUMBER[:SECTION]'，收到: {course_spec!r}")
    code, number = parts[0].upper(), parts[1].upper()
    course = find_course(data, code, number)
    if course is None:
        sys.exit(f"错误: 数据中找不到 {code} {number}")
    sections = course["sections"]
    if not sections:
        sys.exit(f"警告: {code} {number} 无 section")
    if sec:
        match = [s for s in sections if s["section"].upper() == sec.upper()]
        if not match:
            sys.exit(f"错误: {code} {number} 无 section {sec}，可选: "
                     f"{', '.join(s['section'] for s in sections)}")
        section = match[0]
    else:
        section = sections[0]
    return {"code": f"{code} {number}", "course": course, "section": section}


def detect(courses: list, data: dict) -> dict:
    """对已解析的课程列表检测冲突。courses: [{code, course, section}]"""
    resolved = [resolve(c, data) for c in courses]
    entries = []
    for r in resolved:
        slots = parse_slots(r["section"].get("datetime", ""))
        entries.append({
            "label": r["code"],
            "section": r["section"]["section"],
            "datetime": r["section"].get("datetime", ""),
            "room": r["section"].get("room", ""),
            "slots": slots,
        })

    conflicts = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            overlaps = []
            for sa in a["slots"]:
                for sb in b["slots"]:
                    if _overlap(sa, sb):
                        day = sa[0]
                        s, e = max(sa[1], sb[1]), min(sa[2], sb[2])
                        overlaps.append((day, s, e))
            if overlaps:
                conflicts.append({
                    "a": a, "b": b,
                    "overlaps": sorted(set(overlaps)),
                })
    return {"entries": entries, "conflicts": conflicts}


def alternatives(entry: dict, other_slots: list, course: dict) -> list:
    """返回某课中不与该课对端（other_slots）冲突的其他 section"""
    alts = []
    for s in course.get("sections", []):
        if s["section"].upper() == entry["section"].upper():
            continue
        slots = parse_slots(s.get("datetime", ""))
        if any(_overlap(x, y) for x in slots for y in other_slots):
            continue
        alts.append(s)
    return alts


def selftest() -> int:
    """解析器自测：覆盖同天同时、不同天不同时段、日期窗口、TBA"""
    cases = [
        ("TuTh 01:30PM - 02:50PM", 2),
        ("Mo 04:00PM - 05:20PM, Fr 10:00AM - 11:20AM", 2),   # 用户指出的多时段
        ("01-SEP-2026 - 17-OCT-2026We 04:00PM - 05:50PM", 1),  # 日期窗口
        ("TBA", 0),
        ("", 0),
    ]
    ok = True
    for dt, want in cases:
        slots = parse_slots(dt)
        status = "OK" if len(slots) == want else "FAIL"
        if len(slots) != want:
            ok = False
        print(f"  [{status}] {dt!r:50} → {len(slots)} 槽 {_fmt(slots)}")
    # 冲突逻辑：Mo 4pm-5:20 与 Mo 4:30-5:50 冲突；与 Fr 10am 不冲突
    c1 = [(0, 16 * 60, 17 * 60 + 20)]
    c2 = [(0, 16 * 60 + 30, 17 * 60 + 50)]
    c3 = [(4, 10 * 60, 11 * 60 + 20)]
    print(f"  [{'OK' if _overlap(c1[0], c2[0]) else 'FAIL'}] 同天重叠 → 冲突")
    print(f"  [{'OK' if not _overlap(c1[0], c3[0]) else 'FAIL'}] 不同天 → 不冲突")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="WCQ 时间冲突检测")
    ap.add_argument("--session", default="2610", help="学期代码（如 2610 = 2026-27 Fall）")
    ap.add_argument("--courses", nargs="+", help="课程列表，格式 'CODE NUMBER[:SECTION]'")
    ap.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[2] / "data"),
                    help="课程数据目录（默认项目内 data/）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    if not args.courses:
        ap.print_help()
        sys.exit(1)

    data = load_courses(args.session, args.data_dir)
    result = detect(args.courses, data)

    print(f"\n学期 {data.get('semester_name', args.session)} — {len(result['entries'])} 门课")
    for e in result["entries"]:
        tag = "✅" if e["slots"] else "⚠️ 无时间(TBA)"
        print(f"  {tag} {e['label']} [{e['section']}] {e['datetime']} @ {e['room']}")

    if not result["conflicts"]:
        print("\n✅ 无时间冲突")
        return 0

    print(f"\n❌ 发现 {len(result['conflicts'])} 处时间冲突:\n")
    by_label = {r["code"]: r["course"] for r in (resolve(c, data) for c in args.courses)}
    for idx, c in enumerate(result["conflicts"], 1):
        a, b = c["a"], c["b"]
        times = ", ".join(f"{DAY_NAMES[d]} {_fmt_one(s, e)}" for d, s, e in c["overlaps"])
        print(f"══ 冲突 {idx}: {times} ══")
        print(f"  {a['label']}[{a['section']}] ({a['room']})")
        print(f"  ↔  {b['label']}[{b['section']}] ({b['room']})")
        print(f"  交集时段: {times}")
        # 换课建议
        for side, other in ((a, b), (b, a)):
            alts = alternatives(side, other["slots"], by_label[side["label"]])
            if alts:
                print(f"  → 换掉 {side['label']}（避开 {other['label']}[{other['section']}]）可选:")
                for s in alts:
                    print(f"      {s['section']:6} {s.get('datetime','')}  @ {s.get('room','')}")
        print()
    return 1


def _fmt_one(s: int, e: int) -> str:
    return f"{s//60:02d}:{s%60:02d}-{e//60:02d}:{e%60:02d}"


if __name__ == "__main__":
    sys.exit(main())
