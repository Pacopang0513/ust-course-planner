#!/usr/bin/env python3
"""
Step 4 评论精读范围 — scripts/rank/review_scope.py
==================================================
精读范围固定化（所有用户一致，AI 不重复从零构建）：
  - major_required / cc_required 桶 → 全部精读
  - 其余桶（cc_elective / major_elective）→ 按 review_count 取 TOP N（默认 3）
  - 输出 digest：每门课的 review_count / ratings / heat_top5 摘要 /
    今年任课教师（来自 courses_{session}，若提供）
产物 data/review_scope.json（AI 精读范围）+ data/review_digest.md（人读摘要）

用法:
  python3 scripts/rank/review_scope.py --filter data/filter_report.json \
      --reviews data/ustspace_reviews.json --session 2610
  python3 scripts/rank/review_scope.py ... --top 5
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

RE_CODE = re.compile(r"([A-Z]{3,4})\s*(\d{4}[A-Z]?)")


def main():
    ap = argparse.ArgumentParser(description="Step 4 评论精读范围生成")
    ap.add_argument("--filter", default=str(ROOT / "data" / "filter_report.json"))
    ap.add_argument("--reviews", default=str(ROOT / "data" / "ustspace_reviews.json"))
    ap.add_argument("--courses", default="", help="courses_{session}.json（今年教师，可选）")
    ap.add_argument("--session", default="")
    ap.add_argument("--top", type=int, default=3, help="非必修桶取 TOP N（默认 3）")
    ap.add_argument("--out", default=str(ROOT / "data" / "review_scope.json"))
    args = ap.parse_args()

    filter_rep = json.loads(Path(args.filter).read_text(encoding="utf-8-sig"))
    reviews = json.loads(Path(args.reviews).read_text(encoding="utf-8-sig"))

    kept = {c["code"]: c for c in filter_rep.get("kept", [])}
    rv_by_code = {}
    for c in reviews.get("courses", []):
        rv_by_code[f"{c.get('subject', '')} {c.get('number', '')}".strip()] = c

    # 今年任课教师（courses_{session} sections instructors）
    year_instructors = {}
    if args.courses and Path(args.courses).exists():
        sched = json.loads(Path(args.courses).read_text(encoding="utf-8-sig"))
        for c in sched.get("courses", []):
            code = f"{c.get('code', '')} {c.get('number', '')}".strip()
            insts = set()
            for sec in c.get("sections", []):
                insts.update(sec.get("instructors", []))
            if insts:
                year_instructors[code] = sorted(insts)

    # 分桶 → 精读范围
    buckets = {}
    for c in filter_rep.get("kept", []):
        buckets.setdefault(c.get("bucket_id"), []).append(c)
    scope, reasons = [], []
    for bid, items in buckets.items():
        items = sorted(items, key=lambda x: -(rv_by_code.get(x.get("code", ""), {})
                                              .get("review_count") or 0))
        required = any(x.get("category") in ("major_required", "cc_required")
                       for x in items)
        picked = items if required else items[:args.top]
        scope.extend(x["code"] for x in picked)
        reasons.append(f"{bid}: {'必修全读' if required else f'按评论数取 TOP {args.top}'}"
                       f"（{len(picked)}/{len(items)}）")
    scope = sorted(set(scope))

    # digest
    lines = ["# Step 4 评论精读范围（自动生成）\n"]
    for code in scope:
        r = rv_by_code.get(code)
        fl = kept.get(code, {})
        lines.append(f"\n## {code} | {fl.get('name', '')} | bucket={fl.get('bucket_id')}")
        if not r:
            lines.append("(无 ustspace 数据)")
            continue
        lines.append(f"review_count={r.get('review_count')} "
                     f"ratings={json.dumps(r.get('ratings', {}), ensure_ascii=False)}")
        if year_instructors.get(code):
            lines.append(f"今年教师(课表): {year_instructors[code]}")
        for h in r.get("heat_top5", [])[:3]:
            lines.append(f"  - [{h.get('semester', '')}] "
                         f"{', '.join(h.get('instructors', []))} | "
                         f"C{h.get('rating_content')}/T{h.get('rating_teaching')}/"
                         f"G{h.get('rating_grading')}/W{h.get('rating_workload')} | "
                         f"{(h.get('comment') or '')[:200]}")

    digest_md = ROOT / "data" / "review_digest.md"
    digest_md.write_text("\n".join(lines), encoding="utf-8")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope_count": len(scope),
        "scope": scope,
        "reasons": reasons,
        "digest_file": str(digest_md),
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                              encoding="utf-8")

    print(f"精读范围: {len(scope)} 门（过滤清单 {len(kept)} 门）")
    for r in reasons:
        print(f"  - {r}")
    print(f"产物 -> {args.out}")
    print(f"digest -> {digest_md}")


if __name__ == "__main__":
    main()
