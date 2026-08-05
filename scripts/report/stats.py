#!/usr/bin/env python3
"""
运行时产物统计汇总 — scripts/report/stats.py
===========================================
把各 Step 产物的机械性分析（分类计数 / Top 列表 / 移除原因归类 / 方案摘要）
固化成一个脚本，供 AI 与用户快速查看，避免每次内联临时分析。

用法:
  python3 scripts/report/stats.py                 # 汇总全部产物
  python3 scripts/report/stats.py --unmet         # 只看未修统计
  python3 scripts/report/stats.py --filter        # 只看过滤统计
  python3 scripts/report/stats.py --scores-top 15 # 指定最终排名条数（默认 15）

读取文件（均可覆盖）:
  --unmet data/unmet_courses.json --candidates data/candidate_rank.json
  --filter data/filter_report.json --reviews data/ustspace_reviews.json
  --summary data/review_summary.json --scores data/course_scores.json
  --plans output/timetable_plan.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path):
    if not path.exists():
        sys.exit(f"错误: 找不到 {path}（先运行对应步骤的脚本）")
    return json.loads(path.read_text(encoding="utf-8"))


def _first_reason(reasons: list) -> str:
    """过滤理由的首因归类（去掉 user_overridden 前缀外的语义）"""
    reasons = [r for r in (reasons or []) if r != "user_overridden"]
    return reasons[0] if reasons else "kept"


# ── 各产物统计 ─────────────────────────────────────────────
def stats_unmet(d: dict) -> str:
    c = Counter(x["category"] for x in d["courses"])
    lines = [
        f"未修课程（{d.get('program','')}，{d.get('intake_year','')} 入学，目标 {d.get('graduation_target_credits',120)} 学分）",
        f"  合计 {len(d['courses'])} 门: "
        f"必修 {c.get('major_required',0)} / 选修 {c.get('major_elective',0)} / "
        f"CC必修 {c.get('cc_required',0)} / CC选修 {c.get('cc_elective',0)} / "
        f"自由 {c.get('free_elective',0)}",
    ]
    major = [x for x in d["courses"] if x["category"].startswith("major")]
    if major:
        lines.append("  major 明细:")
        for x in major:
            lines.append(f"    {x['category']:15} {x['code']:12} {x['name']} ({x['credits']} cr)")
    return "\n".join(lines)


def stats_candidates(d: dict) -> str:
    c = Counter(x["category"] for x in d["courses"])
    lines = [
        f"候选排名（top_n={d.get('top_n')}，总候选 {d.get('total_candidates')}，"
        f"保送后保留 {len(d['courses'])}）",
        f"  分类: " + ", ".join(f"{k}={v}" for k, v in sorted(c.items())),
        f"  候补池 truncated: {len(d.get('truncated', []))} 门",
    ]
    return "\n".join(lines)


def stats_filter(d: dict) -> str:
    rc = Counter(_first_reason(x["filter_reasons"]) for x in d["removed"])
    lines = [
        f"过滤报告（session {d.get('session')}）: 输入 {d['input_count']} → "
        f"保留 {d['kept_count']} / 移除 {d['removed_count']}",
        "  移除原因:",
    ]
    for reason, n in rc.most_common():
        lines.append(f"    {reason}: {n}")
    over = d.get("overrides") or []
    if over:
        lines.append(f"  用户豁免放回 user_overridden: {', '.join(over)}")
    flags = Counter()
    for k in d["kept"]:
        for r in k["filter_reasons"]:
            if r != "user_overridden":
                flags[r] += 1
    if flags:
        lines.append("  保留但标记: " + ", ".join(f"{k}={v}" for k, v in flags.items()))
    return "\n".join(lines)


def stats_reviews(d: dict) -> str:
    n = d.get("course_count") or len(d.get("courses", []))
    failed = d.get("failed") or []
    lines = [f"USTspace 评论抓取: {n} 门"]
    if failed:
        lines.append("  失败标记 failed[]: " + ", ".join(f"{x.get('code')}({x.get('reason')})" for x in failed))
    return "\n".join(lines)


def stats_summary(d: dict) -> str:
    lines = [f"review_summary（session {d.get('session')}）: {d.get('course_count') or len(d.get('courses', []))} 门"]
    for x in d.get("courses", []):
        s = x.get("summary") or {}
        rating = s.get("overall_rating")
        rec = s.get("recommendation") or "-"
        trend = (s.get("grading") or {}).get("trend") or "-"
        wl = (s.get("workload") or {}).get("level") or "-"
        lines.append(
            f"  {x['code']:12} {x.get('name','')[:28]:28} n={x.get('review_count',0):4} "
            f"rating={rating} 推荐={rec:6} 给分={trend:6} 工作量={wl}")
    return "\n".join(lines)


def stats_scores(d: dict, top: int) -> str:
    lines = [f"最终合成排名（前 {top}）: 规则分60% + 口碑40%"]
    for i, x in enumerate(d["courses"][:top], 1):
        lines.append(
            f"  {i:2}. {x['code']:12} {x.get('name','')[:30]:30} "
            f"score={x['score']:.2f} conf={x['review_confidence']:6} n={x.get('review_count',0)}")
    return "\n".join(lines)


def stats_plans(d: dict) -> str:
    lines = [f"课程表方案（session {d.get('session')}）: {len(d.get('plans', []))} 套"]
    for p in d.get("plans", []):
        lines.append(
            f"  {p['plan_id']} ({p.get('label','')}) {p['total_credits']} 学分 {p['workload']} "
            f"CC {p['cc_credits']} / major {p['major_credits']} / 选修 {p['elective_credits']} "
            f"no_conflict={p['no_conflict']}")
        for c in p.get("course_details", []):
            lines.append(
                f"    {c['code']:12} [{c.get('section',''):5}] {c.get('datetime',''):28} "
                f"{', '.join(c.get('instructors',[]) or [])}")
        for note in p.get("notes", []):
            lines.append(f"    ! {note}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="运行时产物统计汇总")
    ap.add_argument("--unmet", default=str(ROOT / "data" / "unmet_courses.json"))
    ap.add_argument("--candidates", default=str(ROOT / "data" / "candidate_rank.json"))
    ap.add_argument("--filter", default=str(ROOT / "data" / "filter_report.json"))
    ap.add_argument("--reviews", default=str(ROOT / "data" / "ustspace_reviews.json"))
    ap.add_argument("--summary", default=str(ROOT / "data" / "review_summary.json"))
    ap.add_argument("--scores", default=str(ROOT / "data" / "course_scores.json"))
    ap.add_argument("--plans", default=str(ROOT / "output" / "timetable_plan.json"))
    ap.add_argument("--scores-top", type=int, default=15)
    ap.add_argument("--only", choices=["unmet", "candidates", "filter", "reviews",
                                       "summary", "scores", "plans"])
    args = ap.parse_args()

    sections = [
        ("unmet", "未修课程", stats_unmet, args.unmet),
        ("candidates", "候选排名", stats_candidates, args.candidates),
        ("filter", "过滤报告", stats_filter, args.filter),
        ("reviews", "评论抓取", stats_reviews, args.reviews),
        ("summary", "口碑摘要", stats_summary, args.summary),
        ("scores", "合成排名", stats_scores, args.scores),
        ("plans", "课表方案", stats_plans, args.plans),
    ]
    for key, title, fn, path in sections:
        if args.only and args.only != key:
            continue
        d = _load(Path(path))
        print(f"\n===== {title} =====")
        if key == "scores":
            print(fn(d, args.scores_top))
        else:
            print(fn(d))


if __name__ == "__main__":
    main()
