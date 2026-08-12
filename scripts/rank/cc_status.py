#!/usr/bin/env python3
"""
CC 区域满足性核查 — scripts/rank/cc_status.py
=============================================
Phase 2/P3 通用工具：已修课程 → 各 CC 区域已修/未修 + Broadening 12 学分 4 区域
结论（所有用户一致，AI 不重复从零构建）。规则与 database/common-core/*.md 一致：
  - 区域归属：database/common-core/areas_{GROUP}.json 的 code_area 映射
  - home area：按专业前缀（SSCI→S、SENG 多数→T、SBM 多数→SA；可 --home-area 覆盖）
  - Broadening：home area 之外 ≥12 学分且覆盖 ≥4 个不同区域

用法:
  python3 scripts/rank/cc_status.py --passed data/passed_courses.json \
      --admission-year 2023-24
  python3 scripts/rank/cc_status.py --passed data/passed_courses.json \
      --admission-year 2023-24 --major DSCT --json
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 专业前缀 → home area（来自 database/common-core/cc-2022-2024.md；可 --home-area 覆盖）
HOME_AREA_BY_PREFIX = {
    "COMP": "T", "COSC": "T", "CPEG": "T", "EEEN": "T", "ELEC": "T",
    "MECH": "T", "CIVL": "T", "IEEM": "T", "ISDN": "T",
    "BIEN": "S", "CENG": "S",  # BIEN/CENG/EEEN: S+T → 取并集见下
    "MATH": "S", "PHYS": "S", "CHEM": "S", "DSCT": "S", "LIFS": "S",
    "ACCT": "SA", "ECON": "SA", "FINA": "SA", "MARK": "SA", "MGMT": "SA",
    "IS": "SA", "GBUS": "SA", "QSA": "SA", "EVMT": "SA",
}
HOME_AREA_UNION = {"BIEN", "CENG", "EEEN"}  # 这些前缀 home area 为 S+T 并集


def admission_to_group(admission_year: str) -> str:
    m = re.match(r"(\d{4})", str(admission_year or ""))
    if not m:
        return ""
    y = int(m.group(1))
    if y <= 2021:
        return "4Y"
    if y <= 2024:
        return "CC22"
    if y == 2025:
        return "CC25"
    return "CC26"


def home_area(major: str) -> str:
    """专业 → home area（并集专业返回 'S,T' 格式）"""
    code = (major or "").strip().upper()
    prefix = code.split()[0] if code else ""
    if prefix in HOME_AREA_UNION:
        return "S,T"
    return HOME_AREA_BY_PREFIX.get(prefix, "")


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="CC 区域满足性核查")
    ap.add_argument("--passed", default=str(ROOT / "data" / "passed_courses.json"))
    ap.add_argument("--admission-year", required=True)
    ap.add_argument("--major", default="", help="主修代码（如 DSCT，用于 home area）")
    ap.add_argument("--home-area", default="", help="home area 覆盖（如 S/T/SA）")
    ap.add_argument("--cc-areas", default="", help="历史 CC 区域表（默认自动按入学年份）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    group = admission_to_group(args.admission_year)
    areas_path = Path(args.cc_areas) if args.cc_areas else \
        ROOT / "database" / "common-core" / f"areas_{group}.json"
    if not areas_path.exists():
        sys.exit(f"错误: 未找到历史 CC 区域表 {areas_path}"
                 f"（先跑 scripts/wcq/cc_areas.py --admission-year {args.admission_year}）")

    areas = json.loads(areas_path.read_text(encoding="utf-8-sig"))
    code_area = areas.get("code_area", {})
    passed = json.loads(Path(args.passed).read_text(encoding="utf-8-sig")) \
        .get("courses", [])

    home = args.home_area or home_area(args.major)
    home_set = {x.strip() for x in home.split(",") if x.strip()}

    # 区域 → 已修课程（按白名单 status；白名单与 filter.PASSED_STATUSES 一致）
    KEEP = ("taken", "transferred", "exempted", "in_progress")
    done_codes = {c["code"].replace(" ", ""): c for c in passed
                  if c.get("status") in KEEP}

    result = {"admission_year": args.admission_year, "cc_group": group,
              "home_area": home, "areas": []}
    broad_credits, broad_areas = 0.0, set()
    for a in areas.get("areas", []):
        label = a.get("label", "")
        codes = a.get("codes", [])
        have = [c for c in codes if c.replace(" ", "") in done_codes]
        credits = sum(done_codes[c.replace(" ", "")].get("credits") or 0
                      for c in have)
        area_code = a.get("area_code", "")
        result["areas"].append({
            "area_code": area_code, "label": label, "courses": have,
            "credits": round(credits, 1),
            "satisfied": len(have) > 0,
        })
        if area_code not in ("20", "21", "22", "23") and area_code not in home_set:
            # Broadening 区域（非 Foundations、非 home area）
            broad_credits += credits
            if credits > 0:
                broad_areas.add(area_code)

    result["broadening"] = {
        "credits_outside_home": round(broad_credits, 1),
        "areas_covered": sorted(broad_areas),
        "credits_ok": broad_credits >= 12,
        "areas_ok": len(broad_areas) >= 4,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"CC 组 {group} | home area = {home or '（未知，需确认）'}")
    for a in result["areas"]:
        mark = "✅" if a["satisfied"] else "⬜"
        print(f"  {mark} {a['label'][:44]:44} 已修 {a['credits']:.0f} 学分"
              f"{'：' + ', '.join(a['courses'][:5]) if a['courses'] else ''}")
    b = result["broadening"]
    print(f"\nBroadening（home 外）：{b['credits_outside_home']:.0f} 学分 / "
          f"{len(b['areas_covered'])} 个区域（要求 ≥12 学分 / ≥4 区域）→ "
          f"{'✅ 满足' if b['credits_ok'] and b['areas_ok'] else '⚠️ 未满足'}")
    if not b["credits_ok"] or not b["areas_ok"]:
        print("  提示：A/H/T/SA/S 中未满足区域需补课；若含 1 学分课注意 12 学分下限")


if __name__ == "__main__":
    main()
