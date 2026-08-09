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
from rank.planner import (build_plan, build_pre_enroll_advice,  # noqa: E402
                          diversity_swap, vary_sections, norm_code, emit)


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


class TestPreEnrollAdvice(unittest.TestCase):
    def test_low_priority_pre_enrolled_advised_drop(self):
        plan = {
            "details": [{"code": "COMP 2011"}, {"code": "MATH 2011"}],
        }
        pre_scored = {"PHYS 1007": {"code": "PHYS 1007", "name": "G",
                                    "score": 30.0}}  # 已 +20% 加权仍低
        pool_by_code = {"COMP 2011": 90.0, "MATH 2011": 70.0}
        advice = build_pre_enroll_advice(plan, pre_scored, pool_by_code)
        self.assertEqual(len(advice), 1)
        a = advice[0]
        self.assertEqual(a["code"], "PHYS 1007")
        self.assertEqual(a["min_plan_score"], 70.0)
        self.assertIn("waiver", a["note"])

    def test_competitive_pre_enrolled_no_advice(self):
        plan = {"details": [{"code": "COMP 2011"}]}
        pre_scored = {"PHYS 1007": {"code": "PHYS 1007", "name": "G",
                                    "score": 85.0}}  # 加权后高于方案最低
        pool_by_code = {"COMP 2011": 70.0}
        self.assertEqual(build_pre_enroll_advice(plan, pre_scored, pool_by_code), [])

    def test_no_placed_courses_no_advice(self):
        plan = {"details": []}
        pre_scored = {"PHYS 1007": {"code": "PHYS 1007", "score": 10.0}}
        self.assertEqual(build_pre_enroll_advice(plan, pre_scored, {}), [])


class TestGroupQuota(unittest.TestCase):
    """池配额句式解析（2026-08 修复 'Any 3 courses of' 不匹配 → quota=1）"""

    def _quota(self, note):
        from rank.buckets import _group_quota
        return _group_quota(note)

    def test_any_n_of(self):
        self.assertEqual(self._quota("Note: any 2 of"), 2)

    def test_any_n_courses_of(self):
        self.assertEqual(self._quota("MATH 2000-level or above Electives "
                                     "(Any 3 courses of the subject)"), 3)

    def test_n_courses_out_of(self):
        self.assertEqual(self._quota("(2 courses out of 5)"), 2)

    def test_n_courses_from(self):
        self.assertEqual(self._quota("8 courses from the specified list"), 8)

    def test_default_one(self):
        self.assertEqual(self._quota("Note: COMP 2011 OR COMP 2012"), 1)


class TestLevelPool(unittest.TestCase):
    """描述性级别池（'MATH 2000-level or above'）从课表生成真实候选"""

    def _blocks(self, note, kind="pool"):
        return [{
            "block": "major", "name": "Major Requirements",
            "sections": [{
                "type": "elective", "name": "Elective Course(s)",
                "groups": [{"subject": "MATH", "kind": kind, "note": note,
                            "courses": []}],
            }],
        }]

    def _sched(self):
        return {"MATH 2011": {"title": "Multivariable Calculus", "units": 3.0},
                "MATH 3312": {"title": "Real Analysis II", "units": 3.0},
                "MATH 4432": {"title": "Algebra II", "units": 3.0},
                "COMP 3211": {"title": "Fundamentals of AI", "units": 3.0}}

    def test_generates_candidates_from_schedule(self):
        from rank.buckets import major_buckets
        courses, buckets = major_buckets(
            self._blocks("MATH 2000-level or above Electives (Any 2 courses "
                         "of the subject and level as specified)"),
            sched_idx=self._sched())
        pool = [c["code"] for c in courses]
        self.assertIn("MATH 2011", pool)   # 非必修的 2xxx 课应保留
        self.assertIn("MATH 3312", pool)
        self.assertIn("MATH 4432", pool)
        self.assertNotIn("COMP 3211", pool)  # subject 不符排除
        self.assertEqual(buckets[0]["quota"], 2)

    def test_level_pool_excludes_required_courses(self):
        """必修已占用的课（同 subject 同 level）不得混入级别池（防重复推荐）"""
        from rank.buckets import major_buckets
        blocks = [{
            "block": "major", "name": "Major Requirements",
            "sections": [
                {"type": "required", "name": "Required Course(s)",
                 "groups": [{"subject": "MATH", "kind": "single", "note": "",
                             "courses": [{"code": "MATH 2011",
                                          "title": "Multivariable Calculus",
                                          "credits": "3", "area": ""}]}]},
                {"type": "elective", "name": "Elective Course(s)",
                 "groups": [{"subject": "MATH", "kind": "pool",
                             "note": "MATH 2000-level or above Electives "
                                     "(Any 2 courses of the subject and "
                                     "level as specified)",
                             "courses": []}]},
            ],
        }]
        courses, buckets = major_buckets(blocks, sched_idx=self._sched())
        pool = [c["code"] for c in courses if c.get("bucket_id") == buckets[-1]["bucket_id"]]
        self.assertNotIn("MATH 2011", pool)  # 必修占用排除
        self.assertIn("MATH 3312", pool)

    def test_level_pool_keeps_pool_quota_with_single_candidate(self):
        from rank.buckets import major_buckets
        sched = {"MATH 3312": {"title": "Real Analysis II", "units": 3.0}}
        courses, buckets = major_buckets(
            self._blocks("MATH 3000-level or above Elective (Any 1 course "
                         "of the subject and level as specified)"),
            sched_idx=sched)
        self.assertEqual(len(courses), 1)
        self.assertEqual(buckets[0]["quota"], 1)
        self.assertIn("-pool-", buckets[0]["bucket_id"])

    def test_nested_level_pools_merged_to_lowest(self):
        from rank.buckets import major_buckets
        blocks = [{
            "block": "major", "name": "Major Requirements",
            "sections": [{
                "type": "elective", "name": "Elective Course(s)",
                "groups": [
                    {"subject": "MATH", "kind": "pool",
                     "note": "MATH 2000-level or above Electives (Any 3 courses "
                             "of the subject and level as specified)",
                     "courses": []},
                    {"subject": "MATH", "kind": "pool",
                     "note": "MATH 3000-level or above Electives (Any 2 courses "
                             "of the subject and level as specified)",
                     "courses": []},
                    {"subject": "MATH", "kind": "pool",
                     "note": "MATH 4000-level or above Electives (Any 2 courses "
                             "of the subject and level as specified)",
                     "courses": []},
                ],
            }],
        }]
        courses, buckets = major_buckets(blocks, sched_idx=self._sched())
        self.assertEqual(len(buckets), 1)  # 嵌套合并为最低级别池
        self.assertEqual(buckets[0]["quota"], 3)
        pool = [c["code"] for c in courses]
        self.assertIn("MATH 3312", pool)


class TestGrading(unittest.TestCase):
    """pre-req 成绩要求（grading）三状态 + 分支绑定判定"""

    def _met(self, pre, passed, grades):
        from rank.filter import prereq_met
        ok, info = prereq_met(pre, passed, grades)
        return ok, info

    def test_grade_met_comparison(self):
        from rank.filter import grade_met
        self.assertTrue(grade_met("A", "A"))
        self.assertFalse(grade_met("B+", "A"))
        self.assertFalse(grade_met("A-", "A"))
        self.assertTrue(grade_met("B", "Pass"))
        self.assertIsNone(grade_met(None, "A"))      # 无成绩记录
        self.assertIsNone(grade_met("X", "A"))       # 格式未知

    def test_grading_not_met_waiver_path(self):
        ok, info = self._met("Grade A or above in PHYS 1312",
                             {"PHYS1312"}, {"PHYS1312": "B"})
        self.assertFalse(ok)
        self.assertIn("成绩", info["note"])
        self.assertEqual(info["grading"][0]["met"], False)

    def test_grading_met(self):
        ok, info = self._met("Grade A or above in PHYS 1312",
                             {"PHYS1312"}, {"PHYS1312": "A"})
        self.assertTrue(ok)

    def test_grading_unknown_needs_review(self):
        ok, info = self._met("Grade A or above in PHYS 1312",
                             {"PHYS1312"}, {})  # 已修但无成绩记录
        self.assertIsNone(ok)

    def test_grading_or_branch_binding(self):
        """OR 分支内成绩判定绑定：一个分支不达标、另一分支满足 → 整体满足"""
        ok, _ = self._met(
            "(Grade A or above in COMP 1023) OR "
            "(Grade A or above in COMP 1021 AND Pass grade in COMP 1028)",
            {"COMP1023", "COMP1021", "COMP1028"},
            {"COMP1023": "B", "COMP1021": "A", "COMP1028": "P"})
        self.assertTrue(ok)

    def test_grading_not_taken_ignored_for_grading(self):
        """未修课程的成绩要求由课程层面 missing 覆盖，不参与成绩判定"""
        ok, info = self._met(
            "(Grade A or above in COMP 1023) OR "
            "(Grade A or above in COMP 1021 AND Pass grade in COMP 1028)",
            {"COMP1021", "COMP1028"},   # 1023 未修
            {"COMP1021": "A", "COMP1028": "P"})
        self.assertTrue(ok)
        g = {x["code"]: x for x in info["grading"]}
        self.assertTrue(g["COMP 1023"]["not_taken"])

    def test_grading_level_no_code_unknown(self):
        ok, _ = self._met("Level 3 or above in HKDSE Mathematics Extended Module M1/M2",
                          set(), {})
        self.assertIsNone(ok)


class TestDayOffAndMeals(unittest.TestCase):
    """排课偏好：整天空闲优先（高权重）+ 正餐时段避让（低权重）"""

    def test_section_reuses_existing_days_for_day_off(self):
        """已有课在 Mon/Tue：候选有 We 与其他天时，优先复用已有天（少 1 天 → 空出整天）"""
        occupied = parse_slots("Mo 09:00AM - 10:20AM") + \
            parse_slots("Tu 09:00AM - 10:20AM")
        pool = [mk("COMP 2011", score=90, dt="We 09:00AM - 10:20AM",
                   extra_sections=[("L2", "Mo 01:30PM - 02:50PM"),
                                   ("L3", "Tu 01:30PM - 02:50PM")])]
        plan = build_plan("t", 3.0, pool, pre_slots=occupied)
        secs = plan["details"][0]["sections"]
        self.assertEqual([s["section"] for s in secs], ["L2"])  # 复用 Mon，不开 We

    def test_section_avoids_lunch_window_when_days_equal(self):
        """同天数下避开午餐保护时段（12:00-14:00）"""
        pool = [mk("COMP 2011", score=90, dt="Mo 12:00PM - 01:20PM",
                   extra_sections=[("L2", "Mo 03:00PM - 04:20PM")])]
        plan = build_plan("t", 3.0, pool)
        secs = plan["details"][0]["sections"]
        self.assertEqual([s["section"] for s in secs], ["L2"])

    def test_meal_conflict_accepted_when_no_alternative(self):
        """无备选时段时，正餐冲突可接受（低权重偏好，不硬性剔除）"""
        pool = [mk("COMP 2011", score=90, dt="We 12:00PM - 01:20PM")]
        plan = build_plan("t", 3.0, pool)
        self.assertIn("COMP 2011", plan["courses"])

    def test_emit_reports_days_free_days_meal_conflicts(self):
        """输出含 days_used / free_days / meal_conflicts 与提示 notes"""
        pool = [mk("COMP 2011", score=90, dt="We 12:00PM - 01:20PM"),
                mk("MATH 2011", score=50, dt="Mo 09:00AM - 10:20AM",
                   category="major_elective")]
        plan = build_plan("t", 6.0, pool)
        plan["plan_id"] = "plan-1"
        out = emit([plan], "2610", 6.0)["plans"][0]
        self.assertEqual(out["days_used"], ["Mon", "Wed"])
        self.assertEqual(out["free_days"], ["Tue", "Thu", "Fri"])
        meals = {m["meal"]: m for m in out["meal_conflicts"]}
        self.assertIn("午餐", meals)
        self.assertEqual(meals["午餐"]["courses"][0]["code"], "COMP 2011")
        self.assertTrue(any("整天空闲" in n for n in out["notes"]))
        self.assertTrue(any("午餐" in n for n in out["notes"]))

    def test_no_day_off_note_when_all_weekdays_used(self):
        pool = [mk("COMP 2011", score=90, dt="Mo 09:00AM - 10:20AM"),
                mk("COMP 2211", score=80, dt="Tu 09:00AM - 10:20AM",
                   category="major_elective"),
                mk("COMP 2711", score=70, dt="We 09:00AM - 10:20AM",
                   category="major_elective"),
                mk("COMP 3111", score=60, dt="Th 09:00AM - 10:20AM",
                   category="major_elective"),
                mk("MATH 2011", score=50, dt="Fr 09:00AM - 10:20AM",
                   category="major_elective")]
        plan = build_plan("t", 15.0, pool)
        plan["plan_id"] = "plan-1"
        out = emit([plan], "2610", 15.0)["plans"][0]
        self.assertEqual(out["free_days"], [])
        self.assertTrue(any("未能实现整天空闲" in n for n in out["notes"]))



    """剩余学期估算（4 年制 8 个主学期含当前）"""

    def _left(self, year, session):
        from rank.buckets import estimate_semesters_left
        return estimate_semesters_left(year, session)

    def test_year3_fall(self):
        self.assertEqual(self._left(3, "2610"), 4)   # 大三上 → 剩 4

    def test_year3_spring(self):
        self.assertEqual(self._left(3, "2630"), 3)   # 大三下（Spring=30）→ 剩 3

    def test_year1_fall(self):
        self.assertEqual(self._left(1, "2610"), 8)

    def test_year4_fall(self):
        self.assertEqual(self._left(4, "2610"), 2)

    def test_missing_or_out_of_range(self):
        self.assertEqual(self._left(None, "2610"), 0)
        self.assertEqual(self._left(5, "2610"), 0)

    def test_next_year_session_works(self):
        """明年 session（2710/2730）不因硬编码 2610 失效（松弛度回归）"""
        self.assertEqual(self._left(3, "2710"), 4)
        self.assertEqual(self._left(3, "2730"), 3)

    def test_unknown_session_safe(self):
        """未知尾号（如 2650）→ 按第 1 学期保守计，不崩溃"""
        self.assertEqual(self._left(3, "2650"), 4)


class TestSemesterOfSession(unittest.TestCase):
    """session → 学期名（config semesters 映射；2026-08 实测 wcq 索引页下拉：
    2610=2026-27 Fall、2520=2025-26 Winter、2530=2025-26 Spring、
    2540=2025-26 Summer → Fall=10/Winter=20/Spring=30/Summer=40）"""

    def _sem(self, session):
        from harness.config import semester_of_session
        return semester_of_session(session)

    def test_known_sessions(self):
        self.assertEqual(self._sem("2610"), "Fall")
        self.assertEqual(self._sem("2620"), "Winter")
        self.assertEqual(self._sem("2630"), "Spring")
        self.assertEqual(self._sem("2640"), "Summer")
        self.assertEqual(self._sem("2520"), "Winter")
        self.assertEqual(self._sem("2530"), "Spring")
        self.assertEqual(self._sem("2540"), "Summer")

    def test_next_year_sessions(self):
        self.assertEqual(self._sem("2710"), "Fall")
        self.assertEqual(self._sem("2720"), "Winter")
        self.assertEqual(self._sem("2730"), "Spring")

    def test_unknown_returns_empty(self):
        self.assertEqual(self._sem("2650"), "")
        self.assertEqual(self._sem(""), "")


if __name__ == "__main__":
    unittest.main()
