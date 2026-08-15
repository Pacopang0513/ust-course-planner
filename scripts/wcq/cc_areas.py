#!/usr/bin/env python3
"""
历史 CC 区域课程表构建 — scripts/wcq/cc_areas.py
================================================
把多个历史学期的 Common Core 区域页课程并集为"课程码 → 区域"静态表，
供 buckets.py 判定"已修课程属于哪个 CC 区域"（CC 满足性全脚本化，无需 AI）。

背景（2026-08 实测）：SIS AR 页面对部分 CC 区域（如 S/SA）不渲染明细（折叠空壳），
"已修 6 学分"无法从 AR 归因到具体区域；而当年开课学期所在的 wcq CC 区域页
（公开、历史 session 仍在）明确列出课程归属（如 SOSC 1969 → SA 区、PHYS 1007 → S 区）。

产物：database/common-core/areas_{GROUP}.json
  {group, generated_at, areas: [{area_code, label, codes: [...]}], code_area: {code: area_code}}

注意（2026-08 实测）：
  - 旧学期（2022-23 及更早 session）索引/区域页全部返回同一份通用页（实际是
    当前索引），本脚本已加"页面=索引页即无效"防呆跳过；
  - 4Y 组（36 学分制）：当前与历史均无真实区域课程页（本学期为空、旧学期不
    提供历史）→ 无法构建 areas_4Y.json，4Y 入学年份走 SIS AR 判定（不生成表）；
  - CC22/CC25/CC26 以最近的在读学期（如 2310-2610）构建，课程归属稳定。

用法:
  python3 scripts/wcq/cc_areas.py --admission-year 2023-24     # 默认：入学年起至今全部学期
  python3 scripts/wcq/cc_areas.py --admission-year 2023-24 --sessions 2520 2530
  python3 scripts/wcq/cc_areas.py --admission-year 2023-24 --force
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "wcq"))

from crawler import (  # noqa: E402  (复用索引/区域页解析)
    _get, admission_to_group, parse_cc_options, parse_cc_page,
)

RAW_ROOT = ROOT / "cache" / "wcq" / "raw"
DEST_ROOT = ROOT / "database" / "common-core"

BASE = "https://w5.ab.ust.hk"


def default_sessions(admission_year: str, latest: int) -> list:
    """入学年份 → 至今所有 Fall/Spring/Summer session（CC 池通常不发布 Winter）"""
    m = re.match(r"(\d{4})", admission_year)
    start = int(m.group(1)) if m else 2020
    now = latest // 100 + 2000
    out = []
    for y in range(start, now + 1):
        for term in (10, 20, 30):
            s = (y % 100) * 100 + term
            if 2000 < s <= latest:
                out.append(str(s))
    return out


def main():
    ap = argparse.ArgumentParser(description="历史 CC 区域课程表构建（code→area 静态表）")
    ap.add_argument("--admission-year", default="", help="入学年份（如 2023-24）→ 自动选 CC 组与学期范围")
    ap.add_argument("--cc-group", choices=["4Y", "CC22", "CC25", "CC26"], default="",
                    help="CC 组（默认由 --admission-year 推导）")
    ap.add_argument("--sessions", nargs="+", default=[],
                    help="指定历史 session（默认：入学年起至最新全部 Fall/Spring/Summer）")
    ap.add_argument("--latest", default="",
                    help="最新 session（默认自动检测，同 crawler --session latest）")
    ap.add_argument("--force", action="store_true", help="强制重抓区域页")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()

    group = args.cc_group or (admission_to_group(args.admission_year) if args.admission_year else "")
    if not group:
        sys.exit("错误: 需提供 --admission-year 或 --cc-group")
    if not args.latest:
        from crawler import latest_session
        args.latest = latest_session()
    latest = int(args.latest)
    sessions = args.sessions or default_sessions(args.admission_year or f"{latest // 100 + 2000 - 2}", latest)
    print(f"CC 组 {group}，历史 session: {', '.join(sessions)}")

    sem = asyncio.Semaphore(args.concurrency)
    raw_dir = RAW_ROOT

    async def fetch_area(session: str, group: str, area: dict,
                         idx_html: str = "") -> tuple:
        p = raw_dir / session / "common_core" / f"{group}-{area['code']}.html"
        if not args.force and p.exists():
            return "skip", session, area
        url = f"{BASE}/wcq/cgi-bin/{session}/common_core/{group}/{area['code']}"
        async with sem:
            html, reason = await asyncio.to_thread(_get, url)
        if not html:
            return "fail", session, area
        if idx_html and html == idx_html:
            # 防呆（2026-08 实测）：旧 session（如 1810-2210）索引/区域页全部返回
            # 同一份"通用页"（338KB，实际是当前索引），若存盘会把整页前 N 门课
            # 误当成该区域课程 → code_area 全错。页面与索引页相同即视为无效。
            print(f"  [BOGUS] {session}/{group}/{area['code']}: 页面=索引页（旧学期"
                  f"未提供真实区域页），跳过")
            return "fail", session, area
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        return "ok", session, area

    async def run():
        stats = {"ok": 0, "skip": 0, "fail": 0}
        fails = []
        area_set = {}   # (session, code) → label
        for session in sessions:
            idx_html, reason = await asyncio.to_thread(
                _get, f"{BASE}/wcq/cgi-bin/{session}/")
            if not idx_html:
                print(f"  [SKIP] {session}: 索引页不可用（{reason}）")
                continue
            groups = parse_cc_options(idx_html, session)
            g = next((x for x in groups if x["group"] == group), None)
            if not g:
                print(f"  [SKIP] {session}: 无 {group} 下拉")
                continue
            for status, sess, area in await asyncio.gather(
                *[fetch_area(session, group, a, idx_html) for a in g["areas"]]
            ):
                stats[status] += 1
                if status == "fail":
                    fails.append(f"{sess}/{group}/{area['code']}")
                if status in ("ok", "skip"):
                    area_set[(sess, area["code"])] = area["label"]
        print(f"区域页抓取统计: {stats}")
        if fails:
            print("失败:", ", ".join(fails[:10]))

        # 汇总 → code→area 并集
        areas_out = {}
        for session in sessions:
            gdir = raw_dir / session / "common_core"
            if not gdir.is_dir():
                continue
            for p in sorted(gdir.glob(f"{group}-*.html")):
                html = p.read_text(encoding="utf-8", errors="ignore")
                if not html.strip():
                    continue
                code = p.stem.split("-", 1)[1] if "-" in p.stem else p.stem
                label = area_set.get((session, code), code)
                for c in parse_cc_page(html, label):
                    ckey = f"{c.get('code', '')} {c.get('number', '')}".strip()
                    if ckey:
                        areas_out.setdefault(code, {"area_code": code, "label": label, "codes": []})
                        if ckey not in areas_out[code]["codes"]:
                            areas_out[code]["codes"].append(ckey)
        code_area = {}
        for a in areas_out.values():
            for c in a["codes"]:
                code_area[c] = a["area_code"]
        doc = {
            "group": group,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sessions": sessions,
            "area_count": len(areas_out),
            "areas": sorted(areas_out.values(), key=lambda x: x["area_code"]),
            "code_area": code_area,
        }
        DEST_ROOT.mkdir(parents=True, exist_ok=True)
        dest = DEST_ROOT / f"areas_{group}.json"
        dest.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"区域表: {len(areas_out)} 个区域 / {len(code_area)} 门课 -> {dest}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
