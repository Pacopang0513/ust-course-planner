#!/usr/bin/env python3
"""
AR↔curriculum 映射主入口 — mapper/run.py
========================================
输入 SIS Academic Requirements + 预构建 curriculum，为每个"未满足"条目
生成候选课程与置信度。产物写入 data/mapping_result.json。

用法:
  python3 scripts/mapper/run.py --program PHYS \\
      --ar cache/sis/sis_academic_req.json \\
      --curriculum database/curriculum/2026-27/PHYS.json \\
      --output data/mapping_result.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "mapper"))

import generic
import registry


def load_json(path) -> dict:
    p = Path(path)
    if not p.exists():
        sys.exit(f"错误: 找不到 {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description="AR↔curriculum 映射")
    ap.add_argument("--program", required=True)
    ap.add_argument("--ar", required=True, help="SIS Academic Requirements JSON")
    ap.add_argument("--curriculum", default="", help="预构建 curriculum JSON（默认按年份定位）")
    ap.add_argument("--intake-year", help="入学年份，自动定位 database/curriculum/{year}/{PROG}.json")
    ap.add_argument("--mappings-dir", default=str(ROOT / "database" / "mappings"))
    ap.add_argument("--output", default=str(ROOT / "data" / "mapping_result.json"))
    args = ap.parse_args()

    curriculum_path = args.curriculum
    if not curriculum_path:
        if not args.intake_year:
            sys.exit("错误: 需指定 --curriculum 或 --intake-year")
        curriculum_path = ROOT / "database" / "curriculum" / args.intake_year / f"{args.program}.json"
    ar = load_json(args.ar)
    curriculum = load_json(curriculum_path)
    entries = generic.flatten_curriculum(curriculum)
    mappings_dir = args.mappings_dir

    out_entries, unmapped, cc_items = [], [], []

    groups = ar.get("requirement_groups", [])
    for i, g in enumerate(groups):
        name = g.get("name", "")
        status = g.get("overall_status") or g.get("status", "unknown")
        codes = g.get("related_courses", [])
        if status == "satisfied":
            continue

        ar_text = f"{name} {' '.join(codes)}"

        # 覆盖规则（最高优先级）
        rule = registry.find_override(args.program, mappings_dir, name)
        if rule:
            hits = registry.select_by_override(rule, entries)
            out_entries.append({
                "ar_group": name, "ar_status": status,
                "curriculum_block": rule.get("map_to", {}).get("block", ""),
                "curriculum_group": rule.get("map_to", {}).get("section", ""),
                "candidates": sorted({c for e in hits for c in e["courses"]}),
                "confidence": "explicit",
                "method": "override",
                "evidence": {"note": rule.get("note", "")},
            })
            continue

        # Common Core 分流
        if generic.is_cc_item(ar_text, codes):
            cc_items.append({
                "ar_group": name, "ar_status": status,
                "channel": "cc", "candidates": [],
                "note": "分布要求 → 走 database/common-core/ Common Core 规则",
            })
            continue

        # 代码交集
        hits = generic.code_intersection(codes, entries)
        if hits:
            note = hits[0][0]["note"] or ""
            out_entries.append({
                "ar_group": name, "ar_status": status,
                "curriculum_block": hits[0][0]["block"],
                "curriculum_group": f"{hits[0][0]['section_name']} "
                                    f"(note: {note[:40]})",
                "candidates": sorted({c for e, _ in hits for c in e["courses"]}),
                "confidence": "high",
                "method": "code_intersection",
                "evidence": {"matched_groups": [e["section_name"] for e, _ in hits],
                             "matched_codes": sorted({c for _, cs in hits for c in cs})},
            })
            continue

        # 文本匹配 / 结构兜底
        best = generic.best_match(ar_text, entries, section=None)
        if best["confidence"] != "unmapped":
            e = best["entry"]
            note = e["note"] or ""
            out_entries.append({
                "ar_group": name, "ar_status": status,
                "curriculum_block": e["block"],
                "curriculum_group": f"{e['section_name']} (note: {note[:40]})",
                "candidates": e["courses"],
                "confidence": best["confidence"],
                "method": best["method"],
                "evidence": {"score": best.get("score")},
            })
        else:
            unmapped.append({
                "ar_group": name, "ar_status": status,
                "reason": "无课程代码可 join，文本无法定位",
            })

    result = {
        "program": args.program,
        "intake_year": curriculum.get("intake_year", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "mapped": len(out_entries),
            "cc_routed": len(cc_items),
            "unmapped": len(unmapped),
        },
        "entries": out_entries,
        "cc_items": cc_items,
        "unmapped": unmapped,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 映射完成: {result['summary']}")
    print(f"   产物 -> {out}")
    for u in unmapped:
        print(f"   ⚠️  未映射: {u['ar_group']} [{u['ar_status']}]")


if __name__ == "__main__":
    main()
