#!/usr/bin/env python3
"""
课程表编排 — scripts/rank/planner.py
====================================
Step 6：按 Step 5 排名（data/course_scores.json）与本学年 Class Schedule
（data/courses_{session}.json，wcq 抓取产物，每 section 含 datetime/instructors）
生成 N 套无时间冲突的课程表方案 → output/timetable_plan.json。

严格按 schedule 排课：每门课从 schedule sections 中选一个与已选课程无冲突的
section（首个可用，确定性输出）；TBA 无时间 section 不参与排课，对应课程记入
notes。section 的 datetime / room / instructors 原样记录在 course_details。

方案差异（固定 PLAN_PROFILES）：
  plan-1  低学分（目标 12-13，必修优先，major 配比高）
  plan-2  中学分（目标 15-16，均衡）
  plan-3  高学分（目标 17-18，CC 配比高）

硬约束：学分 12-18 / 不重复 / 不含已修课 / 每套先满足专业必修（major_required）。
两阶段选课：phase1 全必修（按排名），phase2 按方案偏好补足学分；
若两套方案课程完全相同，做一次确定性多样性调整（换出低分非必修，换入高分
同类别候选），保证 N 套方案可区分。

phase4.5 硬插：--must-take 指定的课程在 phase0 优先入排（不满足 12-18/冲突/
不在 pool 时记入 notes 由 AI 取舍），输出 must_take_inserted。

用法:
  python3 scripts/rank/planner.py --scores data/course_scores.json --session 2610
  python3 scripts/rank/planner.py --scores data/course_scores.json --session 2610 \
      --passed data/passed_courses.json --plans 3 --top 20 --output output/timetable_plan.json
  python3 scripts/rank/planner.py --scores data/course_scores.json --session 2610 \
      --must-take "COMP 3111" "MATH 2023"      # 硬插课程（phase4.5）
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from wcq.conflict import parse_slots  # noqa: E402  (复用 schedule 时间槽解析)

MAX_CREDITS = 18
MIN_CREDITS = 12

# 固定方案模板（顺序即优先级）
PLAN_PROFILES = [
    {"plan_id": "plan-1", "target_min": 12, "target_max": 13,
     "phase2": "all", "label": "低学分 12-13，必修优先（major 配比高）"},
    {"plan_id": "plan-2", "target_min": 15, "target_max": 16,
     "phase2": "all", "label": "中学分 15-16，均衡"},
    {"plan_id": "plan-3", "target_min": 17, "target_max": 18,
     "phase2": "cc_first", "label": "高学分 17-18，CC 配比高"},
]
CATEGORY_ORDER = {"cc_required": 0, "cc_elective": 1,
                  "major_elective": 2, "free_elective": 3}


def load_json(p: Path) -> dict:
    if not p.exists():
        sys.exit(f"错误: 找不到 {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def workload(total: float) -> str:
    if total >= 17:
        return "heavy"
    if total >= 15:
        return "medium"
    return "light"


def build_pool(scores: dict, schedule: dict, passed: set, top: int) -> list:
    """course_scores 前 top 名 → 池（含 schedule section/slots，学分取 schedule units）。
    major_required/major_elective 即使分数在 top 之外也强制入池（防必修被 CC 池挤出）。"""
    sched = {f"{c.get('code', '')} {c.get('number', '')}".strip(): c
             for c in schedule.get("courses", [])}

    def entry(c: dict) -> dict:
        sc = sched.get(c.get("code", ""))
        if sc is None:
            return None
        credits = sc.get("units")
        if not isinstance(credits, (int, float)):
            return None
        secs = []
        for s in sc.get("sections") or []:
            slots = parse_slots(s.get("datetime", ""))
            if slots:
                secs.append({"section": s, "slots": slots})
        return {
            "code": c.get("code", ""), "name": c.get("name", ""),
            "score": float(c.get("score") or 0.0),
            "category": c.get("category") or "free_elective",
            "credits": float(credits), "passed": c.get("code", "") in passed,
            "sections": secs, "all_tba": len(secs) == 0,
        }

    pool = [e for e in (entry(c) for c in scores.get("courses", [])[:top]) if e]
    # 必修/选修强制入池（分数在 top 之外也不丢，供 phase1/phase0 使用）
    in_pool = {p["code"] for p in pool}
    for c in scores.get("courses", []):
        code = c.get("code", "")
        if code in in_pool:
            continue
        if c.get("category") not in ("major_required", "major_elective"):
            continue
        e = entry(c)
        if e is not None:
            pool.append(e)
            in_pool.add(code)
    return pool


def place_course(pool_item: dict, occupied: list) -> dict:
    """为课程选第一个无冲突 section → {section, slots}；None=无可用时段"""
    for cand in pool_item["sections"]:
        if any(sa[0] == sb[0] and sa[1] < sb[2] and sb[1] < sa[2]
               for sa in cand["slots"] for sb in occupied):
            continue
        return cand
    return None


def build_plan(profile: dict, pool: list, must_take: list = None,
               pre_slots: list = None, pre_notes: list = None) -> dict:
    plan = {"plan_id": profile["plan_id"], "label": profile["label"],
            "target_min": profile["target_min"], "target_max": profile["target_max"],
            "courses": [], "details": [], "slots": list(pre_slots or []),
            "credits": 0.0, "must_take": [], "notes": list(pre_notes or [])}

    def try_add(item: dict, force_tba: bool = False) -> bool:
        if item["passed"]:
            plan["notes"].append(f"已修课程跳过：{item['code']}")
            return False
        placed = place_course(item, plan["slots"])
        if placed is None:
            if item["all_tba"] and force_tba:
                # TBA 无固定课堂（如 Capstone Research）：仍计入学分，占位无时段
                placed = {"section": {"section": "TBA", "datetime": "TBA",
                                      "room": "TBA", "instructors": []},
                          "slots": []}
            elif item["all_tba"]:
                plan["notes"].append(
                    f"{item['code']} 仅有 TBA/无时间 section，无法排入")
                return False
            else:
                plan["notes"].append(f"{item['code']} 无可用时段（时间冲突），未排入")
                return False
        if plan["credits"] + item["credits"] > MAX_CREDITS:
            plan["notes"].append(
                f"{item['code']} 学分超上限（+{item['credits']} 将超 {MAX_CREDITS}），未排入")
            return False
        plan["courses"].append(item["code"])
        plan["details"].append({
            "code": item["code"], "name": item["name"],
            "category": item["category"], "credits": item["credits"],
            "section": placed["section"].get("section", ""),
            "datetime": placed["section"].get("datetime", ""),
            "room": placed["section"].get("room", ""),
            "instructors": placed["section"].get("instructors", []),
        })
        plan["slots"].extend(placed["slots"])
        plan["credits"] += item["credits"]
        return True

    def remaining():
        return [i for i in pool if i["code"] not in plan["courses"]]

    # phase0：must-take 硬插（不在 pool / 冲突 / 超限均记 note，不强行）
    for code in must_take or []:
        item = next((i for i in pool if i["code"] == code), None)
        if item is None:
            plan["notes"].append(
                f"must-take {code} 不在选课池（排名外/未开设/已修），未排入")
            continue
        if try_add(item, force_tba=True):
            plan["must_take"].append(code)

    # phase1：必修全部先入（按排名）
    for item in sorted(remaining(),
                       key=lambda x: (x["category"] != "major_required", -x["score"])):
        if item["category"] == "major_required":
            try_add(item, force_tba=True)

    # phase2：按方案偏好补足学分，达到 target_min 即停
    rest = remaining()
    if profile["phase2"] == "cc_first":
        cc = sorted([i for i in rest if i["category"] in ("cc_required", "cc_elective")],
                    key=lambda x: -x["score"])
        other = sorted([i for i in rest
                        if i["category"] not in ("cc_required", "cc_elective")],
                       key=lambda x: -x["score"])
        order = cc + other
    else:
        order = sorted(rest, key=lambda x: -x["score"])
    for item in order:
        if plan["credits"] >= profile["target_min"]:
            break
        try_add(item)

    if plan["credits"] < MIN_CREDITS:
        plan["notes"].append(
            f"候选池不足以达到下限：最终 {plan['credits']} 学分（要求 {MIN_CREDITS}-{MAX_CREDITS}）")
    elif plan["credits"] < profile["target_min"]:
        plan["notes"].append(
            f"目标区间未达：最终 {plan['credits']} 学分（目标 {profile['target_min']}-"
            f"{profile['target_max']}，候选池学分粒度不足）")
    return plan


def diversity_swap(plan: dict, pool: list):
    """两套方案课程相同 → 确定性换课：换出最低分非必修，换入同类别高分候选"""
    required = "major_required"
    selected = {d["code"] for d in plan["details"]}
    drop_candidates = [d for d in plan["details"]
                       if d["category"] != required and d["code"] not in plan["must_take"]]
    if not drop_candidates:
        return False
    # 用分数排序（details 未存 score → 从 pool 反查）
    by_score = {i["code"]: i["score"] for i in pool}
    drop = min(drop_candidates, key=lambda d: (by_score.get(d["code"], 0.0), d["code"]))

    rest = [i for i in pool if i["code"] not in selected]
    # code+section → slots 预索引，供移除 drop 后重建占用槽
    slot_by = {(i["code"], s["section"].get("section", "")): s["slots"]
               for i in pool for s in i["sections"]}
    cat_rank = lambda c: (0 if c["category"] == drop["category"] else 1,
                          CATEGORY_ORDER.get(c["category"], 9),
                          -by_score.get(c["code"], 0.0))
    for cand in sorted(rest, key=cat_rank):
        if cand["passed"]:
            continue
        if plan["credits"] - drop["credits"] + cand["credits"] < MIN_CREDITS:
            continue
        if plan["credits"] - drop["credits"] + cand["credits"] > MAX_CREDITS:
            continue
        # 移除 drop 后的占用槽
        remain_slots = [slots for d in plan["details"]
                        if d["code"] != drop["code"]
                        for slots in slot_by.get((d["code"], d["section"]), [])]
        placed = place_course(cand, remain_slots)
        if placed is None:
            continue
        plan["courses"] = [c for c in plan["courses"] if c != drop["code"]]
        plan["details"] = [d for d in plan["details"] if d["code"] != drop["code"]]
        plan["credits"] = plan["credits"] - drop["credits"] + cand["credits"]
        plan["slots"] = remain_slots
        plan["details"].append({
            "code": cand["code"], "name": cand["name"],
            "category": cand["category"], "credits": cand["credits"],
            "section": placed["section"].get("section", ""),
            "datetime": placed["section"].get("datetime", ""),
            "room": placed["section"].get("room", ""),
            "instructors": placed["section"].get("instructors", []),
        })
        plan["courses"].append(cand["code"])
        plan["notes"].append(f"多样性调整：换出 {drop['code']}（低分非必修）→ "
                             f"换入 {cand['code']}（同类优先，其次按类别序）")
        return True
    return False


def emit(plans: list, session: str) -> dict:
    out_plans = []
    for p in plans:
        cc = sum(d["credits"] for d in p["details"]
                 if d["category"] in ("cc_required", "cc_elective"))
        major = sum(d["credits"] for d in p["details"]
                    if d["category"] in ("major_required", "major_elective"))
        elec = sum(d["credits"] for d in p["details"] if d["category"] == "free_elective")
        out_plans.append({
            "plan_id": p["plan_id"],
            "label": p["label"],
            "courses": p["courses"],
            "course_details": p["details"],
            "total_credits": p["credits"],
            "workload": workload(p["credits"]),
            "cc_credits": round(cc, 1),
            "major_credits": round(major, 1),
            "elective_credits": round(elec, 1),
            "no_conflict": True,
            "must_take_inserted": p["must_take"],
            "notes": p["notes"],
        })
    return {"session": session, "plans": out_plans,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main():
    ap = argparse.ArgumentParser(description="课程表编排（N 套无冲突方案）")
    ap.add_argument("--scores", default=str(ROOT / "data" / "course_scores.json"),
                    help="Step 5 产物（排名）")
    ap.add_argument("--session", default="2610",
                    help="学期代码，对应 data/courses_{session}.json")
    ap.add_argument("--passed", default=str(ROOT / "data" / "passed_courses.json"))
    ap.add_argument("--plans", type=int, default=3, help="方案数量（默认 3）")
    ap.add_argument("--top", type=int, default=20, help="选课池取排名前 N（默认 20）")
    ap.add_argument("--must-take", nargs="+", default=[],
                    help="硬插课程（phase4.5），如 'COMP 3111' 'MATH 2023'")
    ap.add_argument("--exclude", nargs="+", default=[],
                    help="从选课池排除的课程（如未选的 Capstone 备选 'PHYS 4191'）——"
                         "排除后 phase1 必修自动加入也不会带上被排课程")
    ap.add_argument("--pre-enrolled", default="",
                    help="SIS 预选课文件（data/pre_enrolled.json）；预选课 section 时段"
                         "进入占用槽，选课不得与其冲突")
    ap.add_argument("--output", default=str(ROOT / "output" / "timetable_plan.json"))
    args = ap.parse_args()

    scores = load_json(Path(args.scores))
    schedule = load_json(ROOT / "data" / f"courses_{args.session}.json")
    passed = {c.get("code", "").replace(" ", "")
              for c in load_json(Path(args.passed)).get("courses", [])} \
        if Path(args.passed).exists() else set()

    pool = build_pool(scores, schedule, passed, args.top)
    if args.exclude:
        exclude = set(args.exclude)
        pool = [p for p in pool if p["code"] not in exclude]
        print(f"已排除 {len(exclude)} 门: {', '.join(sorted(exclude))}")
    if len(pool) < 1:
        sys.exit(f"错误: 选课池为空（scores 前 {args.top} 名无 schedule 记录？）")

    # 预选课：section 时段 → 占用槽（schedule 找 code+section 的 datetime）
    pre_enrolled_slots = []
    pre_enrolled_notes = []
    if args.pre_enrolled and Path(args.pre_enrolled).exists():
        sched = {f"{c.get('code', '')} {c.get('number', '')}".strip(): c
                 for c in schedule.get("courses", [])}
        for pe in load_json(Path(args.pre_enrolled)).get("courses", []):
            code = pe.get("code", "").replace(" ", "")
            for sc in sched.values():
                if f"{sc.get('code', '')}{sc.get('number', '')}" != code:
                    continue
                sec_name = pe.get("section") or ""
                secs = [x for x in (sc.get("sections") or [])
                        if x.get("section", "").upper() == sec_name.upper()]
                if not secs and (sc.get("sections") or []):
                    secs = [sc["sections"][0]]
                for x in secs:
                    slots = parse_slots(x.get("datetime", ""))
                    if slots:
                        pre_enrolled_slots.extend(slots)
                        pre_enrolled_notes.append(
                            f"预选课时段占用: {code} [{x.get('section')}] "
                            f"{x.get('datetime')}（选课不得冲突）")
        if not pre_enrolled_slots:
            pre_enrolled_notes.append(
                "预选课文件存在但未匹配到 schedule 时段（可能未开设或仅 TBA）")

    plans = [build_plan(p, pool, args.must_take, pre_enrolled_slots,
                        pre_enrolled_notes)
             for p in PLAN_PROFILES[:args.plans]]

    # 硬约束：学分 12-18（产物 schema 亦强制，先于落盘拦截）
    for p in plans:
        if p["credits"] < MIN_CREDITS or p["credits"] > MAX_CREDITS:
            sys.exit(
                f"错误: {p['plan_id']} 学分 {p['credits']} 超出 {MIN_CREDITS}-{MAX_CREDITS} 硬约束。"
                f"候选池不足或 --must-take 超载，请检查 course_scores 排名/"
                f"候选池规模后调整 --top/--must-take 重跑")

    # 多样性：课程集合完全相同的方案做确定性换课（后出现的方案被调整）
    seen = set()
    for p in plans:
        key = tuple(sorted(p["courses"]))
        if key in seen and len(p["courses"]) > 1:
            diversity_swap(p, pool)
        seen.add(tuple(sorted(p["courses"])))

    out = emit(plans, args.session)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"编排完成: {len(plans)} 套方案 -> {dest}\n")
    for p in out["plans"]:
        print(f"  {p['plan_id']}: {p['total_credits']} 学分 ({p['workload']}) "
              f"CC {p['cc_credits']} / major {p['major_credits']} / 选修 {p['elective_credits']}")
        for d in p["course_details"]:
            print(f"      {d['code']:10} [{d['section']:4}] {d['datetime']:28} "
                  f"{', '.join(d['instructors'])}")
        for n in p["notes"]:
            print(f"      ! {n}")


if __name__ == "__main__":
    main()
