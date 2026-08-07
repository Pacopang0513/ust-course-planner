#!/usr/bin/env python3
"""2026-08-07 修复轮单测：
P1 三字段校验 / manifest session 数字优先 / planner 学分覆盖 /
ext 顶点池 4990/4991 规则（course_notes） / ctx credits_overrides 传递"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


class TestP1ThreeFields(unittest.TestCase):
    """P1 必须显式填写 major/minor/extended_major（三状态：代码/NA/空置不通过）"""

    def _checks(self, p1: dict):
        from harness import decisions, manifest
        from harness.contracts import _phase1_checks, ctx_for
        with tempfile.TemporaryDirectory() as tmp:
            manifest.init(root=tmp, session="2610")
            if p1:
                decisions.set_decision(tmp, "P1", p1)
            return _phase1_checks(ctx_for(root=tmp))

    def test_missing_extended_major_blocked(self):
        errs = self._checks({"major": "PHYS", "minor": "NA", "session": "2610"})
        self.assertTrue(any("extended_major" in e for e in errs))

    def test_missing_minor_blocked(self):
        errs = self._checks({"major": "PHYS", "extended_major": "NA", "session": "2610"})
        self.assertTrue(any("minor" in e for e in errs))

    def test_na_counts_as_given(self):
        errs = self._checks({"major": "PHYS", "minor": "NA", "extended_major": "NA",
                             "session": "2610"})
        self.assertEqual(errs, [])

    def test_empty_p1_blocked(self):
        errs = self._checks({})
        self.assertTrue(any("major" in e for e in errs))
        self.assertTrue(any("minor" in e for e in errs))
        self.assertTrue(any("extended_major" in e for e in errs))


class TestNewestSession(unittest.TestCase):
    def test_numeric_session_wins_over_latest(self):
        from ustplan import _newest_session
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "data"
            d.mkdir()
            # 空跑残留 courses_latest.json 不得干扰真实数字 session
            (d / "courses_latest.json").write_text("{}", encoding="utf-8")
            (d / "courses_2610.json").write_text("{}", encoding="utf-8")
            (d / "courses_2520.json").write_text("{}", encoding="utf-8")
            self.assertEqual(_newest_session(Path(tmp)), "2610")

    def test_only_latest_fallback(self):
        from ustplan import _newest_session
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "data"
            d.mkdir()
            (d / "courses_latest.json").write_text("{}", encoding="utf-8")
            self.assertEqual(_newest_session(Path(tmp)), "latest")


class TestCreditsOverride(unittest.TestCase):
    def _pool(self, overrides):
        from rank.planner import build_pool
        scores = {"courses": [{"code": "PHYS 4291", "name": "Capstone Research",
                               "category": "major_required",
                               "bucket_id": "major-required-16",
                               "bucket_quota": 1, "score": 0.0}]}
        schedule = {"courses": [{"code": "PHYS", "number": "4291", "units": 6.0,
                                 "attributes": {},
                                 "sections": [{"section": "R1", "datetime": "TBA",
                                               "room": "TBA", "instructors": []}]}]}
        return build_pool(scores, schedule, set(), top=50, credits_overrides=overrides)

    def test_override_applies(self):
        pool = self._pool({"PHYS 4291": 3})
        self.assertEqual(pool[0]["credits"], 3.0)

    def test_no_override_keeps_schedule_units(self):
        pool = self._pool({})
        self.assertEqual(pool[0]["credits"], 6.0)


class TestExtCapstonePairing(unittest.TestCase):
    """course_notes 规则：主修含顶点课程（PHYS 4291）→ ext 顶点池移除 EMIA 4991"""

    def test_removes_4991_when_major_has_capstone(self):
        from rank.buckets import apply_course_notes_rules
        courses = [
            {"code": "PHYS 4291", "category": "major_required",
             "bucket_id": "major-required-16"},
            {"code": "EMIA 4990", "category": "major_required",
             "bucket_id": "ext-required-pool-5"},
            {"code": "EMIA 4991", "category": "major_required",
             "bucket_id": "ext-required-pool-5"},
        ]
        buckets = [{"bucket_id": "ext-required-pool-5", "category": "major_required",
                    "quota": 1, "note": "EMIA 4990 OR EMIA 4991"}]
        apply_course_notes_rules(courses, buckets, "PHYS")
        codes = [c["code"] for c in courses]
        self.assertIn("EMIA 4990", codes)
        self.assertNotIn("EMIA 4991", codes)
        self.assertTrue("规则" in buckets[0]["note"])

    def test_keeps_both_without_capstone(self):
        from rank.buckets import apply_course_notes_rules
        courses = [
            {"code": "EMIA 4990", "category": "major_required",
             "bucket_id": "ext-required-pool-5"},
            {"code": "EMIA 4991", "category": "major_required",
             "bucket_id": "ext-required-pool-5"},
        ]
        buckets = [{"bucket_id": "ext-required-pool-5", "category": "major_required",
                    "quota": 1, "note": "EMIA 4990 OR EMIA 4991"}]
        apply_course_notes_rules(courses, buckets, "PHYS")
        self.assertEqual(len(courses), 2)  # 无主修顶点 → 两者保留


class TestCtxCreditsOverrides(unittest.TestCase):
    def test_ctx_passes_through(self):
        from harness import decisions, manifest
        from harness.contracts import ctx_for
        with tempfile.TemporaryDirectory() as tmp:
            manifest.init(root=tmp, session="2610")
            decisions.set_decision(tmp, "P5", {"credits_overrides": {"PHYS 4291": 3}})
            ctx = ctx_for(root=tmp)
            self.assertEqual(ctx["credits_overrides"], {"PHYS 4291": 3})


class TestYearLongAutoSplit(unittest.TestCase):
    """一年制课程：course_notes tags.year_long → planner 自动 units/2"""

    def test_auto_split_from_course_notes(self):
        from rank.planner import build_pool
        # PHYS 4291 已在 database/course_notes/PHYS.json 标 year_long
        scores = {"courses": [{"code": "PHYS 4291", "name": "Capstone Research",
                               "category": "major_required",
                               "bucket_id": "major-required-16",
                               "bucket_quota": 1, "score": 0.0}]}
        schedule = {"courses": [{"code": "PHYS", "number": "4291", "units": 6.0,
                                 "attributes": {},
                                 "sections": [{"section": "R1", "datetime": "TBA",
                                               "room": "TBA", "instructors": []}]}]}
        pool = build_pool(scores, schedule, set(), top=50)  # 无手动覆盖
        self.assertEqual(pool[0]["credits"], 3.0)  # 全年 6 → 每学期 3

    def test_manual_override_wins_over_year_long(self):
        from rank.planner import build_pool
        scores = {"courses": [{"code": "PHYS 4291", "name": "Capstone Research",
                               "category": "major_required",
                               "bucket_id": "major-required-16",
                               "bucket_quota": 1, "score": 0.0}]}
        schedule = {"courses": [{"code": "PHYS", "number": "4291", "units": 6.0,
                                 "attributes": {},
                                 "sections": [{"section": "R1", "datetime": "TBA",
                                               "room": "TBA", "instructors": []}]}]}
        pool = build_pool(scores, schedule, set(), top=50,
                          credits_overrides={"PHYS 4291": 4})
        self.assertEqual(pool[0]["credits"], 4.0)


class TestYearCourseDetect(unittest.TestCase):
    def test_detect_4291(self):
        import tempfile
        from rank.year_courses import detect
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "courses_2610.json").write_text(json.dumps({
                "courses": [{
                    "code": "PHYS", "number": "4291", "title": "Capstone Research",
                    "units": 6.0,
                    "attributes": {"DESCRIPTION": "The course is extended over two "
                                                  "regular terms."},
                }]}), encoding="utf-8")
            hits = detect("2610", data_dir=Path(tmp))
            codes = {h["code"] for h in hits}
            self.assertIn("PHYS 4291", codes)
            h = next(x for x in hits if x["code"] == "PHYS 4291")
            self.assertEqual(h["units"], 6.0)
            self.assertEqual(h["per_semester"], 3.0)  # 全年 6 → 每学期 3


class TestEnrollCart(unittest.TestCase):
    """选课写入：方案 → 清单（TBA 标注 + term 映射）"""

    def _cart(self, tmp):
        from enroll.cart import cmd_build
        import argparse
        plan = {
            "plans": [{"plan_id": "plan-1", "total_credits": 9.0,
                       "course_details": [
                           {"code": "COMP 1944", "section": "L1", "credits": 3.0,
                            "category": "major_elective",
                            "sections": [{"section": "L1", "datetime": "TuTh 04:30PM - 05:50PM"}]},
                           {"code": "PHYS 4291", "section": "TBA", "credits": 3.0,
                            "category": "major_required",
                            "sections": [{"section": "R1", "datetime": "TBA"}]},
                       ]}]}
        pp = Path(tmp) / "timetable_plan.json"
        pp.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        args = argparse.Namespace(plan=str(pp), plan_id="plan-1", session="2610",
                                  data_dir=tmp,
                                  cart=str(Path(tmp) / "enroll_cart.json"))
        cmd_build(args)
        return json.loads((Path(tmp) / "enroll_cart.json").read_text(encoding="utf-8"))

    def test_build_marks_tba_and_term(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            # 模拟真实数据：courses_<SESSION>.json 提供 semester_name（数据驱动，不写死学年）
            (Path(tmp) / "courses_2610.json").write_text(
                json.dumps({"semester_name": "2026-27 Fall"}), encoding="utf-8")
            cart = self._cart(tmp)
            self.assertEqual(cart["term"], "2026-27 Fall")
            self.assertEqual(len(cart["courses"]), 2)
            ok = next(c for c in cart["courses"] if c["code"] == "COMP 1944")
            tba = next(c for c in cart["courses"] if c["code"] == "PHYS 4291")
            self.assertFalse(ok["tba"])
            self.assertTrue(tba["tba"])
            self.assertTrue("不可提交" in tba["note"])


if __name__ == "__main__":
    unittest.main()
