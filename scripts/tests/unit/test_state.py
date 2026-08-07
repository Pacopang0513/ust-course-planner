#!/usr/bin/env python3
"""配置/清单/决策/合约解析测试 — scripts/tests/unit/test_state.py"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))


class TestConfig(unittest.TestCase):
    def test_defaults_without_file(self):
        from harness.config import load
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load(root=tmp)
        self.assertEqual(cfg["scoring"]["weights"]["a"], 30.0)
        self.assertEqual(cfg["defaults"]["target_credits"], 15)
        self.assertEqual(cfg["session"], "latest")

    def test_override(self):
        from harness.config import load
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "config" / "ustplan.json"
            p.parent.mkdir()
            p.write_text(json.dumps({"scoring": {"weights": {"a": 40.0}}}),
                         encoding="utf-8")
            cfg = load(root=tmp)
        self.assertEqual(cfg["scoring"]["weights"]["a"], 40.0)  # 覆盖
        self.assertEqual(cfg["scoring"]["weights"]["b"], 20.0)  # 其余保持


class TestManifest(unittest.TestCase):
    def test_roundtrip(self):
        from harness import manifest
        with tempfile.TemporaryDirectory() as tmp:
            manifest.init(root=tmp, session="2610", admission_year="2026-27")
            m = manifest.load(root=tmp)
            self.assertEqual(m["session"], "2610")
            manifest.step_done(root=tmp, step="step1")
            self.assertEqual(
                manifest.load(root=tmp)["steps"]["step1"]["status"], "done")

    def test_record_artifact_requires_file(self):
        from harness import manifest
        with tempfile.TemporaryDirectory() as tmp:
            ok, errs = manifest.record_artifact(tmp, "data/x.json", "profile", "t")
            self.assertFalse(ok)
            self.assertTrue(any("缺少产物" in e for e in errs))


class TestDecisions(unittest.TestCase):
    def test_set_get(self):
        from harness import decisions
        with tempfile.TemporaryDirectory() as tmp:
            decisions.set_decision(tmp, "P1", {"major": "PHYS", "session": "2610"})
            self.assertEqual(decisions.get_decision(tmp, "P1")["major"], "PHYS")


class TestContracts(unittest.TestCase):
    def test_ctx_session_priority(self):
        from harness import decisions, manifest
        from harness.contracts import ctx_for
        with tempfile.TemporaryDirectory() as tmp:
            manifest.init(root=tmp, session="2620")
            decisions.set_decision(tmp, "P1", {"track": "X"})
            ctx = ctx_for(root=tmp)
            self.assertEqual(ctx["session"], "2620")  # manifest 优先
            self.assertEqual(ctx["track"], "X")

    def test_ctx_fallback_to_config(self):
        from harness.contracts import ctx_for
        with tempfile.TemporaryDirectory() as tmp:
            ctx = ctx_for(root=tmp)
            self.assertEqual(ctx["session"], "latest")  # 无 manifest → config

    def test_next_step_order(self):
        from harness import manifest
        from harness.contracts import next_step, ctx_for
        with tempfile.TemporaryDirectory() as tmp:
            m = manifest.init(root=tmp)
            cp = Path(tmp) / "data" / "checkpoint.json"
            cp.write_text(json.dumps({"completed": [], "current": "phase3-course-analysis"}),
                          encoding="utf-8")
            self.assertEqual(next_step(ctx_for(root=tmp)), "step1")
            manifest.step_done(root=tmp, step="step1")
            self.assertEqual(next_step(ctx_for(root=tmp)), "step3")

    def test_step_precheck_blocks_without_phase(self):
        from harness.contracts import ctx_for, step_precheck
        with tempfile.TemporaryDirectory() as tmp:
            cp = Path(tmp) / "data" / "checkpoint.json"
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps({"completed": [], "current": "phase1-input"}),
                          encoding="utf-8")
            errs = step_precheck(ctx_for(root=tmp), "step1")
            self.assertTrue(any("phase3-course-analysis" in e for e in errs))


class TestDecisionParse(unittest.TestCase):
    def test_kv_with_spaces(self):
        from ustplan import _parse_decision_value
        v = _parse_decision_value("P1", ["major=PHYS", "track=Physics", "and", "Mathematics",
                                         "session=2610"])
        self.assertEqual(v["track"], "Physics and Mathematics")
        # session 按 schema 保持字符串（decisions.schema P1.session type=string）
        self.assertEqual(v["session"], "2610")

    def test_json_value(self):
        from ustplan import _parse_decision_value
        v = _parse_decision_value("P1", ['{"major": "PHYS"}'])
        self.assertEqual(v["major"], "PHYS")


class TestPrereqParser(unittest.TestCase):
    def test_or_and_parens(self):
        from rank.filter import prereq_met
        passed = {"MATH1013", "COMP1021"}
        met, info = prereq_met("(MATH 1013 OR MATH 1023) AND COMP 1021", passed)
        self.assertTrue(met)
        self.assertFalse(info["missing"])
        met2, info2 = prereq_met("MATH 2350 AND COMP 1021", passed)
        self.assertFalse(met2)
        self.assertIn("MATH2350", info2["missing"])  # 规范化课号（去空格）

    def test_unknown_no_code(self):
        from rank.filter import prereq_met
        met, info = prereq_met("Consent of instructor", set())
        self.assertIsNone(met)  # 无课程代码 → 无法判定


class TestSlots(unittest.TestCase):
    def test_parse(self):
        from wcq.conflict import parse_slots
        self.assertEqual(len(parse_slots("TuTh 01:30PM - 02:50PM")), 2)
        self.assertEqual(len(parse_slots("Mo 04:00PM - 05:20PM, Fr 10:00AM - 11:20AM")), 2)
        self.assertEqual(parse_slots("TBA"), [])
        self.assertEqual(len(parse_slots("01-SEP-2026 - 17-OCT-2026We 04:00PM - 05:50PM")), 1)


class TestPlanner(unittest.TestCase):
    def test_section_type(self):
        from rank.planner import section_type
        self.assertEqual(section_type("L1"), "L")
        self.assertEqual(section_type("T01A"), "T")
        self.assertEqual(section_type("LA1"), "LA")

    def test_workload(self):
        from rank.planner import workload
        self.assertEqual(workload(12), "light")
        self.assertEqual(workload(15), "medium")
        self.assertEqual(workload(18), "heavy")

    def test_place_course_lt_component(self):
        """L + T 组件必须各选一节，且不冲突"""
        from rank.planner import place_course
        item = {
            "groups": [
                [{"section": {"section": "L1", "datetime": "Mo 09:00AM - 10:20AM"},
                  "slots": [(0, 540, 620, None, None)]},
                 {"section": {"section": "L2", "datetime": "We 09:00AM - 10:20AM"},
                  "slots": [(2, 540, 620, None, None)]}],
                [{"section": {"section": "T1A", "datetime": "Tu 09:00AM - 09:50AM"},
                  "slots": [(1, 540, 590, None, None)]}],
            ],
        }
        placed = place_course(item, [])
        self.assertIsNotNone(placed)
        self.assertEqual(len(placed), 2)  # L + T 各一节
        # L1 与 T1A 不冲突 → L1+T1A；若 occupied 占用 Mo 9:00，则应选 L2
        placed2 = place_course(item, [(0, 540, 620, None, None)])
        self.assertEqual(placed2[0]["section"]["section"], "L2")

    def test_place_course_conflict_returns_none(self):
        from rank.planner import place_course
        item = {"groups": [
            [{"section": {"section": "L1", "datetime": "Mo 09:00AM - 10:20AM"},
              "slots": [(0, 540, 620, None, None)]}]]}
        self.assertIsNone(place_course(item, [(0, 550, 600, None, None)]))  # 全冲突

    def test_waiver_list(self):
        from rank.planner import waiver_list
        plan = {"details": [
            {"code": "A", "prerequisites": "MATH 1013", "prereq_met": False,
             "prereq_missing": ["MATH 1013"]},
            {"code": "B", "prerequisites": "", "prereq_met": True,
             "prereq_missing": []},
            {"code": "C", "prerequisites": "X OR Y", "prereq_met": None,
             "prereq_missing": []},
        ]}
        w = waiver_list(plan)
        self.assertEqual([x["code"] for x in w], ["A", "C"])


if __name__ == "__main__":
    unittest.main()
