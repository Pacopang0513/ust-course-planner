#!/usr/bin/env python3
"""Note 表达式解析/求值测试 — scripts/tests/unit/test_note_eval.py"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from rank.note_eval import complex_note, eval_note, parse, shape  # noqa: E402


FYP = "Note: [COMP 1991 AND (COMP 4981 OR COMP 4981H)] OR [COMP 4910]"


class TestNoteEval(unittest.TestCase):
    def test_fyp_bracket_semantics(self):
        """方括号嵌套：[(A AND (B OR C)) OR D] 语义"""
        met, _ = eval_note(FYP, {"COMP1991", "COMP4981"})
        self.assertTrue(met)
        met, _ = eval_note(FYP, {"COMP1991"})
        self.assertFalse(met)  # 只修 0 学分实习不算满足 FYP
        met, _ = eval_note(FYP, {"COMP4910"})
        self.assertTrue(met)
        met, _ = eval_note(FYP, {"COMP4981H", "COMP1991"})
        self.assertTrue(met)

    def test_or_and_parens(self):
        met, _ = eval_note("Note: (COMP 2011 AND COMP 2012) OR COMP 2012H",
                           {"COMP2011"})
        self.assertFalse(met)
        met, _ = eval_note("Note: (COMP 2011 AND COMP 2012) OR COMP 2012H",
                           {"COMP2011", "COMP2012H"})
        self.assertTrue(met)

    def test_any_n_of(self):
        met, _ = eval_note("any 2 of MATH 1013, MATH 1023, MATH 2011",
                           {"MATH1013", "MATH1023"})
        self.assertTrue(met)
        met, _ = eval_note("any 2 of MATH 1013, MATH 1023, MATH 2011",
                           {"MATH1013"})
        self.assertFalse(met)
        met, _ = eval_note("any 1 of PHYS 1111, PHYS 1112, PHYS 1312",
                           {"PHYS1312"})
        self.assertTrue(met)

    def test_complex_note_detection(self):
        self.assertTrue(complex_note(FYP))
        self.assertTrue(complex_note("(A AND B) OR C"))
        self.assertTrue(complex_note("any 2 of A, B"))
        self.assertFalse(complex_note("PHYS 1111 OR PHYS 1112 OR PHYS 1312"))
        self.assertFalse(complex_note("Common Core (A)"))

    def test_prose_without_codes_unknown(self):
        met, _ = eval_note("Level 3 or above in HKDSE Mathematics", set())
        self.assertIsNone(met)

    def test_shape_string(self):
        s = shape(parse(FYP))
        self.assertIn("or[", s)
        self.assertIn("and[", s)


if __name__ == "__main__":
    unittest.main()
