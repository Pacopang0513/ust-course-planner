#!/usr/bin/env python3
"""
Bucket 评分合成 — scripts/rank/bucket_score.py
==============================================
Step 5（新工作流）：按"栏位/bucket"独立评分，每个 bucket 取 TOP3，汇总为总表
data/course_scores.json（含 score_components 可追溯）。

评分公式：A+B+C+D（满分 100，可负分）。全部产品参数来自 config/ustplan.json
（scoring 节，schema 校验；缺省用内置默认），公式细节见 scripts/rank/scoring.py。

输入:
  data/filter_report.json    Step 3 保留清单（kept[]，含 bucket_id / prereq）
  data/ustspace_reviews.json Step 4 评论汇总（评分/热度/教授统计）
  data/review_summary.json   Step 4 AI 精读（D 组件 d_rating，可选）
  data/courses_{session}.json 本学期 schedule（本学期任课教授名单）
  data/unmet_courses.json    桶元数据（quota/label）+ pre_enrolled[]（预选课清单）
  data/pre_enrolled.json     （存在性门控）SIS 预选课 → 评分按 pre_enroll_boost 加权

用法:
  python3 scripts/rank/bucket_score.py --session <SESSION>
  python3 scripts/rank/bucket_score.py --filter data/filter_report.json \
      --reviews data/ustspace_reviews.json --summary data/review_summary.json \
      --pre-enrolled data/pre_enrolled.json
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from rank.scoring import (apply_level_bonus, apply_pre_enroll_boost,  # noqa: E402
                          b_weight, course_avg, heat_points,
                          level_bonus_pct, linear, professor_rating)
from harness.config import load as load_config  # noqa: E402


def load_json(p: Path) -> dict:
    if not p.exists():
        sys.exit(f"错误: 找不到 {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def norm_code(s: str) -> str:
    return re.sub(r"[\s.]+", "", str(s)).upper()


def _mean(vals: list):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None


def score_one(e: dict, ctx: dict) -> dict:
    """单门课评分（候选 kept[] 与预选课 pre_enrolled[] 共用）。
    ctx: {rv_by_code, d_by_code, sched_by_code, cfg_s 各项, pre_enroll_boost}"""
    code = e.get("code", "")
    s = ctx["s"]
    WA, WB, WC, WD = (float(s["weights"][k]) for k in ("a", "b", "c", "d"))
    baseline = float(s["baseline"])
    prof_weights = {k: float(v) for k, v in s["professor"].items()}
    tiers = s["heat_tiers"]
    min_reviews = int(s["min_reviews_for_score"])
    penalty = float(s["weight_penalty_per_missing"])
    bonus_map = {str(k): int(v) for k, v in s["level_bonus"].items()}
    boost = float(s.get("pre_enroll_boost") or 0.0)
    rv = ctx["rv_by_code"].get(norm_code(code))
    review_count = rv.get("review_count", 0) if rv else 0

    comp = {"a": None, "b": None, "c": None, "d": None,
            "a_weight": WA, "b_weight": WB, "c_weight": WC, "d_weight": WD,
            "course_avg": None, "professor_rating": None,
            "professor_review_count": 0}
    parts = []

    if review_count < min_reviews:
        parts.append(f"C: 总评论 {review_count} < {min_reviews} → 总分直接 0")
    else:
        avg = course_avg(rv.get("ratings", {})) if rv else None
        comp["course_avg"] = round(avg, 2) if avg is not None else None
        a = linear(avg, WA, baseline) if avg is not None else 0.0
        comp["a"] = round(a, 2)
        parts.append(f"A {comp['a']:+.1f}" + (f"(均分{avg:.2f})" if avg else "(新课无评分→0)"))

        # B：本学期任课教授（schedule sections instructors）→ 评论统计
        sc = ctx["sched_by_code"].get(code)
        this_year = set()
        for sec in (sc.get("sections") or []) if sc else []:
            this_year.update(sec.get("instructors") or [])
        stats = {(i.get("instructor")): i for i in (rv.get("instructor_stats") or [])}
        matched = [(name, stats[name]) for name in this_year if name in stats]
        if not matched:
            comp["b"] = 0.0
            parts.append("B 0.0(本学期教授无评论→新教授 wB=0)")
        else:
            total_n = sum(s_["review_count"] for _, s_ in matched)
            comp["professor_review_count"] = total_n
            wb = b_weight(total_n, WB, min_reviews, penalty)
            comp["b_weight"] = round(wb, 2)
            prof = _mean([professor_rating(s_, prof_weights) for _, s_ in matched])
            comp["professor_rating"] = round(prof, 2) if prof is not None else None
            b = linear(prof, wb, baseline) if prof is not None else 0.0
            comp["b"] = round(b, 2)
            parts.append(f"B {comp['b']:+.1f}(wB={wb:.1f}, 教授{total_n}条评论)")

        # C：评论热度档位（固定 25 权重）
        c = heat_points(review_count, tiers)
        comp["c"] = c
        comp["c_weight"] = WC
        parts.append(f"C {c:.0f}({review_count}条评论)")

        # D：AI 精读（本学期教授最近 5 条评论）
        d = ctx["d_by_code"].get(norm_code(code))
        comp["d"] = round(float(d), 2) if d is not None else 0.0
        if d is None:
            comp["d_weight"] = 0.0
            parts.append("D 0(AI 未精读)")
        else:
            parts.append(f"D {comp['d']:.1f}(AI 精读)")

    total = (comp["a"] or 0) + (comp["b"] or 0) + (comp["c"] or 0) + (comp["d"] or 0)
    pct = level_bonus_pct(e.get("number") or (code.split()[-1] if " " in code else ""),
                          e.get("category"), False, bonus_map)
    bonus_pts = apply_level_bonus(total, pct)
    if pct:
        parts.append(f"低阶必修 +{pct}% → +{bonus_pts}")
    score = round(total + bonus_pts, 2)

    # 预选课：评分后 ×(1+boost)（学校预选课多为必修/必读，默认 +40%）
    boost_pts = 0.0
    if e.get("pre_enrolled") and boost:
        boost_pts = apply_pre_enroll_boost(score, boost)
        score = round(score + boost_pts, 2)
        comp["pre_enroll_boost"] = round(boost, 2)
        parts.append(f"预选课 +{boost * 100:.0f}% → +{boost_pts}")

    return {
        "code": code,
        "name": e.get("name", ""),
        "credits": e.get("credits"),
        "category": e.get("category") or "pre_enrolled",
        "bucket_id": e.get("bucket_id") or "pre_enrolled",
        "bucket_quota": e.get("bucket_quota") or 1,
        "bucket_rank": 0,
        "score": score,
        "score_reason": "; ".join(parts),
        "score_components": {k: v for k, v in comp.items() if v is not None},
        "review_count": review_count,
        "review_confidence": ("high" if review_count >= 100 else
                              "medium" if review_count >= 20 else "low"),
        "open_this_year": bool(ctx["sched_by_code"].get(code)),
        "prerequisites": (e.get("prereq") or {}).get("text", ""),
        "prereq_met": (e.get("prereq") or {}).get("met"),
        "prereq_missing": (e.get("prereq") or {}).get("missing", []),
        "prereq_grading": (e.get("prereq") or {}).get("grading", []),
        "prereq_reference": False,
        "filter_reasons": e.get("filter_reasons", []),
        "pre_enrolled": bool(e.get("pre_enrolled")),
    }


def main():
    ap = argparse.ArgumentParser(description="Bucket 评分合成（Step 5，A+B+C+D + TOP3）")
    ap.add_argument("--filter", default=str(ROOT / "data" / "filter_report.json"))
    ap.add_argument("--reviews", default=str(ROOT / "data" / "ustspace_reviews.json"))
    ap.add_argument("--summary", default=str(ROOT / "data" / "review_summary.json"))
    ap.add_argument("--unmet", default=str(ROOT / "data" / "unmet_courses.json"))
    ap.add_argument("--pre-enrolled", default=str(ROOT / "data" / "pre_enrolled.json"),
                    help="SIS 预选课文件（存在则评分按 pre_enroll_boost 加权并加入栏位排名）")
    ap.add_argument("--session", default="")
    ap.add_argument("--output", default=str(ROOT / "data" / "course_scores.json"))
    ap.add_argument("--config", default=None, help="配置文件（默认 config/ustplan.json）")
    args = ap.parse_args()
    if not args.session:
        sys.exit("错误: 缺少 --session（学期代码；运行中的学期可由 ustplan status 查询）")

    cfg = load_config(path=args.config)
    s = cfg["scoring"]
    top_n = int(load_config(path=args.config)["defaults"]["top_per_bucket"])

    kept = load_json(Path(args.filter)).get("kept", [])
    reviews = load_json(Path(args.reviews))
    rv_by_code = {norm_code(c.get("subject", "") + c.get("number", "")): c
                  for c in reviews.get("courses", [])}
    summary_path = Path(args.summary)
    d_by_code = {}
    if summary_path.exists():
        for c in load_json(summary_path).get("courses", []):
            if c.get("d_rating") is not None:
                d_by_code[norm_code(c.get("code", ""))] = c["d_rating"]
    unmet_path = Path(args.unmet)
    buckets_meta = {}
    pre_list = []
    if unmet_path.exists():
        unmet_data = load_json(unmet_path)
        buckets_meta = {b["bucket_id"]: b
                        for b in unmet_data.get("buckets", [])}
        if Path(args.pre_enrolled).exists():
            pre_list = unmet_data.get("pre_enrolled", [])
    sched = load_json(ROOT / "data" / f"courses_{args.session}.json")
    sched_by_code = {f"{c.get('code', '')} {c.get('number', '')}".strip(): c
                     for c in sched.get("courses", [])}

    ctx = {"rv_by_code": rv_by_code, "d_by_code": d_by_code,
           "sched_by_code": sched_by_code, "s": s}

    scored, by_bucket = [], {}
    for e in kept:
        code = e.get("code", "")
        if e.get("prereq_reference"):
            continue  # 参考课程不评分
        item = score_one(e, ctx)
        scored.append(item)
        by_bucket.setdefault(item["bucket_id"], []).append(item)

    # 预选课：学校预选课程（confirmed/pending）参与所在栏位排名，评分按
    # pre_enroll_boost 加权（config → scoring，默认 +40%）。优先级仍低 → 方案建议
    # drop（step6；必修预选课除外）。
    pre_scored = 0
    for e in pre_list:
        e = dict(e)
        e["pre_enrolled"] = True
        item = score_one(e, ctx)
        scored.append(item)
        by_bucket.setdefault(item["bucket_id"], []).append(item)
        pre_scored += 1
    if pre_list:
        print(f"预选课评分: {pre_scored} 门（+{float(s.get('pre_enroll_boost') or 0) * 100:.0f}% 加权）")

    # 每 bucket 按分数降序 → TOP N（config: top_per_bucket，默认 3）；
    # 其余进 ranked_out（备选池，供 must-take/多样性/补学分使用，评分与字段完整保留）
    top3, ranked_out, buckets_out = [], [], []
    for bid, items in sorted(by_bucket.items()):
        items.sort(key=lambda x: -x["score"])
        for i, it in enumerate(items, 1):
            it["bucket_rank"] = i if i <= top_n else None
            if i <= top_n:
                top3.append(it)
            else:
                ranked_out.append(it)
        meta = buckets_meta.get(bid, {})
        buckets_out.append({
            "bucket_id": bid,
            "label": meta.get("label", "预选课" if bid == "pre_enrolled" else bid),
            "category": items[0]["category"],
            "quota": meta.get("quota", items[0].get("bucket_quota") or 1),
            "note": meta.get("note", "") or
            ("学校预选课（Pre-Enroll），评分按 pre_enroll_boost 加权" if bid == "pre_enrolled" else ""),
            "top_codes": [i["code"] for i in items[:top_n]],
        })

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": args.session,
        "bucket_count": len(buckets_out),
        "top_per_bucket": top_n,
        "buckets": buckets_out,
        "courses": top3,
        "ranked_out": ranked_out,
        "source_files": {
            "filter": str(Path(args.filter).relative_to(ROOT) if Path(args.filter).is_relative_to(ROOT) else args.filter),
            "reviews": str(Path(args.reviews).relative_to(ROOT) if Path(args.reviews).is_relative_to(ROOT) else args.reviews),
        },
    }
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"评分完成: {len(scored)} 门 → {len(top3)} 门（每 bucket TOP{top_n}）+ "
          f"{len(ranked_out)} 门备选(ranked_out)")
    for b in buckets_out:
        top = [i["code"] for i in by_bucket[b["bucket_id"]][:top_n]]
        print(f"  {b['bucket_id']:28} quota={b['quota']}: {', '.join(top)}")
    print(f"产物 -> {dest}")


if __name__ == "__main__":
    main()
