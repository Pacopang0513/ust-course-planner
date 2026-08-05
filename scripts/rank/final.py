#!/usr/bin/env python3
"""
候选课程合成排名 — scripts/rank/final.py
========================================
Step 5：把过滤后的候选（filter_report.kept）+ USTspace 评论信号
（ustspace_reviews.json）合成为最终吸引力 + 置信度，写入
data/course_scores.json（对齐 templates/schemas/course_scores.schema.json）。

分数构成:
  吸引力 (0-100) = 规则分(60%) + USTspace 口碑(40%)
    口碑 = 课程整体评分归一化(40%) + 评论热度的经验分(60%)
  置信度 = 评论数分档: >=100 high / >=20 medium / >=1 low / 0 none

用法:
  python3 scripts/rank/final.py --filter data/filter_report.json
  python3 scripts/rank/final.py --filter data/filter_report.json \
      --reviews data/ustspace_reviews.json --output data/course_scores.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _heat_score(reviews: dict, code: str) -> dict:
    """code 如 'COMP 2011' → (口碑分, 置信度档, 评论数)"""
    for c in reviews.get("courses", []):
        if f"{c.get('subject', '')} {c.get('number', '')}".strip() == code:
            rc = c.get("review_count", 0) or 0
            ratings = c.get("ratings") or {}
            vals = [ratings.get(k) for k in ("content", "teaching", "grading", "workload")]
            vals = [v for v in vals if isinstance(v, (int, float))]
            avg = sum(vals) / len(vals) if vals else 0.0
            reputation = min(100.0, avg / 5.0 * 100)
            heat = min(100.0, rc / 20.0 * 5) if rc else 0.0  # 400 条评论封顶 100 分
            word_of_mouth = reputation * 0.4 + heat * 0.6
            if rc >= 100:
                conf = "high"
            elif rc >= 20:
                conf = "medium"
            elif rc >= 1:
                conf = "low"
            else:
                conf = "none"
            return round(word_of_mouth, 2), conf, rc, round(avg, 2)
    return 0.0, "none", 0, 0.0


def main():
    ap = argparse.ArgumentParser(description="候选课程合成排名")
    ap.add_argument("--filter", default=str(ROOT / "data" / "filter_report.json"))
    ap.add_argument("--reviews", default=str(ROOT / "data" / "ustspace_reviews.json"))
    ap.add_argument("--output", default=str(ROOT / "data" / "course_scores.json"))
    args = ap.parse_args()

    flt_path = Path(args.filter)
    if not flt_path.exists():
        sys.exit(f"错误: 找不到 {flt_path}（先运行 Step 3 filter.py）")
    flt = json.loads(flt_path.read_text(encoding="utf-8"))
    reviews = {}
    if Path(args.reviews).exists():
        reviews = json.loads(Path(args.reviews).read_text(encoding="utf-8"))

    courses = []
    for c in flt.get("kept", []):
        code = c.get("code", "")
        wom, conf, rc, avg = _heat_score(reviews, code)
        try:
            rule = float(c.get("rule_score") or 0.0)
        except (TypeError, ValueError):
            rule = 0.0
        score = round(rule * 0.6 + wom * 0.4, 2)
        name = c.get("name") or ""
        credits = c.get("credits")
        courses.append({
            "code": code,
            "name": name,
            "credits": credits if isinstance(credits, (int, float)) else None,
            "score": score,
            "score_reason": (
                f"rule={rule:.1f}(60%), ustspace口碑={wom:.1f}(40%), "
                f"均分={avg:.2f}/5, 评论数={rc}"
            ),
            "review_count": rc,
            "review_confidence": conf if conf != "none" else "low",
            "open_this_year": True,
            "attractiveness": score,
            "confidence_score": {"high": 90, "medium": 60, "low": 30, "none": 10}[conf],
            "category": c.get("category"),
        })
    courses.sort(key=lambda x: -x["score"])

    out = {
        "courses": courses,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"合成排名完成: {len(courses)} 门课 -> {dest}")
    for c in courses[:10]:
        print(f"  {c['score']:6.2f}  {c['code']:14} {c['review_confidence']:6} "
              f"n={c['review_count']:4}  {(c.get('name') or '')[:36]}")


if __name__ == "__main__":
    main()
