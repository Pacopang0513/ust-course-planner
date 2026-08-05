#!/usr/bin/env python3
"""
Demo testcase — 模拟 phase1-input → phase4.5-must-take 完整流程
================================================================
写 schema 合规产物到 data/ 与 output/，并按顺序推进 checkpoint。

用法（由 test_runner.py 调用，cwd = 隔离副本根目录）:
  python scripts/tests/demo/run.py
  python scripts/tests/demo/run.py --tamper   # 篡改只读文件，演示 R1 失败
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
TAMPER = "--tamper" in sys.argv


def checkpoint(cmd: str, phase: str):
    r = subprocess.run(
        [sys.executable, "scripts/harness/checkpoint.py", cmd, phase],
        capture_output=True, text=True, cwd=ROOT,
    )
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        sys.exit(r.returncode)


def write_json(rel: str, obj: dict):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {rel}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    print("[demo] phase1-input (读取 mock 输入)")
    checkpoint("begin", "phase1-input")
    assert (ROOT / "user" / "major.txt").exists(), "缺少 mock major 输入"
    assert (ROOT / "credentials" / "cookies.txt").exists(), "缺少 mock cookie"
    checkpoint("done", "phase1-input")

    print("[demo] phase2-profile (写画像产物)")
    checkpoint("begin", "phase2-profile")
    write_json("data/profile.json", {
        "admission_year": "2023-24",
        "year_of_study": 3,
        "programs": {"first_major": "COMP", "additional_major": [], "extended_major": "", "minor": ["MATH"]},
        "cga": 3.5,
        "credits_earned": 89.0,
        "school": "SENG",
        "source": "SIS(mock)",
        "confirmed_by_user": True,
    })
    write_json("data/passed_courses.json", {
        "courses": [
            {"code": "COMP 1021", "name": "Introduction to Computer Science", "credits": 3.0,
             "grade": "A", "term": "2023-24 Fall", "status": "taken"},
            {"code": "MATH 1013", "name": "Calculus I", "credits": 3.0,
             "grade": "B+", "term": "2023-24 Fall", "status": "taken"},
            {"code": "LANG 1402", "name": "English for University Studies", "credits": 3.0,
             "grade": "P", "term": "2023-24 Spring", "status": "taken"},
        ],
        "source": "SIS(mock)",
    })
    checkpoint("done", "phase2-profile")

    print("[demo] phase3-course-analysis (写候选课程评分)")
    checkpoint("begin", "phase3-course-analysis")
    write_json("data/course_scores.json", {
        "courses": [
            {"code": "COMP 2011", "name": "Data Structures", "credits": 3.0,
             "timeslots": ["Mon 10:30-11:50"], "instructor": "Prof. Mock",
             "prerequisites": ["COMP 1021"], "exclusions": [],
             "score": 82.0, "score_reason": "grading A-range 20%, good reviews",
             "review_count": 12, "review_confidence": "medium", "open_this_year": True},
            {"code": "MATH 2011", "name": "Multivariable Calculus", "credits": 3.0,
             "timeslots": ["Wed 13:30-14:50"], "instructor": "Prof. Mock",
             "prerequisites": ["MATH 1013"], "exclusions": [],
             "score": 70.0, "score_reason": "grading strict",
             "review_count": 8, "review_confidence": "low", "open_this_year": True},
        ],
        "generated_at": now(),
    })
    checkpoint("done", "phase3-course-analysis")

    print("[demo] phase4-report (写课程表方案)")
    checkpoint("begin", "phase4-report")
    write_json("output/timetable_plan.json", {
        "plans": [
            {"plan_id": "plan-1", "courses": ["COMP 2011", "MATH 2011"],
             "total_credits": 15.0, "workload": "medium",
             "cc_credits": 3.0, "major_credits": 9.0, "elective_credits": 3.0,
             "no_conflict": True, "must_take_inserted": []},
            {"plan_id": "plan-2", "courses": ["COMP 2011"],
             "total_credits": 12.0, "workload": "light",
             "cc_credits": 6.0, "major_credits": 6.0, "elective_credits": 0.0,
             "no_conflict": True, "must_take_inserted": []},
        ],
        "generated_at": now(),
    })
    write_json("output/final_report.md", {"_note": "markdown 模板产物（无 schema 跳过校验）"})
    checkpoint("done", "phase4-report")

    print("[demo] phase4.5-must-take (无指定课程, 维持原方案)")
    checkpoint("begin", "phase4.5-must-take")
    checkpoint("done", "phase4.5-must-take")

    if TAMPER:
        ro = ROOT / "skills" / "README.md"
        with open(ro, "a", encoding="utf-8") as f:
            f.write("\ntampered-by-demo\n")
        print("[demo] !! tamper: skills/README.md 已修改")

    print("[demo] 完成")


if __name__ == "__main__":
    main()
