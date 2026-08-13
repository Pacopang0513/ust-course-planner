#!/usr/bin/env python3
"""
历史学期教授对照 — scripts/rank/history_compare.py
==================================================
Step 5.5（step5 与 step6 之间，可选）：对照前两个学期的开课与授课教授口碑，
识别"本学期教授评分明显低于往期"的候选课，输出 data/history_compare.json，
供 step6（planner.py）降权（effective_score）与延后建议（defer advice）。

逻辑（2026-08 新增，产品参数在 config → history）:
  1. 候选 = course_scores.json 的 courses[]（每 bucket TOP3）+ ranked_out[]
     （这些课已通过 step3 匹配，必然本学期开设）
  2. 对每门候选：查前两学期课表（data/courses_{prev}.json，由后台 job
     wcq_history 抓取；缺失 → 该学期跳过）是否开设
  3. 开设 → 取该学期 section 授课教授 → 计算该教授在【这门课】上的评分
     （数据源优先 cache/ustspace/raw/{CODE}.json 逐条评论，回退
     data/ustspace_reviews.json 的 instructor_top5 聚合；默认限定该学期
     评论，不足回退全量）
  4. 与本学期教授评分对比：往期最高 − 本学期 ≥ threshold（默认 0.5）→ 记录
     {code, prev_sessions, best_prev, this_year, delta, penalty_pct,
     next_occurrence}（next_occurrence = 该学期同序下一轮，如 2530 Spring →
     2630 Spring；四个学期循环，上年度的同 term 课程可作下年度同 term 参考）
  5. 未开设 / 无评分数据 → 不记录（不打扰，feature 静默降级）

用法:
  python3 scripts/rank/history_compare.py --session 2610 \
      --scores data/course_scores.json --reviews data/ustspace_reviews.json
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from harness.config import load as load_config  # noqa: E402
from harness.config import previous_sessions, semester_of_session  # noqa: E402
from rank.scoring import professor_rating  # noqa: E402


def load_json(p: Path) -> dict:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def norm_code(s: str) -> str:
    return re.sub(r"[\s.]+", "", str(s or "")).upper()


def sem_matches(sem_label: str, session: str, cfg: dict = None) -> bool:
    """评论 semester 文本是否属于 session 对应学期（容错：年份只比对年份前缀，
    学期名全词匹配）。如 session 2530（2025-26 Spring）→ '2025-26 Spring' /
    '2025 Spring' 均命中。"""
    label = str(sem_label or "")
    if not label:
        return False
    sem = (cfg or load_config()).get("semesters") or {}
    want_term = semester_of_session(session, cfg)
    if not want_term:
        return False
    if want_term not in label:
        return False
    yy = int(str(session)[:2]) + 2000
    return str(yy) in label or str(yy + 1) in label


def session_label(session: str, cfg: dict = None) -> str:
    """2530 → '2025-26 Spring'"""
    s = str(session or "")
    if not re.fullmatch(r"\d{4}", s):
        return s
    yy = int(s[:2]) + 2000
    sem = semester_of_session(s, cfg)
    return f"{yy}-{str(yy + 1)[2:]} {sem}" if sem else s


def next_occurrence(target: str, prev: str, cfg: dict = None) -> str:
    """prev 学期在 target 之后的最近一次出现（四学期循环）。
    target 2610(Fall) + prev 2530(Spring) → 2630；target 2630(Spring) +
    prev 2610(Fall) → 2710。"""
    sem = (cfg or load_config()).get("semesters") or {}
    codes = sorted(sem.values())
    yy_t, tt_t = int(str(target)[:2]), int(str(target)[2:])
    tt_p = int(str(prev)[2:])
    if tt_p not in codes:
        return ""
    next_yy = yy_t if tt_p > tt_t else yy_t + 1
    return f"{next_yy:02d}{tt_p:02d}"


# ── 评论数据源 ──────────────────────────────────────────────

def _rating_of(rev: dict, prof_weights: dict = None):
    """单条评论 → 教授四维加权评分（与 scoring.professor_rating 同公式）"""
    ratings = {k: rev.get(f"rating_{k}") for k in
               ("content", "teaching", "grading", "workload")}
    return professor_rating({"ratings": ratings}, prof_weights)


def load_raw_reviews(code: str, raw_dir: Path) -> list:
    """cache/ustspace/raw/{CODE}.json → 评论列表（含 instructors/semester/rating_*）；
    缺失/损坏返回 None（调用方回退 instructor_top5）"""
    p = raw_dir / f"{norm_code(code)}.json"
    d = load_json(p)
    if not d or not isinstance(d.get("reviews"), list):
        return None
    return d["reviews"]


def instructor_course_ratings(code: str, reviews_doc: dict,
                              raw_dir: Path, prof_weights: dict = None,
                              semester: str = "") -> tuple:
    """教授在【这门课】上的评分表 → (ratings, used_semester_filter)
    ratings: {instructor: (mean_rating, review_count)}
    优先 raw 逐条评论；semester 非空时先限定该学期，不足回退全量。
    回退 reviews_doc.instructor_top5（含 semester + rating_*）。"""
    raw = load_raw_reviews(code, raw_dir)
    per = {}
    if raw is not None:
        for rev in raw:
            if semester and not sem_matches(rev.get("semester", ""), semester):
                continue
            for i in (rev.get("instructors") or []):
                name = i.get("name")
                if not name:
                    continue
                r = _rating_of(rev, prof_weights)
                if r is None:
                    continue
                per.setdefault(name, []).append(r)
    if not per and semester:
        raw = load_raw_reviews(code, raw_dir)
        if raw is not None:
            for rev in raw:
                for i in (rev.get("instructors") or []):
                    name = i.get("name")
                    if not name:
                        continue
                    r = _rating_of(rev, prof_weights)
                    if r is None:
                        continue
                    per.setdefault(name, []).append(r)
    if per:
        out = {}
        for name, vals in per.items():
            out[name] = (round(sum(vals) / len(vals), 2), len(vals))
        return out, bool(semester)

    # 回退 instructor_top5（无 raw 时；每导师至多 5 条热度评论）
    if not reviews_doc:
        return {}, False
    top5 = {}
    for c in reviews_doc.get("courses", []):
        if norm_code(c.get("subject", "") + c.get("number", "")) != norm_code(code):
            continue
        top5 = {t.get("instructor"): (t.get("top5") or [])
                for t in (c.get("instructor_top5") or [])}
        break
    per = {}
    filtered = False
    for name, revs in top5.items():
        if not name:
            continue
        vals = []
        for rev in revs:
            if semester and not sem_matches(rev.get("semester", ""), semester):
                continue
            r = _rating_of(rev, prof_weights)
            if r is None:
                continue
            vals.append(r)
        if not vals and semester:
            for rev in revs:
                r = _rating_of(rev, prof_weights)
                if r is None:
                    continue
                vals.append(r)
        elif vals:
            filtered = True
        if vals:
            per[name] = (round(sum(vals) / len(vals), 2), len(vals))
    return per, filtered


def session_instructors(session: str, code: str, data_dir: Path) -> list:
    """某学期课表 courses_{session}.json → 该课程 section 授课教授名单；
    未开设/数据缺失返回 None（区分：[] = 开设但无教授信息）。"""
    d = load_json(data_dir / f"courses_{session}.json")
    if d is None:
        return None
    for c in d.get("courses", []):
        if norm_code(f"{c.get('code', '')} {c.get('number', '')}".strip()) \
                != norm_code(code):
            continue
        profs = sorted({i for s in (c.get("sections") or [])
                        for i in (s.get("instructors") or [])})
        return profs
    return []


# ── 主逻辑 ──────────────────────────────────────────────────

def compute(session: str, scores: dict, reviews_doc: dict,
            raw_dir: Path, data_dir: Path, cfg: dict = None) -> dict:
    cfg = cfg or load_config()
    hist = cfg.get("history") or {}
    threshold = float(hist.get("threshold", 0.5))
    prof_weights = {k: float(v) for k, v in
                    ((cfg.get("scoring") or {}).get("professor") or {}).items()} or None
    prevs = previous_sessions(session, cfg)
    if not prevs:
        return {"previous_sessions": [], "advice": [], "checked": 0, "matched": 0}

    # 候选：TOP3（courses[]）+ 备选池（ranked_out[]）
    codes = [c.get("code", "") for c in scores.get("courses", [])]
    for c in scores.get("ranked_out", []):
        if c.get("code") not in codes:
            codes.append(c.get("code", ""))
    codes = [c for c in codes if c]

    advice, checked = [], 0
    for code in codes:
        checked += 1
        entry = {"code": code, "offered_prev": False, "prev_sessions": [],
                 "this_year": None, "best_prev": None, "delta": None,
                 "penalty_pct": None, "next_occurrence": None, "note": ""}
        this_ratings, _ = instructor_course_ratings(code, reviews_doc,
                                                    raw_dir, prof_weights)
        this_profs = session_instructors(session, code, data_dir)
        if this_profs is None:
            continue  # 本学期课表缺失（不应发生，step6 会处理）
        this_vals = [r for p, (r, _) in this_ratings.items() if p in this_profs]
        if not this_vals:
            continue  # 本学期教授无评论 → 无从比较
        this_rating = round(sum(this_vals) / len(this_vals), 2)
        entry["this_year"] = {
            "session": session, "label": session_label(session, cfg),
            "professors": this_profs,
            "rating": this_rating,
            "review_count": sum(n for p, (_, n) in this_ratings.items()
                                if p in this_profs),
        }

        best = None
        for prev in prevs:
            profs = session_instructors(prev, code, data_dir)
            if profs is None:
                continue  # 该学期数据缺失
            if not profs:
                continue  # 该学期未开设
            entry["offered_prev"] = True
            ratings, _ = instructor_course_ratings(code, reviews_doc,
                                                   raw_dir, prof_weights,
                                                   semester=prev)
            vals = [r for p, (r, _) in ratings.items() if p in profs]
            if not vals:
                continue
            rating = round(sum(vals) / len(vals), 2)
            n = sum(cnt for p, (_, cnt) in ratings.items() if p in profs)
            cand = {"session": prev, "label": session_label(prev, cfg),
                    "professors": profs, "rating": rating, "review_count": n}
            entry["prev_sessions"].append(cand)
            if best is None or rating > best["rating"]:
                best = cand
        if best is None:
            continue
        delta = round(best["rating"] - this_rating, 2)
        entry["best_prev"] = best
        entry["delta"] = delta
        if delta >= threshold:
            penalty = float(hist.get("penalty_pct", 10))
            entry["penalty_pct"] = penalty
            entry["next_occurrence"] = {
                "session": next_occurrence(session, best["session"], cfg),
                "label": session_label(next_occurrence(session, best["session"], cfg), cfg),
            }
            entry["note"] = (f"{code} 本学期教授 {', '.join(this_profs)} 评分 "
                             f"{this_rating}；{best['label']} 由 "
                             f"{', '.join(best['professors'])} 授课评分 "
                             f"{best['rating']}（提升 {delta:+.2f}）→ 评分 "
                             f"-{penalty:.0f}%，可考虑 "
                             f"{entry['next_occurrence']['label']} 再修")
        else:
            entry["note"] = "往期提升未达阈值，不降权"
        advice.append(entry)

    matched = sum(1 for a in advice if a.get("penalty_pct"))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": session,
        "threshold": threshold,
        "previous_sessions": prevs,
        "data_sources": {p: f"data/courses_{p}.json" for p in prevs},
        "checked": checked,
        "matched": matched,
        "advice": advice,
    }


def main():
    ap = argparse.ArgumentParser(description="历史学期教授对照（step5 与 step6 之间）")
    ap.add_argument("--session", default="")
    ap.add_argument("--scores", default=str(ROOT / "data" / "course_scores.json"))
    ap.add_argument("--reviews", default=str(ROOT / "data" / "ustspace_reviews.json"))
    ap.add_argument("--output", default=str(ROOT / "data" / "history_compare.json"))
    args = ap.parse_args()
    if not args.session:
        sys.exit("错误: 缺少 --session（学期代码；运行中的学期可由 ustplan status 查询）")
    scores = load_json(Path(args.scores))
    if scores is None:
        sys.exit(f"错误: 找不到 {args.scores}（先完成 step5）")
    reviews = load_json(Path(args.reviews)) or {}
    out = compute(args.session, scores, reviews,
                  ROOT / "cache" / "ustspace" / "raw", ROOT / "data")
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"历史对照: 候选 {out['checked']} 门，前两学期 {', '.join(out['previous_sessions'])}，"
          f"触发降权 {out['matched']} 门 -> {dest}")
    for a in out["advice"]:
        if a.get("penalty_pct"):
            print(f"  ! {a['note']}")


if __name__ == "__main__":
    main()
