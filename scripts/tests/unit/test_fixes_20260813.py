#!/usr/bin/env python3
"""
单测：2026-08 新增修复 — bucket 学分配额聚合 / minor 合并（描述性级别池）/
历史学期教授对照（previous_sessions / next_occurrence / history_compare）

运行（在 scripts/ 目录下，保证 harness/rank 可导入）:
  python tests/unit/test_fixes_20260813.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from harness.config import previous_sessions, semester_of_session  # noqa: E402
from rank import history_compare as hc  # noqa: E402
from rank import buckets  # noqa: E402


# ── ① bucket 学分聚合 ─────────────────────────────────────────

class TestBucketCredits(unittest.TestCase):
    def _courses(self, bid: str, credits_list: list):
        return [{"code": f"COMP 20{n:02d}", "name": "", "credits": c,
                 "category": "major_elective", "bucket_id": bid,
                 "bucket_quota": 1} for n, c in enumerate(credits_list)]

    def test_pool_100_courses_quota1(self):
        """修复核心：3 学分选修池 100 门候选 quota=1 → 3（此前误算 300）"""
        courses = self._courses("major-elective-pool-0", [3.0] * 100)
        buckets_meta = [{"bucket_id": "major-elective-pool-0", "quota": 1}]
        total, unknown = buckets.bucket_credit_sum(courses, buckets_meta)
        self.assertEqual(total, 3.0)
        self.assertEqual(unknown, 0)

    def test_pool_quota3(self):
        courses = self._courses("major-elective-pool-0", [3.0] * 100)
        buckets_meta = [{"bucket_id": "major-elective-pool-0", "quota": 3}]
        total, _ = buckets.bucket_credit_sum(courses, buckets_meta)
        self.assertEqual(total, 9.0)

    def test_median_mixed_credits(self):
        """桶内学分 2/3/4 → median 3 → quota1 = 3"""
        courses = self._courses("major-elective-pool-0", [2.0, 4.0, 3.0])
        buckets_meta = [{"bucket_id": "major-elective-pool-0", "quota": 1}]
        total, _ = buckets.bucket_credit_sum(courses, buckets_meta)
        self.assertEqual(total, 3.0)

    def test_min_mode(self):
        courses = self._courses("major-elective-pool-0", [2.0, 4.0])
        buckets_meta = [{"bucket_id": "major-elective-pool-0", "quota": 2}]
        total, _ = buckets.bucket_credit_sum(courses, buckets_meta, mode="min")
        self.assertEqual(total, 4.0)

    def test_unknown_credits_counted(self):
        courses = self._courses("major-elective-pool-0", [None, None])
        buckets_meta = [{"bucket_id": "major-elective-pool-0", "quota": 1}]
        total, unknown = buckets.bucket_credit_sum(courses, buckets_meta)
        self.assertEqual(total, 0.0)
        self.assertEqual(unknown, 2)

    def test_prereq_reference_excluded(self):
        courses = self._courses("major-required-0", [3.0]) + [{
            "code": "MATH 1013", "name": "", "credits": 3.0,
            "category": "major_required", "bucket_id": "prereq-ref-X",
            "bucket_quota": 1, "prereq_reference": True}]
        buckets_meta = [{"bucket_id": "major-required-0", "quota": 1}]
        total, _ = buckets.bucket_credit_sum(courses, buckets_meta)
        self.assertEqual(total, 3.0)


# ── ① minor 合并：级别池规格解析 ──────────────────────────────

class TestLevelPoolSpec(unittest.TestCase):
    def test_minor_math_note(self):
        note = ("Mathematics Electives (Courses from the specified elective list, "
                "of which at least 6 credits must be at 3000-level or above; and out "
                "of these 6 credits at 3000-level or above, at least 3 credits must be "
                "at 4000-level or above) MATH Mathematics courses at 1000- and 2000- "
                "level (except courses coded from 1000 to 1600) MATH Mathematics "
                "courses at 3000- level or above")
        subj, ranges, excludes = buckets._level_pool_spec(note, "MATH")
        self.assertEqual(subj, "MATH")
        # 1000- and 2000- level = 级别带 1000-2999；3000+（含 4000+ 重复合并）
        self.assertTrue(any(lo == 1000 and hi == 2999 for lo, hi in ranges))
        self.assertTrue(any(lo == 3000 and hi is None for lo, hi in ranges))
        self.assertTrue(any(lo == 4000 and hi is None for lo, hi in ranges))
        self.assertTrue(any(lo == 1000 and hi == 1600 for lo, hi in excludes))

    def test_legacy_style(self):
        subj, ranges, _ = buckets._level_pool_spec("COMP 2000-level or above", "COMP")
        self.assertEqual(subj, "COMP")
        self.assertEqual(ranges, [(2000, None)])

    def test_no_match(self):
        subj, ranges, excludes = buckets._level_pool_spec("Any 6 courses from list", "MATH")
        self.assertEqual((subj, ranges, excludes), ("MATH", [], []))

    def test_group_quota_credit_fallback(self):
        # _group_quota 对 '3 courses from the specified elective list' → 3
        self.assertEqual(buckets._group_quota(
            "Big Data Technology Electives (3 courses from the specified elective list)"), 3)
        # '3 courses out of 4' → 3
        self.assertEqual(buckets._group_quota(
            "MECH 3640 OR MECH 3650 OR MECH 3660 OR MECH 3670 (3 courses out of 4)"), 3)


class TestMinorMerge(unittest.TestCase):
    """major_buckets 以副修参数调用：类别映射 / 描述性级别池候选生成 / 学分配额推导"""

    def _minor_prog(self, group_kind="pool", note="", credits="",
                    courses=None, subject="MATH"):
        return {"requirements": [{"block": "major", "name": "Major Requirements",
                                  "sections": [{"type": "elective", "name": "Elective(s)",
                                                "groups": [{
                                                    "subject": subject, "note": note,
                                                    "credits": credits,
                                                    "kind": group_kind,
                                                    "courses": courses or [], "areas": []}]}]}]}

    def test_category_mapping(self):
        prog = {"requirements": [{"block": "major", "name": "M",
                                  "sections": [{"type": "required", "name": "R",
                                                "groups": [{
                                                    "subject": "PHYS", "note": "",
                                                    "credits": "3", "kind": "single",
                                                    "courses": [{"code": "PHYS 1112",
                                                                 "title": "Calc",
                                                                 "credits": "3"}],
                                                    "areas": []}]}]}]}
        courses, buckets_meta = buckets.major_buckets(
            prog["requirements"], "", prefix="min",
            cat_required="minor_required", cat_elective="minor_elective")
        self.assertEqual(courses[0]["category"], "minor_required")
        self.assertEqual(courses[0]["bucket_id"], "min-required-0")
        self.assertEqual(buckets_meta[0]["category"], "minor_required")

    def test_level_range_candidates_from_schedule(self):
        note = ("Mathematics courses at 1000- and 2000- level "
                "(except courses coded from 1000 to 1600) "
                "Mathematics courses at 3000- level or above")
        sched = {"courses": [
            {"code": "MATH", "number": "1011", "title": "Excluded", "units": 3.0},
            {"code": "MATH", "number": "1611", "title": "A", "units": 3.0},
            {"code": "MATH", "number": "2011", "title": "B", "units": 3.0},
            {"code": "MATH", "number": "3033", "title": "C", "units": 4.0},
            {"code": "PHYS", "number": "2011", "title": "OtherSubj", "units": 3.0},
        ]}
        sched_idx = {f"{c['code']} {c['number']}": c for c in sched["courses"]}
        courses, buckets_meta = buckets.major_buckets(
            self._minor_prog(note=note, credits="18").get("requirements", []),
            "", prefix="min", sched_idx=sched_idx,
            cat_required="minor_required", cat_elective="minor_elective",
            credit_quota=True)
        codes = {c["code"] for c in courses}
        # 1011 在 1000-1600 排除段 → 剔除
        self.assertNotIn("MATH 1011", codes)
        # 1611 在 1000-2000 范围且不在排除段
        self.assertIn("MATH 1611", codes)
        self.assertIn("MATH 2011", codes)
        self.assertIn("MATH 3033", codes)
        # 非 subject 课程不混入
        self.assertNotIn("PHYS 2011", codes)
        # 纯学分描述 → quota = ceil(18/3) = 6
        self.assertEqual(buckets_meta[0]["quota"], 6)
        self.assertEqual(courses[0]["category"], "minor_elective")

    def test_pool_note_codes_fallback(self):
        """'Note: COMP 2011 OR COMP 2012H' 风格（prog-crs 不列 courses）→ 补录"""
        note = ("Big Data Technology Electives (3 courses from the specified "
                "elective list) Note: COMP 2011 OR COMP 2012H Note: COMP 4211")
        courses, buckets_meta = buckets.major_buckets(
            self._minor_prog(note=note, credits="9", subject="COMP").get("requirements", []),
            "", prefix="min", sched_idx=None,
            cat_required="minor_required", cat_elective="minor_elective",
            credit_quota=True)
        codes = {c["code"] for c in courses}
        self.assertIn("COMP 2011", codes)
        self.assertIn("COMP 2012H", codes)
        self.assertIn("COMP 4211", codes)
        self.assertEqual(buckets_meta[0]["quota"], 3)


# ── ③ 历史学期对照 ────────────────────────────────────────────

class TestPlannerHistoryPool(unittest.TestCase):
    """planner.build_pool 消费 history_map：score_effective 降权 + history_advice"""

    def _schedule(self):
        return {"courses": [
            {"code": "MATH", "number": "2023", "title": "M", "units": 3.0,
             "attributes": {},
             "sections": [{"section": "L1",
                           "datetime": "Mo 09:00AM - 10:20AM",
                           "instructors": ["A, X"]}]},
            {"code": "COMP", "number": "2011", "title": "C", "units": 3.0,
             "attributes": {},
             "sections": [{"section": "L1",
                           "datetime": "Tu 09:00AM - 10:20AM",
                           "instructors": ["B, Y"]}]}]}

    def _scores(self):
        return {"courses": [
            {"code": "MATH 2023", "name": "M", "credits": 3.0,
             "category": "major_elective", "bucket_id": "b1",
             "bucket_quota": 1, "score": 80.0},
            {"code": "COMP 2011", "name": "C", "credits": 3.0,
             "category": "major_elective", "bucket_id": "b2",
             "bucket_quota": 1, "score": 60.0}],
            "ranked_out": []}

    def test_effective_score_and_advice(self):
        from rank.planner import build_pool
        history = {"MATH2023": {"penalty_pct": 10, "note": "advice-txt"}}
        pool = build_pool(self._scores(), self._schedule(), set(), 50, {}, history)
        by = {p["code"]: p for p in pool}
        self.assertEqual(by["MATH 2023"]["score_effective"], 72.0)
        self.assertEqual(by["MATH 2023"]["history_advice"], "advice-txt")
        self.assertEqual(by["COMP 2011"]["score_effective"], 60.0)
        self.assertEqual(by["COMP 2011"]["history_advice"], "")

    def test_no_history_keeps_score(self):
        from rank.planner import build_pool
        pool = build_pool(self._scores(), self._schedule(), set(), 50, {}, None)
        by = {p["code"]: p for p in pool}
        self.assertEqual(by["MATH 2023"]["score_effective"], 80.0)
        self.assertEqual(by["MATH 2023"]["history_advice"], "")


class TestPlannerDedup(unittest.TestCase):
    """多栏位 double-count 同课（主修 + 副修/第二主修）不得重复入排：
    多 section 或 TBA 课程此前会被两桶各选一次 → 学分 double count"""

    def _fixture(self, sections, tba=False):
        schedule = {"courses": [
            {"code": "COMP", "number": "2011", "title": "DS", "units": 3.0,
             "attributes": {}, "sections": sections or []}]}
        scores = {"courses": [
            {"code": "COMP 2011", "name": "DS", "credits": 3.0,
             "category": "major_required", "bucket_id": "major-required-0",
             "bucket_quota": 1, "bucket_rank": 1, "score": 80.0,
             "prerequisites": "", "prereq_met": True, "prereq_missing": [],
             "prereq_grading": [], "filter_reasons": [], "review_count": 5,
             "review_confidence": "low", "open_this_year": True},
            {"code": "COMP 2011", "name": "DS", "credits": 3.0,
             "category": "major_required", "bucket_id": "addCOSC-required-0",
             "bucket_quota": 1, "bucket_rank": 1, "score": 75.0,
             "prerequisites": "", "prereq_met": True, "prereq_missing": [],
             "prereq_grading": [], "filter_reasons": [], "review_count": 5,
             "review_confidence": "low", "open_this_year": True}],
            "ranked_out": []}
        return scores, schedule

    def test_multi_section_no_duplicate(self):
        from rank.planner import build_pool, build_plan
        scores, schedule = self._fixture([
            {"section": "L1", "datetime": "Mo 09:00AM - 10:20AM",
             "instructors": ["A"]},
            {"section": "L2", "datetime": "Tu 09:00AM - 10:20AM",
             "instructors": ["B"]}])
        pool = build_pool(scores, schedule, set(), 50, {}, None)
        plan = build_plan("t", 15, pool)
        self.assertEqual(plan["courses"], ["COMP 2011"])
        self.assertEqual(plan["credits"], 3.0)

    def test_tba_no_duplicate(self):
        from rank.planner import build_pool, build_plan
        scores, schedule = self._fixture([])
        pool = build_pool(scores, schedule, set(), 50, {}, None)
        plan = build_plan("t", 15, pool)
        self.assertEqual(plan["courses"], ["COMP 2011"])
        self.assertEqual(plan["credits"], 3.0)


class TestPreviousSessions(unittest.TestCase):
    def test_fall(self):
        self.assertEqual(previous_sessions("2610"), ["2540", "2530"])

    def test_winter(self):
        self.assertEqual(previous_sessions("2620"), ["2610", "2540"])

    def test_spring(self):
        self.assertEqual(previous_sessions("2630"), ["2620", "2610"])

    def test_summer(self):
        self.assertEqual(previous_sessions("2640"), ["2630", "2620"])

    def test_year_rollover(self):
        self.assertEqual(previous_sessions("2510"), ["2440", "2430"])

    def test_invalid(self):
        self.assertEqual(previous_sessions("abc"), [])
        self.assertEqual(previous_sessions("2650"), [])


class TestNextOccurrence(unittest.TestCase):
    def test_fall_target_spring_prev(self):
        # 2610(Fall) + 2530(Spring) → 2630（本学年 Spring）
        self.assertEqual(hc.next_occurrence("2610", "2530"), "2630")

    def test_spring_target_fall_prev(self):
        # 2630(Spring) + 2610(Fall) → 2710（下学年 Fall）
        self.assertEqual(hc.next_occurrence("2630", "2610"), "2710")

    def test_winter_target_fall_prev(self):
        # 2620(Winter) + 2610(Fall) → 2710
        self.assertEqual(hc.next_occurrence("2620", "2610"), "2710")


class TestSemMatches(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(hc.sem_matches("2025-26 Spring", "2530"))

    def test_short_year(self):
        self.assertTrue(hc.sem_matches("2025 Spring", "2530"))

    def test_wrong_term(self):
        self.assertFalse(hc.sem_matches("2025-26 Fall", "2530"))

    def test_wrong_year(self):
        self.assertFalse(hc.sem_matches("2024-25 Spring", "2530"))


class TestHistoryCompute(unittest.TestCase):
    """compute() 端到端：伪造 本学期课表 + 前两学期课表 + raw 评论"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="ust_hc_"))
        cls.data = cls.tmp / "data"
        cls.data.mkdir(parents=True)
        cls.raw = cls.tmp / "raw"
        cls.raw.mkdir(parents=True)
        # 本学期（2610 Fall）：MATH 2023 由 "Li, Wei" 授课
        cls.data.joinpath("courses_2610.json").write_text(json.dumps({
            "courses": [{"code": "MATH", "number": "2023", "title": "Multivariable",
                         "units": 3.0,
                         "sections": [{"section": "L1",
                                       "instructors": ["Li, Wei"],
                                       "datetime": "Mo 09:00AM - 10:20AM"}]}]}),
            encoding="utf-8")
        # 前序 2540（Summer）未开设；2530（Spring）由 "Wang, Xue" 授课
        cls.data.joinpath("courses_2540.json").write_text(json.dumps({
            "courses": [{"code": "MATH", "number": "1111", "title": "Calc",
                         "units": 3.0, "sections": []}]}), encoding="utf-8")
        cls.data.joinpath("courses_2530.json").write_text(json.dumps({
            "courses": [{"code": "MATH", "number": "2023", "title": "Multivariable",
                         "units": 3.0,
                         "sections": [{"section": "L1",
                                       "instructors": ["Wang, Xue"],
                                       "datetime": "Mo 09:00AM - 10:20AM"}]}]}),
            encoding="utf-8")

        def review(instr, sem, teaching, grading, content=4.0, workload=3.0):
            return {"instructors": [{"name": instr}], "semester": sem,
                    "rating_content": content, "rating_teaching": teaching,
                    "rating_grading": grading, "rating_workload": workload}

        # 本学期教授 Li 在这门课评论评分低（teaching/grading 2.x）
        revs = [review("Li, Wei", "2026-27 Fall", 2.5, 2.5),
                review("Li, Wei", "2026-27 Fall", 2.0, 3.0)]
        # 往期教授 Wang 在 2025-26 Spring 评论评分高
        revs += [review("Wang, Xue", "2025-26 Spring", 4.5, 4.5),
                 review("Wang, Xue", "2025-26 Spring", 4.0, 4.0)]
        cls.raw.joinpath("MATH2023.json").write_text(
            json.dumps({"course": {}, "reviews": revs}), encoding="utf-8")

        cls.scores = {"courses": [
            {"code": "MATH 2023", "name": "Multivariable", "credits": 3.0,
             "category": "major_required", "bucket_id": "major-required-0",
             "bucket_quota": 1, "score": 80.0}],
            "ranked_out": []}

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_compute_penalty(self):
        out = hc.compute("2610", self.scores, {}, self.raw, self.data)
        self.assertEqual(out["previous_sessions"], ["2540", "2530"])
        self.assertEqual(len(out["advice"]), 1)
        a = out["advice"][0]
        self.assertTrue(a["offered_prev"])
        self.assertEqual(a["best_prev"]["session"], "2530")
        self.assertIn("Wang, Xue", a["best_prev"]["professors"])
        self.assertGreaterEqual(a["delta"], 0.5)  # 4.25 vs ~2.5
        self.assertEqual(a["penalty_pct"], 10)
        self.assertEqual(a["next_occurrence"]["session"], "2630")

    def test_threshold_not_met(self):
        cfg = {"history": {"threshold": 5.0, "penalty_pct": 10}}
        out = hc.compute("2610", self.scores, {}, self.raw, self.data, cfg)
        self.assertEqual(len(out["advice"]), 1)
        self.assertIsNone(out["advice"][0]["penalty_pct"])

    def test_previous_data_missing(self):
        """前序课表缺失 → 无 advice（优雅降级）"""
        d2 = self.tmp / "data_missing"
        d2.mkdir(exist_ok=True)
        d2.joinpath("courses_2610.json").write_text(
            (self.data / "courses_2610.json").read_text(encoding="utf-8"),
            encoding="utf-8")
        out = hc.compute("2610", self.scores, {}, self.raw, d2)
        self.assertEqual(len(out["advice"]), 0)


if __name__ == "__main__":
    unittest.main()
