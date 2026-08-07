#!/usr/bin/env python3
"""planner 修复回归测试 — scripts/tests/unit/test_planner_fixes.py
覆盖：EXCLUSION 互斥强制、0 学分课程标注与排序、方案多样性（换课/换 section）。"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from wcq.conflict import parse_slots  # noqa: E402
from rank.planner import (build_plan, diversity_swap,  # noqa: E402
                          vary_sections, norm_code)


def mk(code, score=50.0, credits=3.0, category="major_required", bucket=None,
       dt="Mo 09:00AM - 10:20AM", exclusions=None, zero_credit=False,
       all_tba=False, quota=1, passed=False, extra_sections=None):
    groups = []
    if not all_tba:
        secs = [{"section": "L1", "datetime": dt, "room": "Rm",
                 "instructors": ["Prof. T"]}]
        for s in extra_sections or []:
            secs.append({"section": s[0], "datetime": s[1], "room": "Rm",
                         "instructors": ["Prof. T"]})
        groups = [[{"section": s, "slots": parse_slots(s["datetime"])}
                   for s in secs]]
    return {
        "code": code, "name": "", "score": score, "category": category,
        "bucket_id": bucket or f"b-{code.replace(' ', '')}",
        "bucket_quota": quota, "credits": credits, "passed": passed,
        "zero_credit": zero_credit, "sections": groups[0] if groups else [],
        "groups": groups, "all_tba": all_tba,
        "exclusions": [norm_code(c) for c in (exclusions or [])],
        "prerequisites": "", "prereq_met": True, "prereq_missing": [],
    }


class TestExclusion(unittest.TestCase):
    def test_excluded_by_passed_not_placed(self):
        pool = [mk("MATH 2421", score=90, exclusions=["MATH 2411"]),
                mk("COMP 2011", score=50, dt="Mo 01:30PM - 02:50PM")]
        plan = build_plan("t", 6.0, pool, passed_norm={"MATH2411"})
        self.assertIn("COMP 2011", plan["courses"])
        self.assertNotIn("MATH 2421", plan["courses"])
        self.assertTrue(any("互斥" in n for n in plan["notes"]))

    def test_mutual_exclusion_pairwise(self):
        pool = [mk("MATH 2411", score=95, exclusions=["MATH 2421"]),
                mk("MATH 2421", score=90, exclusions=["MATH 2411"])]
        plan = build_plan("t", 6.0, pool)
        self.assertEqual(len(plan["courses"]), 1)

    def test_exclusion_blocked_by_placed_course(self):
        pool = [mk("MATH 2411", score=95, exclusions=["MATH 2421"]),
                mk("MATH 2421", score=90, exclusions=["MATH 2411"]),
                mk("COMP 2011", score=50, dt="Mo 01:30PM - 02:50PM")]
        plan = build_plan("t", 9.0, pool)
        self.assertIn("COMP 2011", plan["courses"])
        self.assertTrue(any(d["code"].startswith("MATH") for d in plan["details"]))


class TestZeroCredit(unittest.TestCase):
    def test_zero_credit_annotation_placement(self):
        pool = [mk("COMP 1991", credits=0.0, zero_credit=True, all_tba=True)]
        plan = build_plan("t", 12.0, pool)
        self.assertIn("COMP 1991", plan["courses"])
        d = next(x for x in plan["details"] if x["code"] == "COMP 1991")
        self.assertTrue(d["zero_credit"])
        self.assertEqual(d["section"], "TBA")
        self.assertEqual(d["sections"][0]["section"], "TBA")
        self.assertEqual(plan["slots"], [])  # 不占排课时间
        self.assertTrue(any("0 学分" in n for n in plan["notes"]))

    def test_zero_credit_sorted_after_real_credit_in_bucket(self):
        pool = [mk("COMP 1991", credits=0.0, zero_credit=True, all_tba=True,
                   bucket="fyp"),
                mk("COMP 4981", credits=6.0, bucket="fyp", score=60)]
        plan = build_plan("t", 6.0, pool)
        self.assertIn("COMP 4981", plan["courses"])
        self.assertNotIn("COMP 1991", plan["courses"])  # 配额被真实学分课占用


class TestDiversity(unittest.TestCase):
    def test_all_required_identical_plans_vary_sections(self):
        pool = [mk("COMP 2011", score=90, dt="Mo 09:00AM - 10:20AM",
                   extra_sections=[("L2", "Tu 09:00AM - 10:20AM")])]
        p1 = build_plan("p1", 3.0, pool)
        p2 = build_plan("p2", 3.0, pool)
        self.assertEqual(sorted(p1["courses"]), sorted(p2["courses"]))
        self.assertFalse(diversity_swap(p2, pool))  # 全必修无换课对象
        self.assertTrue(vary_sections(p2, pool))    # 兜底换 section
        s1 = sorted(x["section"] for x in p1["details"][0]["sections"])
        s2 = sorted(x["section"] for x in p2["details"][0]["sections"])
        self.assertNotEqual(s1, s2)

    def test_diversity_swap_swaps_elective_only(self):
        pool = [mk("COMP 2011", score=95, credits=4.0, dt="Mo 09:00AM - 10:20AM",
                   category="major_required"),
                mk("COMP 2211", score=80, credits=4.0, dt="Tu 09:00AM - 10:20AM",
                   category="major_elective"),
                mk("COMP 2711", score=60, credits=4.0, dt="We 09:00AM - 10:20AM",
                   category="major_elective"),
                mk("COMP 3111", score=40, credits=4.0, dt="We 01:30PM - 02:50PM",
                   category="major_elective")]
        p1 = build_plan("p1", 9.0, pool)
        self.assertEqual(sorted(p1["courses"]),
                         ["COMP 2011", "COMP 2211", "COMP 2711"])
        self.assertEqual(p1["credits"], 12.0)  # 换课需 ≥ MIN_CREDITS 才可行
        p2 = copy.deepcopy(p1)
        self.assertTrue(diversity_swap(p2, pool))
        self.assertIn("COMP 2011", p2["courses"])     # 必修不动
        self.assertNotIn("COMP 2711", p2["courses"])  # 低分选修被换出
        self.assertIn("COMP 3111", p2["courses"])     # 备选换入


class TestPreEnrolled(unittest.TestCase):
    def test_pre_enrolled_slot_conflict_not_placed(self):
        pool = [mk("COMP 2011", score=90, dt="Mo 09:00AM - 10:20AM"),
                mk("MATH 2011", score=50, dt="Tu 09:00AM - 10:20AM")]
        pre_slots = parse_slots("Mo 09:00AM - 10:20AM")
        plan = build_plan("t", 6.0, pool, pre_slots=pre_slots)
        self.assertNotIn("COMP 2011", plan["courses"])
        self.assertIn("MATH 2011", plan["courses"])


if __name__ == "__main__":
    unittest.main()
