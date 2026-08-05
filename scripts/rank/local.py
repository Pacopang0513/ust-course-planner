#!/usr/bin/env python3
"""
候选课程本地规则打分 — scripts/rank/local.py
============================================
Step 2：从"未修课程"（data/unmet_courses.json，Step 1 产物）按确定性规则打分，
输出 Top N（默认 50）候选 → data/candidate_rank.json。

规则（纯本地、确定性，无网络）：
  - 课程类别：必修 > CC 必修 > 专业选修 > 自由选修
  - 课程编号等级：低年级课（1000-2000 级）优先于高年级（可先修）
  - 学分紧迫度：距离 120 学分差额 ÷ 剩余 Regular Term 数（剩余学期越少越紧迫）
  - OR 池内课程：同等分（选择交给后续步骤）

 用法:
  python3 scripts/rank/local.py --unmet data/unmet_courses.json --top 50
  python3 scripts/rank/local.py --unmet data/unmet_courses.json --top 50 --output data/candidate_rank.json
  python3 scripts/rank/local.py --unmet data/unmet_courses.json --top 50 --keep-major
      # --keep-major：必修/专业选修（major_required/major_elective）强制进入 Top N，
      #   避免 4xxx 级必修课因等级分低被 CC 池挤出候选池（2026-08 实测问题）
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CATEGORY_PRIORITY = {
    "major_required": 100,
    "cc_required": 80,
    "major_elective": 60,
    "cc_elective": 40,
    "free_elective": 20,
}


def _level(course: dict) -> int:
    """课程编号等级 → 优先级（1000 级最高）"""
    number = str(course.get("number") or "")
    if not number:
        # unmet_courses 产物无 number 字段，从 code（如 "COMP 2011"）兜底提取课号
        m2 = re.search(r"(\d{4}[A-Z]?)$", str(course.get("code") or ""))
        number = m2.group(1) if m2 else ""
    m = re.match(r"(\d)", number)
    if not m:
        return 50
    level = int(m.group(1)) * 1000
    if level <= 2000:
        return 100
    if level <= 3000:
        return 70
    if level <= 4000:
        return 40
    return 10


def _urgency(profile: dict) -> float:
    """学分紧迫度：剩余学分 / 剩余学期数 → 0-100（越高越紧迫）"""
    try:
        target = profile.get("graduation_credits", 120)
        earned = float(profile.get("credits_earned", 0) or 0)
        year = int(profile.get("year_of_study", 4) or 4)
        remaining_terms = max(1, (4 - year) * 2 + 1)
        remaining_credits = max(0.0, target - earned)
        return min(100.0, remaining_credits / max(1.0, remaining_terms) * 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return 50.0


def score_course(course: dict, urgency: float) -> dict:
    category = course.get("category", "free_elective")
    cat_score = CATEGORY_PRIORITY.get(category, 20)
    lev_score = _level(course)
    # 类别(0-100) 40% + 等级(0-100) 25% + 紧迫度(0-100) 35%
    score = cat_score * 0.40 + lev_score * 0.25 + urgency * 0.35
    return {
        "score": round(score, 2),
        "breakdown": {
            "category": cat_score,
            "level": lev_score,
            "urgency": round(urgency, 2),
        },
    }


def main():
    ap = argparse.ArgumentParser(description="候选课程本地规则打分")
    ap.add_argument("--unmet", default=str(ROOT / "data" / "unmet_courses.json"),
                    help="Step 1 未修课程 JSON")
    ap.add_argument("--profile", default=str(ROOT / "data" / "profile.json"),
                    help="用户画像（紧迫度计算）")
    ap.add_argument("--top", type=int, default=50, help="输出 Top N")
    ap.add_argument("--keep-major", action="store_true",
                    help="必修/专业选修强制入 Top N（防高年级必修被挤出）")
    ap.add_argument("--output", default=str(ROOT / "data" / "candidate_rank.json"))
    args = ap.parse_args()

    unmet_p = Path(args.unmet)
    if not unmet_p.exists():
        sys.exit(f"错误: 找不到 {unmet_p}（先运行 Step 1 生成未修课程列表）")
    unmet = json.loads(unmet_p.read_text(encoding="utf-8"))
    profile = {}
    if Path(args.profile).exists():
        profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))

    urgency = _urgency(profile)
    ranked = []
    for c in unmet.get("courses", []):
        code = c.get("code", "")
        if not code:
            continue
        sc = score_course(c, urgency)
        ranked.append({
            "code": code,
            "name": c.get("name", ""),
            "credits": c.get("credits"),
            "category": c.get("category", "free_elective"),
            "source_groups": c.get("source_groups", []),
            "rule_score": sc["score"],
            "breakdown": sc["breakdown"],
        })
    ranked.sort(key=lambda x: -x["rule_score"])

    # --keep-major：major_required/major_elective 即使分数在 top-N 之外也追加保留
    # （防 4xxx 级必修被低年级 CC 池挤出候选池），追加部分不改变原有分数序
    pool = ranked[: args.top]
    if args.keep_major:
        in_pool = {c["code"] for c in pool}
        pool += [c for c in ranked[args.top:]
                 if c["category"] in ("major_required", "major_elective")
                 and c["code"] not in in_pool]
    in_pool = {c["code"] for c in pool}
    truncated = [c for c in ranked if c["code"] not in in_pool]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "top_n": min(args.top, len(ranked)),
        "total_candidates": len(ranked),
        "rules": {
            "category_weight": 0.40, "level_weight": 0.25, "urgency_weight": 0.35,
            "category_priority": CATEGORY_PRIORITY,
        },
        "courses": pool,
        "truncated": truncated,
    }
    out["truncated"] = [
        {"code": c["code"], "rule_score": c["rule_score"], "category": c["category"]}
        for c in out["truncated"]
    ]
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"规则打分完成: {len(ranked)} 门候选中 Top {out['top_n']} -> {dest}")
    for c in out["courses"][:10]:
        print(f"  {c['rule_score']:6.2f}  {c['code']:14} {c['category']:18} {c['name'][:40]}")


if __name__ == "__main__":
    main()
