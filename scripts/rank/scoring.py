#!/usr/bin/env python3
"""
评分公式纯函数 — scripts/rank/scoring.py
========================================
Step 5 Bucket 评分 A+B+C+D 的纯函数实现（无 I/O，可单测）。

公式（config/ustplan.json → scoring 节，内置默认与产品参数一致）：
  课程得分 = A + B + C + D                        （满分 100，可负分）
  A = (课程四维均分 − baseline) / baseline × wA     # 均分<baseline 倒扣；新课 → 0
  B = (本学期教授评分综合 − baseline) / baseline × wB
      教授评分综合 = Σ(维度均分 × 维度权重)
      本学期教授总评论数 < min_reviews_for_score：每少 1 条降
        weight_penalty_per_missing × 原始权重；新教授 → wB=0
  C = 评论热度档位分（heat_tiers 降序命中）
      review_count < min_reviews_for_score → 总分直接 0（由调用方判定）
  D = 本学期任课教授最近 5 条评论 AI 精读评分（0~25，来自 review_summary）

  major_required 低阶加分：level_bonus 按课号千位（1xxx +5% …）
  （对当前总分，负分不乘）

  预选课加分：pre_enroll_boost（默认 0.2）——学校 Pre-Enroll 课程往往比普通
  候选更重要，评分完成后对总分 ×(1+boost)（含低阶加分之后，负分不乘）。
"""

import re

DEFAULT_CFG = {
    "baseline": 2.5,
    "weights": {"a": 30.0, "b": 20.0, "c": 25.0, "d": 25.0},
    "professor": {"teaching": 0.3, "grading": 0.3, "content": 0.2, "workload": 0.2},
    "heat_tiers": [
        {"min_reviews": 80, "points": 25.0},
        {"min_reviews": 60, "points": 20.0},
        {"min_reviews": 40, "points": 15.0},
        {"min_reviews": 20, "points": 10.0},
        {"min_reviews": 5, "points": 5.0},
    ],
    "min_reviews_for_score": 5,
    "weight_penalty_per_missing": 0.2,
    "level_bonus": {"1": 5, "2": 3, "3": 1},
    "pre_enroll_boost": 0.2,
}


def _mean(vals: list):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None


def linear(rating, weight: float, baseline: float = 2.5) -> float:
    """(rating − baseline) / baseline × weight；无评分返回 0（权重作废）"""
    if rating is None:
        return 0.0
    return (rating - baseline) / baseline * weight


def course_avg(ratings: dict) -> float:
    """课程四维均分（content/teaching/grading/workload）"""
    return _mean([ratings.get(k) for k in ("content", "teaching", "grading", "workload")])


def professor_rating(stats: dict, prof_weights: dict = None) -> float:
    """教授评分综合 = Σ(维度均分 × 权重)；无数据返回 None"""
    prof_weights = prof_weights or DEFAULT_CFG["professor"]
    parts, weight_sum = [], 0.0
    for k, w in prof_weights.items():
        v = stats.get("ratings", {}).get(k)
        if isinstance(v, (int, float)):
            parts.append(v * w)
            weight_sum += w
    return sum(parts) / weight_sum if parts else None


def heat_points(review_count: int, tiers: list = None) -> float:
    """评论热度档位分（tiers 降序命中首个 min_reviews 阈值）；低于最低档 0"""
    tiers = tiers or DEFAULT_CFG["heat_tiers"]
    for t in tiers:
        if review_count >= t["min_reviews"]:
            return float(t["points"])
    return 0.0


def b_weight(review_count: int, wb: float,
             min_reviews: int = 5, penalty: float = 0.2) -> float:
    """B 组件实际权重：评论数 < min_reviews 每少 1 条降 penalty × wb；下限 0"""
    if review_count >= min_reviews:
        return wb
    return wb * max(0.0, 1 - penalty * (min_reviews - review_count))


def level_bonus_pct(number: str, category: str, prereq_reference: bool,
                    bonus_map: dict = None) -> int:
    """major_required 低阶加分：1xxx +5% / 2xxx +3% / 3xxx +1% / 4xxx+ 0%"""
    bonus_map = bonus_map or DEFAULT_CFG["level_bonus"]
    if category != "major_required" or prereq_reference:
        return 0
    m = re.match(r"(\d)", str(number or ""))
    if not m:
        return 0
    return int(bonus_map.get(m.group(1), 0))


def apply_level_bonus(score: float, pct: int) -> float:
    """对当前总分（负分不乘）加低阶百分比，返回加分点数"""
    if not pct:
        return 0.0
    return round(max(0.0, score) * pct / 100, 2)


def apply_pre_enroll_boost(score: float, boost: float) -> float:
    """预选课加分点数：总分 × boost（负分不乘）。返回加分点数，由调用方叠加。"""
    if not boost:
        return 0.0
    return round(max(0.0, score) * boost, 2)


def score_total(a, b, c, d) -> float:
    return round(sum(x for x in (a, b, c, d) if x is not None), 2)
