#!/usr/bin/env python3
"""
最终报告渲染 — scripts/report/render.py
=======================================
把各 step 产物（profile/unmet/filter/scores/timetable_plan）按固定模板
（templates/reports/final_report.md.tpl）渲染为 output/final_report.md。
机械段落全自动；第 4 节（口碑精读）与第 7 节（下一步建议）留占位，由 AI
精读 review_summary.json 后补充；末尾选课时间提醒由 enrollment-dates-reminder
skill 附加。

用法:
  python3 scripts/report/render.py --plan plan-1 --session <SESSION>
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TPL = ROOT / "templates" / "reports" / "final_report.md.tpl"
OUT = ROOT / "output" / "final_report.md"


def load(p: Path):
    if not p.exists():
        sys.exit(f"错误: 缺少 {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def semester_label(session: str) -> str:
    if not session or len(session) < 4:
        return f"session {session}"
    yy, tail = session[:2], session[2:]
    year = f"20{yy}-20{int(yy) + 1}"
    name = {"0": "Fall", "5": "Winter", "20": "Spring", "30": "Summer"}.get(tail, "")
    return f"{year} {name}".strip()


# ── 机械段落生成 ─────────────────────────────────────────

def sec_profile(profile: dict, passed: dict, pre: dict, decisions: dict) -> dict:
    p1 = (decisions or {}).get("P1") or {}
    major = (profile.get("programs") or {}).get("first_major") or p1.get("major") or "-"
    return {
        "major": major,
        "track": p1.get("track") or "-",
        "admission_year": profile.get("admission_year") or "-",
        "year_of_study": profile.get("year_of_study") or "-",
        "credits_earned": profile.get("credits_earned") or 0,
        "cga": profile.get("cga") if profile.get("cga") is not None else "-",
        "courses_taken": len(passed.get("courses", [])),
        "pre_enrolled_summary": _pre_summary(pre),
    }


def _pre_summary(pre: dict) -> str:
    if not pre or not pre.get("courses"):
        return "无"
    n = len(pre["courses"])
    codes = ", ".join(c.get("code", "") for c in pre["courses"][:6])
    more = "…" if n > 6 else ""
    return f"{n} 门（{codes}{more}）"


def sec_unmet(unmet: dict) -> str:
    lines = []
    buckets = unmet.get("buckets", [])
    courses = unmet.get("courses", [])
    if not courses:
        return "（空）"
    by_bucket = {}
    for c in courses:
        by_bucket.setdefault(c.get("bucket_id", ""), []).append(c)
    for b in buckets:
        sub = by_bucket.get(b["bucket_id"], [])
        if not sub:
            continue
        cat = b.get("category", "")
        label = f"{b.get('label', b['bucket_id'])}（{b.get('quota', '?')} 门）"
        if cat.startswith("cc_") or cat == "free_elective":
            # CC/选修：折叠为栏位级说明
            need = [c["code"] for c in sub if not c.get("prereq_reference")]
            lines.append(f"- **{label}**：候选 {len(need)} 门（{', '.join(need[:6])}"
                         f"{'…' if len(need) > 6 else ''}）")
        else:
            for c in sub:
                ref = "（pre-req 参考，不参与排课）" if c.get("prereq_reference") else ""
                lines.append(f"- **{c['code']}** {c.get('name', '')} "
                             f"({c.get('credits')} cr){ref}")
    if not lines:
        return "（无未满足栏位）"
    return "\n".join(lines)


def sec_filter(fr: dict) -> str:
    kept = fr.get("kept", [])
    removed = fr.get("removed", [])
    overrides = fr.get("overrides") or []
    flags = {}
    for k in kept:
        for r in (k.get("filter_reasons") or []):
            if r and r != "user_overridden":
                flags[r] = flags.get(r, 0) + 1
    lines = [
        f"- 未修 {fr.get('input_count', '?')} → 今年开设保留 **{fr.get('kept_count', len(kept))}**"
        f" → 移除 {fr.get('removed_count', len(removed))}",
    ]
    if overrides:
        lines.append(f"- 用户豁免放回：{', '.join(overrides)}")
    if removed:
        lines.append(f"- 移除原因：{'; '.join(sorted(set(r.get('filter_reasons', [''])[0] if r.get('filter_reasons') else '?' for r in removed)))}")
    if flags:
        lines.append(f"- 保留但标记：{', '.join(f'{k}={v}' for k, v in sorted(flags.items()))}")
    return "\n".join(lines)


def sec_scores(scores: dict) -> str:
    lines = []
    buckets = scores.get("buckets", [])
    courses = {c["code"]: c for c in scores.get("courses", [])}
    for b in buckets:
        lines.append(f"\n**{b.get('label', b['bucket_id'])}**（quota={b.get('quota')}）：")
        for code in b.get("top_codes", []):
            c = courses.get(code)
            if not c:
                continue
            comp = c.get("score_components") or {}
            lines.append(f"  - {code}（{c.get('credits')} cr）**{c.get('score', 0):+.2f}**"
                         f"　A={comp.get('a', 0)} B={comp.get('b', 0)} "
                         f"C={comp.get('c', 0)} D={comp.get('d', 0)}"
                         f"　评论 n={c.get('review_count', 0)}")
    return "\n".join(lines)


def _plan_table(p: dict) -> str:
    lines = [f"- **{p.get('label', p.get('plan_id', ''))}**："
             f"{p.get('total_credits')} cr（{p.get('workload')}）"
             f"　CC {p.get('cc_credits')} / major {p.get('major_credits')} / "
             f"选修 {p.get('elective_credits')}"]
    for d in p.get("course_details", []):
        instructors = ", ".join(d.get("instructors") or []) or "-"
        lines.append(f"  - {d['code']} [{d.get('section', '')}] "
                     f"{d.get('datetime', '')} @ {d.get('room', '')} "
                     f"（{instructors}）")
    for n in (p.get("notes") or [])[:8]:
        lines.append(f"  - ! {n}")
    return "\n".join(lines)


def sec_plans(plans: dict, chosen: str) -> dict:
    all_plans = plans.get("plans", [])
    chosen_p = next((p for p in all_plans if p.get("plan_id") == chosen), None) \
        or (all_plans[0] if all_plans else None)
    overview = "\n".join(f"- **{p.get('plan_id')}** {p.get('total_credits')} cr "
                         f"（{p.get('workload')}）" for p in all_plans)
    detail = _plan_table(chosen_p) if chosen_p else "（无选定方案）"
    waivers = chosen_p.get("waiver_required", []) if chosen_p else []
    if waivers:
        wl = [f"  - **{w['code']}**：{w.get('prerequisites', '')}"
              f"{'　缺失: ' + ', '.join(w.get('missing', [])) if w.get('missing') else ''}"
              f"　（{w.get('note', '')}）" for w in waivers]
    else:
        wl = ["  （无，全部 pre-req 已满足或无需豁免）"]
    return {"plans_sections": overview, "chosen_plan_detail": detail,
            "waiver_section": "\n".join(wl)}


def main():
    ap = argparse.ArgumentParser(description="final_report.md 渲染")
    ap.add_argument("--plan", default="plan-1")
    ap.add_argument("--session", default="")
    args = ap.parse_args()

    profile = load(ROOT / "data" / "profile.json")
    passed = load(ROOT / "data" / "passed_courses.json")
    pre = load(ROOT / "data" / "pre_enrolled.json") \
        if (ROOT / "data" / "pre_enrolled.json").exists() else {}
    unmet = load(ROOT / "data" / "unmet_courses.json")
    fr = load(ROOT / "data" / "filter_report.json")
    scores = load(ROOT / "data" / "course_scores.json")
    plans = load(ROOT / "output" / "timetable_plan.json")

    decisions = {}
    dp = ROOT / "data" / "decisions.json"
    if dp.exists():
        decisions = json.loads(dp.read_text(encoding="utf-8"))

    pf = sec_profile(profile, passed, pre, decisions)
    pl = sec_plans(plans, args.plan)

    ctx = {
        "semester_label": semester_label(args.session or plans.get("session", "")),
        "top_per_bucket": scores.get("top_per_bucket", 3),
        "chosen_plan": pl and (args.plan if any(p.get("plan_id") == args.plan
                                                 for p in plans.get("plans", []))
                               else plans.get("plans", [{}])[0].get("plan_id", "plan-1")),
        "profile": pf,
        "unmet_sections": sec_unmet(unmet),
        "filter_summary": sec_filter(fr),
        "scores_sections": sec_scores(scores),
        "plans_sections": pl["plans_sections"],
        "chosen_plan_detail": pl["chosen_plan_detail"],
        "waiver_section": pl["waiver_section"],
    }

    text = TPL.read_text(encoding="utf-8")

    def fill(marker: str, value: str):
        return text.replace("{{" + marker + "}}", value)

    text = fill("semester_label", ctx["semester_label"])
    text = fill("top_per_bucket", str(ctx["top_per_bucket"]))
    text = fill("chosen_plan", ctx["chosen_plan"])
    text = fill("profile.major", ctx["profile"]["major"])
    text = fill("profile.track", ctx["profile"]["track"])
    text = fill("profile.admission_year", ctx["profile"]["admission_year"])
    text = fill("profile.year_of_study", str(ctx["profile"]["year_of_study"]))
    text = fill("profile.credits_earned", str(ctx["profile"]["credits_earned"]))
    text = fill("profile.cga", str(ctx["profile"]["cga"]))
    text = fill("profile.courses_taken", str(ctx["profile"]["courses_taken"]))
    text = fill("profile.pre_enrolled_summary", ctx["profile"]["pre_enrolled_summary"])
    text = fill("unmet_sections", ctx["unmet_sections"])
    text = fill("filter_summary", ctx["filter_summary"])
    text = fill("scores_sections", ctx["scores_sections"])
    text = fill("plans_sections", ctx["plans_sections"])
    text = fill("chosen_plan_detail", ctx["chosen_plan_detail"])
    text = fill("waiver_section", ctx["waiver_section"])

    left = [m for m in ("{{" + s + "}}" for s in
                        ("unmet_sections", "filter_summary", "scores_sections",
                         "plans_sections", "chosen_plan_detail", "waiver_section"))
            if m in text]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"渲染完成 -> {OUT}（选定 {ctx['chosen_plan']}）")
    if left:
        print(f"提示: 仍有未填充占位: {left}")
    print("AI 后续: 精读 review_summary.json 填第 4/7 节 + 附加选课时间提醒")


if __name__ == "__main__":
    main()
