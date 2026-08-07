#!/usr/bin/env python3
"""
SIS Academic Requirements → 未修课程 — scripts/rank/ar_to_unmet.py
==================================================================
Step 1 的回退路径：当 `database/curriculum/{admissionYear}/{PROG}.json`（prog-crs 预构建）
不可得（如旧入学年份已下线）时，改用 SIS Academic Requirements（学生本人学位审计，
`cache/sis/sis_academic_req.json`）作为权威来源生成 data/unmet_courses.json。

数据流（单入口，无联网）：
  sis_academic_req.json（PHYS 需求组 + 组内课程+状态）
  + cc_courses_{session}.json（wcq 按入学年份组抓取的 CC 池）
  + passed_courses.json（已修，兜底排除）
  → data/unmet_courses.json

规则（固定）：
  - PHYS 需求组（含 "PHYS"）内 status=not_taken 的课程 → major_required（代码归一为 "SUBJ NUMBER"）
  - School Requirement (Part 2)（理学基础）not_taken → major_elective
  - CC：cc_courses 池全部课程 → cc_required（含区域 source 标注）
  - 复杂语义（OR/AND、池内任选、Capstone 三选一、C-Comm 3 学分需求）由 AI 在
    note_interpretation 中精读补全（脚本只打基架，符合"复杂逻辑结合模型输出"原则）

用法:
  python3 scripts/rank/ar_to_unmet.py --ar cache/sis/sis_academic_req.json \
      --cc data/cc_courses_<SESSION>.json --profile data/profile.json \
      --passed data/passed_courses.json --session <SESSION> \
      --output data/unmet_courses.json
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MAJOR_GROUP_MARKERS = ("PHYS",)
SCHOOL_GROUP_MARKERS = ("School Requirement",)


def norm_code(code: str) -> str:
    """'PHYS1113' / 'PHYS 1113' → 'PHYS 1113'"""
    m = re.match(r"^([A-Z]{2,6})\s*(\d{4}[A-Z]?)$", code.strip())
    return f"{m.group(1)} {m.group(2)}" if m else code.strip()


def major_courses(ar: dict) -> list:
    """AR 需求组 → major_required / major_elective 候选（not_taken 且未修）"""
    out = []
    for g in ar.get("requirement_groups", []):
        name = g.get("name", "")
        if any(m in name for m in MAJOR_GROUP_MARKERS):
            cat = "major_required"
        elif any(m in name for m in SCHOOL_GROUP_MARKERS):
            cat = "major_elective"
        else:
            continue
        for c in g.get("courses", []):
            if c.get("status") != "not_taken":
                continue
            out.append({
                "code": norm_code(c.get("code", "")),
                "name": c.get("description", "") or "",
                "credits": c.get("units"),
                "category": cat,
                "source_groups": [{"block": cat.split("_")[0], "section": name,
                                   "group": name}],
                "note_interpretation": f"AR 组「{name}」未修，复杂语义（计数/池/选项）待 AI 精读补全",
            })
    return out


def cc_courses(cc: dict, session: str, areas_filter: list) -> list:
    """wcq CC 池 → cc_required 候选（整池或按 --areas 过滤）"""
    out = []
    for a in cc.get("areas", []):
        area = a.get("area", "")
        if areas_filter:
            hit = False
            for f in areas_filter:
                if f == a.get("area_code", ""):
                    hit = True
                elif not f.isdigit() and f.lower() in area.lower():
                    hit = True
            if not hit:
                continue
        for c in a.get("courses", []):
            code = norm_code(f"{c.get('code', '')} {c.get('number', '')}".strip())
            if not code.strip() or code.strip().lower() == "none":
                continue
            out.append({
                "code": code,
                "name": c.get("title", "") or "",
                "credits": c.get("units"),
                "category": "cc_required",
                "source_groups": [{"block": "common-core", "section": area,
                                   "group": area}],
                "note_interpretation": f"CC22 区域「{area}」（session {session} 可读池）",
            })
    return out


def main():
    ap = argparse.ArgumentParser(description="SIS AR → 未修课程（curriculum 缺失回退）")
    ap.add_argument("--ar", default=str(ROOT / "cache" / "sis" / "sis_academic_req.json"),
                    help="SIS Academic Requirements 解析产物")
    ap.add_argument("--session", default="")
    ap.add_argument("--areas", nargs="*", default=[],
                    help="只取指定 CC 区域（子串匹配 area_code/area，如 C-Comm A H SA）；"
                         "空=全池（由 AI 按 AR 状态收窄）")
    ap.add_argument("--profile", default=str(ROOT / "data" / "profile.json"))
    ap.add_argument("--passed", default=str(ROOT / "data" / "passed_courses.json"))
    ap.add_argument("--output", default=str(ROOT / "data" / "unmet_courses.json"))
    args = ap.parse_args()
    if not args.session:
        sys.exit("错误: 缺少 --session（学期代码；运行中的学期可由 ustplan status 查询）")

    ar_path = Path(args.ar)
    if not ar_path.exists():
        sys.exit(f"错误: 找不到 AR 产物 {ar_path}（先运行 scripts/sis/parser.py --fetch）")
    ar = json.loads(ar_path.read_text(encoding="utf-8"))

    cc_path = ROOT / "data" / f"cc_courses_{args.session}.json"
    if not cc_path.exists():
        sys.exit(f"错误: 找不到 CC 池 {cc_path}（先运行 wcq/crawler.py --admission-year）")
    cc = json.loads(cc_path.read_text(encoding="utf-8"))

    profile = {}
    if Path(args.profile).exists():
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    passed = set()
    if Path(args.passed).exists():
        passed = {norm_code(c.get("code", "")) for c in
                  json.loads(Path(args.passed).read_text(encoding="utf-8")).get("courses", [])}

    courses = [c for c in major_courses(ar) if c["code"] not in passed]
    courses += [c for c in cc_courses(cc, args.session, args.areas)
                if c["code"] not in passed]

    # 去重（同 code 多组）
    seen, unique = set(), []
    for c in courses:
        if c["code"] in seen:
            continue
        seen.add(c["code"])
        unique.append(c)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "program": profile.get("programs", {}).get("first_major", ""),
        "intake_year": profile.get("admission_year", ""),
        "graduation_target_credits": profile.get("graduation_credits", 120),
        "notes": [
            "本产物由 ar_to_unmet.py 生成：SIS AR 为 curriculum 缺失时的权威回退源",
            "复杂语义（Capstone 三选一 / 池内计数 / C-Comm 3 学分 / CTDL 替代）需 AI 精读 note_interpretation 补全",
        ],
        "courses": unique,
    }
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter
    print(f"AR→unmet 完成: {len(unique)} 门 -> {dest}")
    print(f"  分类: {dict(Counter(c['category'] for c in unique))}")


if __name__ == "__main__":
    main()
