#!/usr/bin/env python3
"""
USTspace 评论 → review_summary 基架 — scripts/rank/review_summary_build.py
=====================================================================
Step 4 产物 data/review_summary.json 的自动基架生成：从 USTspace 抓取产物
（data/ustspace_reviews.json）按四维评分/评论数/今年导师生成每条摘要的默认值
（grading/workload 档位、recommendation、instructors 名单），供 AI 精读时
覆盖 enrich——复杂语义（给分松紧、工作量、共识优缺点、导师风格）由模型输出补全。

数据流（无联网）：
  ustspace_reviews.json（评分/评论数/heat_top5/instructor_top5）
  + courses_{session}.json（今年导师名单，section.instructors）
  → review_summary.json（schema 合规基架）

评分档位启发（可按精读结果覆盖）：
  grading:  评分 grading ≥4.0 lenient / ≥3.0 fair / 否则 strict
  workload: 评分 workload ≥4.0 light / ≥3.0 medium / 否则 heavy（评分越高=越轻松）

用法:
  python3 scripts/rank/review_summary_build.py --session <SESSION>
  # 之后由 AI 精读覆盖 grading/workload/strengths/weaknesses/recommendation 等字段
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(p: Path) -> dict:
    if not p.exists():
        sys.exit(f"错误: 找不到 {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def this_year_instructors(code: str, schedule: dict) -> list:
    subj, num = code.split()
    for c in schedule.get("courses", []):
        if c.get("code") == subj and c.get("number") == num:
            instr = set()
            for s in c.get("sections", []) or []:
                instr.update(s.get("instructors", []) or [])
            return sorted(instr)
    return []


def scaffold_entry(c: dict, schedule: dict) -> dict:
    ratings = c.get("ratings") or {}
    vals = [ratings.get(k) for k in ("content", "teaching", "grading", "workload")]
    vals = [v for v in vals if isinstance(v, (int, float))]
    avg = round(sum(vals) / len(vals), 2) if vals else None

    g = ratings.get("grading")
    trend = "lenient" if g is not None and g >= 4.0 else \
            ("fair" if g is not None and g >= 3.0 else "strict")
    w = ratings.get("workload")
    wl = "light" if w is not None and w >= 4.0 else \
         ("medium" if w is not None and w >= 3.0 else "heavy")

    code = f"{c.get('subject', '')} {c.get('number', '')}".strip()
    rc = c.get("review_count") or 0
    rec = "recommended" if rc >= 1 else "mixed"

    return {
        "code": code,
        "name": c.get("name", ""),
        "review_count": rc,
        "summary": {
            "overall_rating": avg,
            "strengths": [],
            "weaknesses": [],
            "grading": {"trend": trend,
                        "note": "基架按评分档位生成，AI 精读后可覆盖"},
            "workload": {"level": wl, "note": "基架按评分档位生成，AI 精读后可覆盖"},
            "assessment": [],
            "recommendation": rec,
            "recent_trend": None,
            "evidence_note": "基架条目：由 review_summary_build.py 自动生成，需 AI 精读 heat_top5/instructor_top5 覆盖",
        },
        "instructors": [
            {"name": n, "teaching_this_year": True, "rating": None,
             "style": None, "notes": None}
            for n in this_year_instructors(code, schedule)
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="USTspace 评论 → review_summary 基架")
    ap.add_argument("--session", default="")
    ap.add_argument("--reviews", default=str(ROOT / "data" / "ustspace_reviews.json"))
    ap.add_argument("--output", default=str(ROOT / "data" / "review_summary.json"))
    args = ap.parse_args()
    if not args.session:
        sys.exit("错误: 缺少 --session（学期代码；运行中的学期可由 ustplan status 查询）")

    reviews = load(Path(args.reviews))
    schedule = load(ROOT / "data" / f"courses_{args.session}.json")

    # 幂等：已有文件保留 AI 精读过的条目（按 code 合并，精读优先），
    # 仅对新增课程生成基架；reviews 未收录的手动补充条目（如 0 评论必修）也保留。
    existing = {}
    out_dest = Path(args.output)
    if out_dest.exists():
        old = json.loads(out_dest.read_text(encoding="utf-8"))
        existing = {c.get("code"): c for c in old.get("courses", []) if c.get("code")}

    seen = set()
    out = []
    for c in reviews.get("courses", []):
        code = f"{c.get('subject', '')} {c.get('number', '')}".strip()
        if code in seen:
            continue  # 去重（reviews 内重复收录 + existing 合并叠加）
        seen.add(code)
        rc = c.get("review_count") or 0
        if rc == 0:
            # 0 评论课程：已有精读条目保留，无条目则跳过（不进基架）
            if code in existing:
                out.append(existing[code])
            continue
        if code in existing:
            out.append(existing[code])
        else:
            out.append(scaffold_entry(c, schedule))
    for code, entry in existing.items():
        if code not in seen:
            out.append(entry)
    out.sort(key=lambda x: -x["review_count"])

    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": args.session,
        "course_count": len(out),
        "courses": out,
    }
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    kept = sum(1 for e in out if e.get("d_rating") is not None or
               (e.get("summary") or {}).get("strengths"))
    print(f"review_summary 基架: {len(out)} 门 -> {dest}（保留已精读 {kept} 门）")
    print("提示: AI 需精读 heat_top5 + 今年导师评论，覆盖 grading/workload/"
          "strengths/weaknesses/recommendation 等字段")


if __name__ == "__main__":
    main()
