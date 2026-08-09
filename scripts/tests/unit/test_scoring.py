#!/usr/bin/env python3
"""评分公式纯函数测试 — scripts/tests/unit/test_scoring.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".." / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rank.scoring import (apply_level_bonus, apply_pre_enroll_boost, b_weight,
                          course_avg, heat_points, level_bonus_pct, linear,
                          professor_rating, score_total)


class TestLinear(unittest.TestCase):
    def test_above_baseline(self):
        self.assertAlmostEqual(linear(4.0, 30), 18.0)

    def test_below_baseline_negative(self):
        self.assertAlmostEqual(linear(2.0, 30), -6.0)  # 差评倒扣

    def test_at_baseline_zero(self):
        self.assertAlmostEqual(linear(2.5, 20), 0.0)

    def test_none_returns_zero(self):
        self.assertEqual(linear(None, 30), 0.0)  # 新课 → 0


class TestCourseAvg(unittest.TestCase):
    def test_four_dims(self):
        self.assertAlmostEqual(
            course_avg({"content": 4.0, "teaching": 3.0, "grading": 2.0, "workload": 5.0}),
            3.5)

    def test_missing_dims_ignored(self):
        self.assertAlmostEqual(course_avg({"content": 4.0}), 4.0)

    def test_empty(self):
        self.assertIsNone(course_avg({}))


class TestProfessorRating(unittest.TestCase):
    def test_weighted(self):
        stats = {"ratings": {"teaching": 4.0, "grading": 4.0,
                             "content": 3.0, "workload": 3.0}}
        self.assertAlmostEqual(professor_rating(stats), 3.6)  # 0.3*4+0.3*4+0.2*3+0.2*3

    def test_none_when_no_data(self):
        self.assertIsNone(professor_rating({"ratings": {}}))


class TestHeatPoints(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(heat_points(100), 25.0)
        self.assertEqual(heat_points(80), 25.0)
        self.assertEqual(heat_points(61), 20.0)
        self.assertEqual(heat_points(40), 15.0)
        self.assertEqual(heat_points(21), 10.0)
        self.assertEqual(heat_points(5), 5.0)

    def test_below_min(self):
        self.assertEqual(heat_points(4), 0.0)


class TestBWeight(unittest.TestCase):
    def test_full_weight(self):
        self.assertEqual(b_weight(10, 20), 20.0)

    def test_penalty(self):
        self.assertAlmostEqual(b_weight(3, 20), 12.0)  # 每缺 1 条降 20%

    def test_floor_zero(self):
        self.assertEqual(b_weight(0, 20), 0.0)


class TestLevelBonus(unittest.TestCase):
    def test_required_only(self):
        self.assertEqual(level_bonus_pct("1123", "major_required", False), 5)
        self.assertEqual(level_bonus_pct("2234", "major_required", False), 3)
        self.assertEqual(level_bonus_pct("3123", "major_required", False), 1)
        self.assertEqual(level_bonus_pct("4123", "major_required", False), 0)

    def test_not_required(self):
        self.assertEqual(level_bonus_pct("1123", "cc_elective", False), 0)

    def test_prereq_reference_excluded(self):
        self.assertEqual(level_bonus_pct("1123", "major_required", True), 0)

    def test_apply_positive_only(self):
        self.assertAlmostEqual(apply_level_bonus(80.0, 5), 4.0)
        self.assertEqual(apply_level_bonus(-10.0, 5), 0.0)  # 负分不乘
        self.assertEqual(apply_level_bonus(80.0, 0), 0.0)


class TestScoreTotal(unittest.TestCase):
    def test_sum(self):
        self.assertAlmostEqual(score_total(18.0, 12.0, 15.0, 25.0), 70.0)

    def test_none_ignored(self):
        self.assertAlmostEqual(score_total(None, 12.0, None, 0.0), 12.0)


class TestPreEnrollBoost(unittest.TestCase):
    def test_positive_score_boosted(self):
        self.assertAlmostEqual(apply_pre_enroll_boost(80.0, 0.2), 16.0)  # ×20%

    def test_negative_score_not_boosted(self):
        self.assertEqual(apply_pre_enroll_boost(-10.0, 0.2), 0.0)  # 负分不乘

    def test_zero_boost_noop(self):
        self.assertEqual(apply_pre_enroll_boost(80.0, 0.0), 0.0)

    def test_default_cfg_has_boost(self):
        from rank.scoring import DEFAULT_CFG
        self.assertEqual(DEFAULT_CFG["pre_enroll_boost"], 0.2)


if __name__ == "__main__":
    unittest.main()
