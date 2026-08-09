#!/usr/bin/env python3
"""
课程表编排 — scripts/rank/planner.py
====================================
Step 6（新工作流）：以用户目标学分（--target-credits，默认 15）为参照生成 N 套
无时间冲突课程表 → output/timetable_plan.json。默认三档：目标学分 / 目标+3 /
目标−3。学分是软约束：目标 ±3（约一门课）内取近似值；超出常规区间
（<12 或 >18）仅提示（overload 需 Dean 批准写入报告），不夹边界、不拒绝。

bucket 配额选课（防选重/选多）：course_scores 每门课带 bucket_id / bucket_quota，
phase2 补学分时每个 bucket 至多选 quota 门（常见 quota=1，即每栏位取最高分）。
phase1 必修先入（低阶课程号优先——基础课先排），再按分数补足。

tutorial 处理（组件型 section）：一门课有多个组件类型（如 L + T）时，按组件
分组，**每个组件必须选一节**（L + T 都要；序号无需对应，L1+T2 亦可），且彼此
不冲突、不与已排课程冲突；course_details[].sections[] 列出所选全部 section，
section 字段为 "L1 + T1B" 形式摘要。

EXCLUSION 互斥（硬约束）：对照 Class Schedule 的 EXCLUSION 属性，已修/预选课/
已排课程与候选互斥 → 该候选不排入（note 说明），杜绝 MATH 2411/2421 类重复课
同排。

0 学分课程（如 COMP 1991 实习，学分 0 且无时间 section）：预标注 zero_credit，
无时间槽时仅占位不占排课时间；必修先排时零学分靠后（同桶真实学分课优先），
避免 0 学分实习抢占 FYP 桶配额挡住 COMP 4981/4910。

TBA 有学分课程（如 UROP 3200 仅 TBA section）：允许占位排入并计入学分
（course_details 标注 TBA，不占具体时段），避免必修/CC 需求被静默丢弃。

方案多样性：phase2 按 variant 轮转 bucket 取课顺序；多套方案课程相同时
diversity_swap 换入同桶/同类高分候选（不动必修与 must-take），无候选可换时
vary_sections 换用不同 section 组合（课程不变、时段变化）。

排课偏好（config → planner，产品参数）：
- prefer_day_off（高权重）：section 组合优先复用已有上课日，尽力把每周上课
  压缩到更少天数（如 5 天 → 4 天，空出整天）；组合无法再少时输出提示。
- prefer_meal_free（低权重）：同等天数前提下，优先选择不占用午餐/晚餐
  保护时段（默认 12:00-14:00 / 18:00-20:00）的 section。
  排课后输出 days_used / free_days / meal_conflicts 供展示与提醒。

pre-req 处理（新工作流）：评分与排课均不因 pre-req 剔除课程；排课后输出
waiver_required[]（placed 课程中 pre-req 未满足 / 无法判定者，附 missing 清单），
提醒用户写教授豁免申请。

预选课（Pre-Enroll）处理：预选课视为已确定——不重复选入（pool 排除）、
其 section 时段计入占用槽；评分已在 step5 +20% 加权（pre_enroll_boost）。
排课后若某门预选课即便加权后评分仍低于本方案最低分已选课（优先级低），
输出 pre_enroll_advice[] 建议 drop（学校不建议 drop 预选课，坚持需 waiver，
提前告知风险与原因）。

硬约束：不重复 / 不含已修课 / 每 bucket 不超过配额 / 无 EXCLUSION 互斥 /
无时间冲突。学分软约束：目标 ±3 内取近似（一门课 3 学分粒度），
<12 或 >18 仅提示（overload 需 Dean 批准，写入报告说明）。
phase4.5 硬插：--must-take 在 phase0 优先入排（不在池/冲突 → notes）。

用法:
  python3 scripts/rank/planner.py --scores data/course_scores.json --session <SESSION> \
      --target-credits 15
  python3 scripts/rank/planner.py --scores data/course_scores.json --session <SESSION> \
      --target-credits 20                              # 提示 overload，按 18-22 编排
  python3 scripts/rank/planner.py --scores data/course_scores.json --session <SESSION> \
      --must-take "COMP 3111" "MATH 2023"              # 硬插课程（phase4.5）
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "rank"))
sys.path.insert(0, str(ROOT / "scripts"))

from wcq.conflict import parse_slots, _overlap, DAY_NAMES  # noqa: E402  (复用 schedule 时间槽解析)
from filter import passed_set as filter_passed_set  # noqa: E402 (已修白名单：挂科/旁听不计)
from harness.config import load as load_config  # noqa: E402

# 常规学期学分上下限：唯一权威 = config/ustplan.json → defaults.credits_min/max
# （2026-08 松弛度修复：此前硬编码 12/18，与 config 双份定义易失同步）
CFG_DEFAULTS = load_config().get("defaults", {})
MAX_CREDITS = float(CFG_DEFAULTS.get("credits_max", 18))  # 超过仅提示（overload 需 Dean 批准）
MIN_CREDITS = float(CFG_DEFAULTS.get("credits_min", 12))  # 低于仅提示
CREDIT_TOLERANCE = 3  # 目标 ±3 学分（一门课粒度）内视为达标
CATEGORY_ORDER = {"cc_required": 0, "cc_elective": 1,
                  "major_elective": 2, "free_elective": 3}

# 排课偏好（config/ustplan.json → planner）：整天空闲优先（高权重）+
# 正餐时段避让（低权重）；meal_windows 分钟化，缺省 午餐 12:00-14:00 / 晚餐 18:00-20:00
_PLANNER_CFG = load_config().get("planner", {})
PREFER_DAY_OFF = bool(_PLANNER_CFG.get("prefer_day_off", True))
PREFER_MEAL_FREE = bool(_PLANNER_CFG.get("prefer_meal_free", True))


def _parse_hhmm(t: str) -> int:
    hh, _, mm = str(t).partition(":")
    return int(hh) * 60 + int(mm)


MEAL_WINDOWS = []
for _mw in _PLANNER_CFG.get("meal_windows") or [
        {"label": "午餐", "start": "12:00", "end": "14:00"},
        {"label": "晚餐", "start": "18:00", "end": "20:00"}]:
    MEAL_WINDOWS.append({"label": _mw.get("label", "餐"),
                         "start": _parse_hhmm(_mw.get("start", "12:00")),
                         "end": _parse_hhmm(_mw.get("end", "14:00"))})

# 组件类型展示顺序（L=lecture 优先；其余按字母序）
TYPE_ORDER = {"L": 0, "LA": 1, "T": 2}

RE_CODE = re.compile(r"([A-Z]{3,4})\s*(\d{4}[A-Z]?)")


def norm_code(s: str) -> str:
    """课号规范化：大写、去空格/点 → 'COMP1991'（EXCLUSION/已修/预选匹配用）"""
    return re.sub(r"[\s.]+", "", str(s or "")).upper()


def section_type(name: str) -> str:
    """section 名 → 组件类型：前导字母（L1→L、T01A→T、LA1→LA、R1→R）。
    一门课若同时有多个组件类型（如 L+T），每个组件都须选一节。"""
    m = re.match(r"^([A-Za-z]+)", str(name or ""))
    return m.group(1).upper() if m else str(name or "").strip()


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


def course_number(code: str) -> int:
    m = re.search(r"(\d{4})", code or "")
    return int(m.group(1)) if m else 9999


def build_pool(scores: dict, schedule: dict, passed: set, top: int,
               credits_overrides: dict = None) -> list:
    """course_scores（每 bucket TOP3）→ 池（含 schedule section/slots，学分取 schedule units）。
    major_required/major_elective 即使分数在 top 之外也强制入池。
    credits_overrides：{norm_code: 学分} 覆盖 schedule units（如全年课按学期学分计）。
    全年课程自动折算：course_notes tags.year_long → units/2（每学期注册学分，
    如 PHYS 4291 全年 6 → 每学期 3）；手动 credits_overrides 优先。
    sections 按组件类型分组（groups）：课程有多个组件类型（如 L+T）时，
    排课必须每个组件各选一节（tutorial 处理，序号无需对应）。"""
    overrides = {norm_code(k): float(v) for k, v in (credits_overrides or {}).items()}
    year_long = set()
    try:
        from buckets import load_course_notes
        year_long = {k for k, v in load_course_notes().items()
                     if "year_long" in (v.get("tags") or [])}
    except Exception:
        year_long = set()
    sched = {f"{c.get('code', '')} {c.get('number', '')}".strip(): c
             for c in schedule.get("courses", [])}

    def entry(c: dict) -> dict:
        if c.get("pre_enrolled"):
            return None  # 预选课已确定（固定选课），排课不重复选取；仅参与评分排序
        sc = sched.get(c.get("code", ""))
        if sc is None:
            return None
        n = norm_code(c.get("code", ""))
        credits = overrides.get(n, sc.get("units"))
        if n not in overrides and n in year_long and \
                isinstance(credits, (int, float)) and credits > 0:
            credits = credits / 2.0
        if not isinstance(credits, (int, float)):
            return None
        attrs = sc.get("attributes") or {}
        secs = []
        for s in sc.get("sections") or []:
            slots = parse_slots(s.get("datetime", ""))
            if slots:
                secs.append({"section": s, "slots": slots})
        groups = {}
        for item in secs:
            groups.setdefault(section_type(item["section"].get("section", "")),
                              []).append(item)
        # 组件顺序：L/LA/T 优先，其余按类型字母序（确定性）
        ordered = [groups[t] for t in sorted(groups,
                                             key=lambda t: (TYPE_ORDER.get(t, 9), t))]
        return {
            "code": c.get("code", ""), "name": c.get("name", ""),
            "score": float(c.get("score") or 0.0),
            "category": c.get("category") or "free_elective",
            "bucket_id": c.get("bucket_id") or c.get("code", ""),
            "bucket_quota": int(c.get("bucket_quota") or 1),
            "credits": float(credits), "passed": norm_code(c.get("code", "")) in passed,
            "zero_credit": float(credits) <= 0,
            "sections": secs, "groups": ordered, "all_tba": len(secs) == 0,
            "exclusions": sorted({norm_code(f"{a} {b}")
                                  for a, b in RE_CODE.findall(
                                      (attrs.get("EXCLUSION") or ""))}),
            "prerequisites": c.get("prerequisites", "") or "",
            "prereq_met": c.get("prereq_met"),
            "prereq_missing": c.get("prereq_missing", []),
            "prereq_grading": c.get("prereq_grading", []),
        }

    pool = [e for e in (entry(c) for c in scores.get("courses", [])[:top]) if e]
    in_pool = {p["code"] for p in pool}
    # 备选池 ranked_out（栏位 TOP3 之外的完整评分名单）：不参与常规补选，
    # 仅服务 must-take 硬插 / 多样性换课
    extra = [e for e in (entry(c) for c in scores.get("ranked_out", []))
             if e is not None and e["code"] not in in_pool]
    extra_codes = {e["code"] for e in extra}
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
    # 标记备选池课程 not_top3：phase2 常规补选不主动选它们
    for e in extra:
        e["not_top3"] = True
    pool.extend(extra)
    return pool


def _slots_conflict(slots: list, occupied: list) -> bool:
    return any(_overlap(sa, sb) for sa in slots for sb in occupied)


def _days_used(slots: list) -> set:
    """槽 → 使用天数集合（slot[0] = day 0-6）"""
    return {s[0] for s in slots}


def _meal_hits(slots: list) -> set:
    """槽 → 被占用的（天, 餐次）集合：与保护时段重叠即计入"""
    hits = set()
    for day, s, e, *_ in slots:
        for m in MEAL_WINDOWS:
            if s < m["end"] and m["start"] < e:
                hits.add((day, m["label"]))
    return hits


def _combo_rank(combo: list, occupied: list) -> tuple:
    """section 组合偏好评分（越小越优）：
    1) 高权重 prefer_day_off：加课后总上课天数最少（复用已有日，空出整天）；
    2) 低权重 prefer_meal_free：占用正餐时段最少；
    3) 确定性兜底：section 名升序（防随机、可复现）。"""
    combo_slots = [s for c in combo for s in c["slots"]]
    days = len(_days_used(occupied) | _days_used(combo_slots))
    meals = len(_meal_hits(combo_slots))
    names = tuple(sorted(c["section"].get("section", "") for c in combo))
    return (days if PREFER_DAY_OFF else 0,
            meals if PREFER_MEAL_FREE else 0, names)


def place_course(pool_item: dict, occupied: list):
    """为课程选一组 section：每个组件类型各一节（如 L+T），类型间不冲突、
    与已占用槽不冲突；组件序号无需对应（L1+T2 亦可）。
    在所有可行组合中按偏好取最优（少占天数 → 避正餐时段 → section 名序）。
    返回 [{section, slots}, ...]；None = 无可用组合（时间冲突）。"""
    groups = pool_item["groups"]
    if not groups:
        return None
    combos = []
    chosen = []

    def dfs(i: int, used: list):
        if i == len(groups):
            combos.append(list(chosen))
            return
        for cand in groups[i]:
            if _slots_conflict(cand["slots"], used) or \
                    _slots_conflict(cand["slots"], occupied):
                continue
            chosen.append(cand)
            dfs(i + 1, used + cand["slots"])
            chosen.pop()

    dfs(0, [])
    if not combos:
        return None
    return min(combos, key=lambda c: _combo_rank(c, occupied))


def detail_sections(placed: list) -> list:
    """placed sections → course_details.sections[]（兼容 schema 输出）"""
    return [{
        "section": x["section"].get("section", ""),
        "datetime": x["section"].get("datetime", ""),
        "room": x["section"].get("room", ""),
        "instructors": x["section"].get("instructors", []),
    } for x in placed]


def make_detail(item: dict, placed: list) -> dict:
    """pool item + 选中的 section 组合 → course_details 条目（try_add /
    diversity_swap / vary_sections 共用，字段一致）"""
    secs_out = detail_sections(placed)
    return {
        "code": item["code"], "name": item["name"],
        "category": item["category"], "credits": item["credits"],
        "bucket_id": item["bucket_id"],
        "section": " + ".join(s["section"] for s in secs_out),
        "datetime": ", ".join(s["datetime"] for s in secs_out if s["datetime"]),
        "room": " / ".join(s["room"] for s in secs_out if s["room"]),
        "instructors": sorted({i for s in secs_out for i in s["instructors"]}),
        "sections": secs_out,
        "prerequisites": item["prerequisites"],
        "prereq_met": item["prereq_met"],
        "prereq_missing": item["prereq_missing"],
        "prereq_grading": item.get("prereq_grading", []),
        "exclusions": sorted(item.get("exclusions") or []),
        "zero_credit": bool(item.get("zero_credit")),
    }


def build_plan(label: str, target_credits: float, pool: list, must_take: list = None,
               pre_slots: list = None, pre_notes: list = None,
               cc_first: bool = False, variant: int = 0,
               passed_norm: set = None, pre_norm: set = None) -> dict:
    plan = {"label": label, "target": target_credits,
            "courses": [], "details": [], "slots": list(pre_slots or []),
            "credits": 0.0, "must_take": [], "notes": list(pre_notes or []),
            "bucket_counts": {}}
    passed_norm = passed_norm or set()
    pre_norm = pre_norm or set()

    def bucket_ok(item) -> bool:
        n = plan["bucket_counts"].get(item["bucket_id"], 0)
        if n >= item["bucket_quota"]:
            plan["notes"].append(
                f"{item['code']} 已选满所在栏位（{item['bucket_id']} 配额 "
                f"{item['bucket_quota']}），不重复选取")
            return False
        return True

    def exclusion_ok(item) -> bool:
        """EXCLUSION 硬约束：候选与已修/预选/已排课程互斥 → 不排入"""
        cn = norm_code(item["code"])
        blocked = set(item.get("exclusions") or []) & \
            (passed_norm | pre_norm | {norm_code(d["code"])
                                       for d in plan["details"]})
        if blocked:
            plan["notes"].append(
                f"{item['code']} 与已修/预选/已排课程互斥（EXCLUSION: "
                f"{', '.join(sorted(blocked))}），未排入")
            return False
        for d in plan["details"]:
            if cn in set(d.get("exclusions") or []):
                plan["notes"].append(
                    f"{item['code']} 与已排课程 {d['code']} 互斥（EXCLUSION），未排入")
                return False
        return True

    def try_add(item: dict, force_tba: bool = False,
                enforce_credit: bool = True) -> bool:
        if item["passed"]:
            plan["notes"].append(f"已修课程跳过：{item['code']}")
            return False
        if not bucket_ok(item):
            return False
        if not exclusion_ok(item):
            return False
        placed = place_course(item, plan["slots"])
        if placed is None:
            if item["all_tba"] and item.get("zero_credit"):
                placed = [{"section": {"section": "TBA", "datetime": "TBA",
                                       "room": "TBA", "instructors": []},
                           "slots": []}]
                plan["notes"].append(
                    f"{item['code']} 为 0 学分课程（实习/体验类）且无时间 section，"
                    f"仅标注占位，不占排课时间")
            elif item["all_tba"] and (force_tba or item["category"] in
                                      ("major_required", "cc_required", "cc_elective")):
                placed = [{"section": {"section": "TBA", "datetime": "TBA",
                                       "room": "TBA", "instructors": []},
                           "slots": []}]
                plan["notes"].append(
                    f"{item['code']} 仅有 TBA/无时间 section，按占位排入并计入学分")
            elif item["all_tba"]:
                plan["notes"].append(
                    f"{item['code']} 仅有 TBA/无时间 section，无法排入")
                return False
            else:
                plan["notes"].append(
                    f"{item['code']} 无可用时段（时间冲突），未排入")
                return False
        if enforce_credit and \
                plan["credits"] + item["credits"] > target_credits + CREDIT_TOLERANCE:
            plan["notes"].append(
                f"{item['code']} 学分将超目标区间（当前 {plan['credits']} + "
                f"{item['credits']} > {target_credits}+{CREDIT_TOLERANCE}），未排入")
            return False
        plan["courses"].append(item["code"])
        plan["details"].append(make_detail(item, placed))
        plan["bucket_counts"][item["bucket_id"]] = \
            plan["bucket_counts"].get(item["bucket_id"], 0) + 1
        plan["slots"].extend(slot for x in placed for slot in x["slots"])
        plan["credits"] += item["credits"]
        return True

    def remaining():
        return [i for i in pool if i["code"] not in plan["courses"]]

    # phase0：must-take 硬插（不因学分拒绝——必修性质课程优先满足）
    for code in must_take or []:
        item = next((i for i in pool if i["code"] == code), None)
        if item is None:
            plan["notes"].append(
                f"must-take {code} 不在选课池（排名外/未开设/已修），未排入")
            continue
        if try_add(item, force_tba=True, enforce_credit=False):
            plan["must_take"].append(code)

    # phase1：必修全部先入（低阶课号优先 → 基础课先排，同号按分数；零学分
    # 课程靠后——同桶真实学分课先占配额，防 0 学分实习挡 FYP；只取栏位 TOP3）
    for item in sorted(remaining(),
                       key=lambda x: (x["category"] != "major_required",
                                      bool(x.get("zero_credit")),
                                      course_number(x["code"]), -x["score"])):
        if item["category"] == "major_required" and not item.get("not_top3"):
            try_add(item, force_tba=True, enforce_credit=False)

    # phase2：按偏好补足学分到 target（每 bucket 至多 quota 门；备选池不主动选）。
    # variant 轮转取课顺序：0=按分数；1=CC 优先；2=按桶轮转（同分换桶挑不同组合）
    rest = remaining()
    if cc_first or variant % 3 == 1:
        cc = sorted([i for i in rest if i["category"] in ("cc_required", "cc_elective")
                     and not i.get("not_top3")],
                    key=lambda x: -x["score"])
        other = sorted([i for i in rest
                        if i["category"] not in ("cc_required", "cc_elective")
                        and not i.get("not_top3")],
                       key=lambda x: -x["score"])
        order = cc + other
    elif variant % 3 == 2:
        buckets_order = []
        for i in rest:
            if i["bucket_id"] not in buckets_order:
                buckets_order.append(i["bucket_id"])
        rot = {bid: (idx + 1) % max(1, len(buckets_order))
               for idx, bid in enumerate(buckets_order)}
        order = sorted([i for i in rest if not i.get("not_top3")],
                       key=lambda x: (rot.get(x["bucket_id"], 9), -x["score"]))
    else:
        order = sorted([i for i in rest if not i.get("not_top3")],
                       key=lambda x: -x["score"])
    for item in order:
        if plan["credits"] >= target_credits:
            break
        try_add(item)

    if plan["credits"] < MIN_CREDITS:
        plan["notes"].append(
            f"候选池不足：最终 {plan['credits']} 学分（低于常规下限 {MIN_CREDITS}，"
            f"建议咨询学校）")
    elif plan["credits"] < target_credits - CREDIT_TOLERANCE:
        plan["notes"].append(
            f"目标未达：最终 {plan['credits']} 学分（目标 {target_credits}，"
            f"候选池学分粒度不足）")
    return plan


def diversity_swap(plan: dict, pool: list):
    """两套方案课程相同 → 确定性换课：换出最低分非必修，换入同类高分候选
    （尊重 bucket 配额与 EXCLUSION 互斥；不换必修与 must-take，不换 0 学分
    TBA 占位课程）。返回 True=已换。"""
    selected = {d["code"] for d in plan["details"]}
    drop_candidates = [d for d in plan["details"]
                       if d["category"] != "major_required"
                       and d["code"] not in plan["must_take"]
                       and not d.get("zero_credit")]
    if not drop_candidates:
        return False
    by_score = {i["code"]: i["score"] for i in pool}
    drop = min(drop_candidates, key=lambda d: (by_score.get(d["code"], 0.0), d["code"]))

    rest = [i for i in pool if i["code"] not in selected]
    cat_rank = lambda c: (0 if c["category"] == drop["category"] else 1,
                          CATEGORY_ORDER.get(c["category"], 9),
                          -by_score.get(c["code"], 0.0))
    placed_norm = {norm_code(d["code"]) for d in plan["details"]}
    for cand in sorted(rest, key=cat_rank):
        if cand["passed"]:
            continue
        cn = norm_code(cand["code"])
        blocked = set(cand.get("exclusions") or []) & placed_norm
        blocked |= {x for d in plan["details"] if cn in set(d.get("exclusions") or [])
                    for x in [norm_code(d["code"])]}
        if blocked:
            continue
        drop_bucket = next((d["bucket_id"] for d in plan["details"]
                            if d["code"] == drop["code"]), "")
        # 换入桶必须未满（防跨桶破坏配额，如 CC 每区域 1 门）；同桶或未满桶均可换入
        bucket_n = plan["bucket_counts"].get(cand["bucket_id"], 0)
        if bucket_n >= cand["bucket_quota"]:
            continue
        if plan["credits"] - drop["credits"] + cand["credits"] < MIN_CREDITS:
            continue
        if plan["credits"] - drop["credits"] + cand["credits"] > \
                plan.get("target", 15.0) + CREDIT_TOLERANCE:
            continue
        remain_slots = [slot for d in plan["details"] if d["code"] != drop["code"]
                        for s in d.get("sections", [])
                        for slot in parse_slots(s.get("datetime", ""))]
        placed = place_course(cand, remain_slots)
        if placed is None:
            continue
        plan["bucket_counts"][cand["bucket_id"]] = bucket_n + 1
        plan["bucket_counts"][drop["bucket_id"]] = \
            plan["bucket_counts"].get(drop["bucket_id"], 1) - 1
        plan["courses"] = [c for c in plan["courses"] if c != drop["code"]]
        plan["details"] = [d for d in plan["details"] if d["code"] != drop["code"]]
        plan["credits"] = plan["credits"] - drop["credits"] + cand["credits"]
        plan["slots"] = remain_slots
        plan["details"].append(make_detail(cand, placed))
        plan["courses"].append(cand["code"])
        plan["notes"].append(f"多样性调整：换出 {drop['code']}（低分非必修）→ "
                             f"换入 {cand['code']}（同类优先，其次按类别序）")
        return True
    return False


def _section_names(placed: list) -> tuple:
    return tuple(sorted(s["section"] for s in placed))


def _place_variant(groups: list, occupied: list, exclude_combo: tuple):
    """DFS 枚举 section 组合：返回与 exclude_combo（当前方案）不同的最优无冲突
    组合（课程不变、时段变化；偏好同 place_course）；无其它组合返回 None。"""
    combos = []
    chosen = []

    def dfs(i: int, used: list):
        if i == len(groups):
            combo = tuple(sorted(c["section"]["section"] for c in chosen))
            if combo != exclude_combo:
                combos.append(list(chosen))
            return
        for cand in groups[i]:
            if _slots_conflict(cand["slots"], used) or \
                    _slots_conflict(cand["slots"], occupied):
                continue
            chosen.append(cand)
            dfs(i + 1, used + cand["slots"])
            chosen.pop()

    dfs(0, [])
    if not combos:
        return None
    return min(combos, key=lambda c: _combo_rank(c, occupied))


def vary_sections(plan: dict, pool: list):
    """方案多样性兜底：课程集合无法换（全必修/已达学分上限）时，为已排课程
    换用不同的 section 组合（如 L1 → L2），保证多套方案至少在时段上有差异。
    返回 True=至少一门课换了时段。"""
    items = {i["code"]: i for i in pool}
    for d in plan["details"]:
        item = items.get(d["code"])
        if item is None or item.get("all_tba") or not item["groups"]:
            continue
        current = _section_names(d.get("sections") or [])
        others_slots = [slot for o in plan["details"] if o["code"] != d["code"]
                        for s in o.get("sections", [])
                        for slot in parse_slots(s.get("datetime", ""))]
        placed = _place_variant(item["groups"], others_slots, current)
        if placed is None:
            continue
        old = " + ".join(current)
        new = " + ".join(sorted(s["section"]["section"] for s in placed))
        new_detail = make_detail(item, placed)
        d.update(new_detail)
        plan["slots"] = [slot for o in plan["details"]
                         for s in o.get("sections", [])
                         for slot in parse_slots(s.get("datetime", ""))]
        plan["notes"].append(
            f"多样性调整：{d['code']} 换用不同时段（{old} → {new}）")
        return True
    return False


def build_pre_enroll_advice(plan: dict, pre_scored: dict,
                            pool_by_code: dict) -> list:
    """预选课 drop 建议：预选课评分已 +20% 加权（step5），若仍低于本方案
    已选课程的最低分（= 仅凭分数不会入选），建议 drop。学校预选课一般
    不建议 drop，坚持 drop 需申请 waiver（提前告知风险与原因）。"""
    placed_scores = [pool_by_code.get(d["code"]) for d in plan["details"]
                     if d["code"] in pool_by_code]
    placed_scores = [s for s in placed_scores if s is not None]
    if not placed_scores:
        return []
    min_placed = min(placed_scores)
    advice = []
    for code, c in sorted(pre_scored.items()):
        if c.get("score", 0.0) >= min_placed:
            continue
        advice.append({
            "code": code,
            "name": c.get("name", ""),
            "score": round(float(c.get("score") or 0.0), 2),
            "min_plan_score": round(min_placed, 2),
            "reason": ("即便 +20% 预选课加权，评分仍低于本方案全部已选"
                       "课程的最低分，仅凭分数不会入选"),
            "note": ("学校预选课一般不建议 drop；若坚持 drop 需申请 "
                     "waiver，并注意可能影响下学期预选资格"),
        })
    return advice


def waiver_list(plan: dict) -> list:
    """placed 课程中 pre-req 未满足/无法判定/成绩不达标者 → waiver 提醒清单"""
    out = []
    for d in plan["details"]:
        if not d.get("prerequisites"):
            continue
        met = d.get("prereq_met")
        grading_bad = [g for g in d.get("prereq_grading", [])
                       if g.get("met") is False]
        grading_unknown = [g for g in d.get("prereq_grading", [])
                           if g.get("met") is None]
        if met is False:
            note = "pre-req 未满足，需教授/系豁免（waiver）"
            if grading_bad:
                note += "；" + "；".join(
                    f"{g['code']} 成绩不达标（需 {g['required']}，实得 "
                    f"{g['actual'] or '无记录'}）" for g in grading_bad)
            out.append({"code": d["code"], "prerequisites": d["prerequisites"],
                        "missing": d.get("prereq_missing", []),
                        "grading": d.get("prereq_grading", []), "note": note})
        elif met is None:
            note = "pre-req 文本需人工确认是否满足，不满足则申请 waiver"
            if grading_unknown:
                note += "；成绩要求无法对照（" + "、".join(
                    f"{g['code']} 需 {g['required']}" for g in grading_unknown) + "）"
            out.append({"code": d["code"], "prerequisites": d["prerequisites"],
                        "missing": [],
                        "grading": d.get("prereq_grading", []), "note": note})
    return out


def _fmt_min(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _plan_comfort(plan: dict) -> tuple:
    """方案舒适度统计（不影响排课结果）：
    - days_used：有课天数（含预选课占用的天）；
    - free_days：无课的工作日（周一至周五；周末默认无课不算）；
    - meal_conflicts：占用正餐时段的（天, 餐次, 课程）清单。"""
    occupied_days = {s[0] for s in plan["slots"]}
    days_used = [DAY_NAMES[d] for d in sorted(occupied_days)]
    free_days = [DAY_NAMES[d] for d in range(5) if d not in occupied_days]
    meals = []
    for d in plan["details"]:
        for sec in d.get("sections", []):
            for day, s, e, *_ in parse_slots(sec.get("datetime", "")):
                for m in MEAL_WINDOWS:
                    if s < m["end"] and m["start"] < e:
                        entry = next((x for x in meals if x["day"] == DAY_NAMES[day]
                                      and x["meal"] == m["label"]), None)
                        if entry is None:
                            entry = {"day": DAY_NAMES[day], "meal": m["label"],
                                     "window": f"{_fmt_min(m['start'])}-{_fmt_min(m['end'])}",
                                     "courses": []}
                            meals.append(entry)
                        item = {"code": d["code"], "times": f"{_fmt_min(s)}-{_fmt_min(e)}"}
                        if item not in entry["courses"]:
                            entry["courses"].append(item)
    return days_used, free_days, meals


def emit(plans: list, session: str, target_credits: float) -> dict:
    out_plans = []
    for p in plans:
        cc = sum(d["credits"] for d in p["details"]
                 if d["category"] in ("cc_required", "cc_elective"))
        major = sum(d["credits"] for d in p["details"]
                    if d["category"] in ("major_required", "major_elective"))
        elec = sum(d["credits"] for d in p["details"] if d["category"] == "free_elective")
        days_used, free_days, meal_conflicts = _plan_comfort(p)
        notes = list(p["notes"])
        if PREFER_DAY_OFF:
            if free_days:
                notes.insert(0, f"整天空闲：{'、'.join(free_days)} 无课"
                                f"（每周上课 {len(days_used)} 天）")
            else:
                notes.insert(0, f"未能实现整天空闲：{', '.join(days_used)} 均有课")
        if PREFER_MEAL_FREE:
            for mc in meal_conflicts:
                notes.append(f"{mc['day']} {mc['meal']}（{mc['window']}）被占用："
                             + "、".join(f"{c['code']}（{c['times']}）"
                                         for c in mc["courses"]))
        out_plans.append({
            "plan_id": p["plan_id"] if "plan_id" in p else "",
            "label": p["label"],
            "target_credits": p["target"],
            "courses": p["courses"],
            "course_details": p["details"],
            "total_credits": p["credits"],
            "workload": workload(p["credits"]),
            "cc_credits": round(cc, 1),
            "major_credits": round(major, 1),
            "elective_credits": round(elec, 1),
            "days_used": days_used,
            "free_days": free_days,
            "meal_conflicts": meal_conflicts,
            "no_conflict": True,
            "must_take_inserted": p["must_take"],
            "waiver_required": waiver_list(p),
            "pre_enroll_advice": p.get("pre_enroll_advice", []),
            "notes": notes,
        })
    return {"session": session, "target_credits": target_credits, "plans": out_plans,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def main():
    ap = argparse.ArgumentParser(description="课程表编排（N 套无冲突方案，按目标学分）")
    ap.add_argument("--scores", default=str(ROOT / "data" / "course_scores.json"),
                    help="Step 5 产物（bucket 评分总表）")
    ap.add_argument("--session", default="",
                    help="学期代码，对应 data/courses_{session}.json")
    ap.add_argument("--passed", default=str(ROOT / "data" / "passed_courses.json"))
    ap.add_argument("--target-credits", type=float,
                    default=float(CFG_DEFAULTS.get("target_credits", 15)),
                    help="用户目标学分（默认取 config；<12 或 >18 仅提示，不夹边界）")
    ap.add_argument("--plans", type=int,
                    default=int(CFG_DEFAULTS.get("plans", 3)),
                    help="方案数量（默认取 config）")
    ap.add_argument("--top", type=int,
                    default=int(CFG_DEFAULTS.get("candidate_pool", 50)),
                    help="选课池取排名前 N（默认取 config）")
    ap.add_argument("--must-take", action="append", default=[],
                    help="硬插课程（phase4.5），如 'COMP 3111' 'MATH 2023'；"
                         "可重复 flag 或一次传多个")
    ap.add_argument("--exclude", action="append", default=[],
                    help="从选课池排除的课程（如未选的 Capstone 备选）；可重复 flag")
    ap.add_argument("--credits-override", action="append", default=[],
                    help="学分覆盖 'CODE=学分'（可多个；如全年课按学期计："
                         "'PHYS 4291=3'）；可重复 flag")
    ap.add_argument("--pre-enrolled", default="",
                    help="SIS 预选课文件（data/pre_enrolled.json）；预选课 section 时段"
                         "进入占用槽，选课不得与其冲突")
    ap.add_argument("--output", default=str(ROOT / "output" / "timetable_plan.json"))
    args = ap.parse_args()
    # action=append 兼容：重复 flag 与单次多值都扁平化为列表（2026-08 修复
    # nargs='+' 重复 flag 只保留最后一个的静默吞值）
    args.must_take = [x for g in args.must_take for x in g]
    args.exclude = [x for g in args.exclude for x in g]
    args.credits_override = [x for g in args.credits_override for x in g]
    if not args.session:
        sys.exit("错误: 缺少 --session（学期代码；运行中的学期可由 ustplan status 查询）")

    scores = load_json(Path(args.scores))
    schedule = load_json(ROOT / "data" / f"courses_{args.session}.json")
    # 已修白名单（filter.PASSED_STATUSES）：taken/transferred/exempted/in_progress；
    # 挂科（incomplete）/旁听（audit）/异常（unknown）不算已修 → 可重修/可推荐
    passed_norm = filter_passed_set(load_json(Path(args.passed))) \
        if Path(args.passed).exists() else set()

    target = args.target_credits
    if target > MAX_CREDITS:
        print(f"提示: 目标 {target} 学分 > {MAX_CREDITS}（常规学期上限），"
              f"需 Dean 批准 overload；按 {target} 编排，说明写入报告")
    if target < MIN_CREDITS:
        print(f"提示: 目标 {target} 学分 < {MIN_CREDITS}（常规学期下限），"
              f"按 {target} 编排（低于下限建议咨询学校）")

    credits_overrides = {}
    for kv in args.credits_override or []:
        code, _, val = kv.partition("=")
        code, val = code.strip(), val.strip()
        if not code or not val.replace(".", "", 1).isdigit():
            sys.exit(f"错误: --credits-override 格式应为 'CODE=学分'，收到 {kv!r}")
        credits_overrides[norm_code(code)] = float(val)
    if credits_overrides:
        print("学分覆盖:", ", ".join(f"{k}={v}" for k, v in credits_overrides.items()))

    pool = build_pool(scores, schedule, passed_norm, args.top, credits_overrides)
    if args.exclude:
        exclude = set(args.exclude)
        pool = [p for p in pool if p["code"] not in exclude]
        print(f"已排除 {len(exclude)} 门: {', '.join(sorted(exclude))}")
    if len(pool) < 1:
        sys.exit(f"错误: 选课池为空（scores 前 {args.top} 名无 schedule 记录？）")

    pre_enrolled_slots = []
    pre_enrolled_notes = []
    pre_enrolled_codes = set()
    if args.pre_enrolled and Path(args.pre_enrolled).exists():
        pe_data = load_json(Path(args.pre_enrolled))
        # 结构兼容：schema 权威为 confirmed/pending（SIS 解析产物），
        # 旧格式 courses 兜底读取
        pe_list = (pe_data.get("confirmed", []) + pe_data.get("pending", [])) \
            or pe_data.get("courses", [])
        sched = {f"{c.get('code', '')} {c.get('number', '')}".strip(): c
                 for c in schedule.get("courses", [])}
        for pe in pe_list:
            code = norm_code(pe.get("code", ""))
            pre_enrolled_codes.add(code)
            for sc in sched.values():
                if norm_code(f"{sc.get('code', '')} {sc.get('number', '')}".strip()) \
                        != code:
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
        if not pe_list:
            pass
        elif not pre_enrolled_slots:
            pre_enrolled_notes.append(
                "预选课文件存在但未匹配到 schedule 时段（可能未开设或仅 TBA）")

    # 目标学分附近生成方案：目标 / +3 / −3（软约束，不去重后裁剪）
    targets = [target]
    if target + CREDIT_TOLERANCE >= MIN_CREDITS:
        targets.append(target + CREDIT_TOLERANCE)
    if target - CREDIT_TOLERANCE >= 0:
        targets.append(target - CREDIT_TOLERANCE)
    targets = list(dict.fromkeys(t for t in targets if t is not None))[:args.plans]
    labels = {}
    if len(targets) >= 1:
        labels[0] = f"目标 {targets[0]:.0f} 学分（用户参照）"
    if len(targets) >= 2:
        labels[1] = f"目标 {targets[1]:.0f} 学分（更满）"
    if len(targets) >= 3:
        labels[2] = f"目标 {targets[2]:.0f} 学分（更轻）"
    cc_first_target = max(targets) if len(targets) > 1 else None
    plans = []
    for i, t in enumerate(targets):
        plan = build_plan(labels.get(i, f"目标 {t:.0f} 学分"),
                          t, pool, args.must_take, pre_enrolled_slots,
                          pre_enrolled_notes, cc_first=(t == cc_first_target),
                          variant=i, passed_norm=passed_norm,
                          pre_norm=pre_enrolled_codes)
        plan["plan_id"] = f"plan-{i + 1}"
        plans.append(plan)

    for p in plans:
        if p["credits"] > MAX_CREDITS:
            p["notes"].append(
                f"学分 {p['credits']} 超过常规上限 {MAX_CREDITS}（overload，需 Dean 批准）")
        if p["credits"] < MIN_CREDITS:
            p["notes"].append(
                f"学分 {p['credits']} 低于常规下限 {MIN_CREDITS}（建议咨询学校）")

    seen = set()
    for p in plans:
        key = tuple(sorted(p["courses"]))
        if key in seen and len(p["courses"]) > 1:
            if not diversity_swap(p, pool):
                vary_sections(p, pool)
        seen.add(tuple(sorted(p["courses"])))

    # 预选课 drop 建议：预选课评分已 +20% 加权（step5），若仍低于本方案
    # 已选课程的最低分（= 仅凭分数不会入选），提示学生考虑 drop——学校预选课
    # 一般不建议 drop，坚持 drop 需申请 waiver（提前告知风险与原因）。
    pre_scored = {c["code"]: c for c in
                  scores.get("courses", []) + scores.get("ranked_out", [])
                  if c.get("pre_enrolled")}
    pool_by_code = {i["code"]: i["score"] for i in pool}
    if pre_scored or pre_enrolled_codes:
        tip = ("预选课（学校 Pre-Enroll）已视为固定选课：占用 section 时段、"
               "不重复推荐；学校通常不建议 drop 预选课，若坚持 drop 需申请 "
               "waiver（且可能影响下学期预选资格）")
        for p in plans:
            p["notes"].append(tip)
    if pre_scored:
        for p in plans:
            advice = build_pre_enroll_advice(p, pre_scored, pool_by_code)
            p["pre_enroll_advice"] = advice
            for a in advice:
                p["notes"].append(
                    f"预选课 {a['code']} 优先级低（{a['score']:+.2f} < 方案最低 "
                    f"{a['min_plan_score']:+.2f}）：可考虑 drop，需 waiver（见 "
                    f"pre_enroll_advice）")

    out = emit(plans, args.session, args.target_credits)
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"编排完成: {len(plans)} 套方案（用户目标 {args.target_credits:.0f} 学分）-> {dest}\n")
    for p in out["plans"]:
        print(f"  {p['plan_id']}: {p['total_credits']} 学分 ({p['workload']}) "
              f"CC {p['cc_credits']} / major {p['major_credits']} / 选修 {p['elective_credits']}")
        if p.get("free_days"):
            print(f"      整天空闲: {'、'.join(p['free_days'])} 无课"
                  f"（每周上课 {len(p['days_used'])} 天）")
        else:
            print(f"      无整天空闲（{', '.join(p['days_used'])} 均有课）")
        for mc in p.get("meal_conflicts", []):
            print(f"      ! {mc['day']} {mc['meal']}（{mc['window']}）被占用: "
                  + "、".join(f"{c['code']} {c['times']}" for c in mc["courses"]))
        for d in p["course_details"]:
            print(f"      {d['code']:10} [{d['section']:4}] {d['datetime']:28} "
                  f"{', '.join(d['instructors'])}")
        for w in p["waiver_required"]:
            print(f"      ! waiver: {w['code']}  pre-req: {w['prerequisites']}")
        for a in p.get("pre_enroll_advice", []):
            print(f"      ! 预选课 drop 建议: {a['code']}  "
                  f"({a['score']:+.2f} < 方案最低 {a['min_plan_score']:+.2f})，"
                  f"需 waiver")
        for n in p["notes"]:
            print(f"      ! {n}")


if __name__ == "__main__":
    main()
