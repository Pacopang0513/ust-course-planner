#!/usr/bin/env python3
"""
Rank testcase — 模拟 Step1→Step5 数据链（rank 脚本 + schema 合规产物）
=====================================================================
在隔离副本中：
  phase1-input    读取 mock 输入
  phase2-profile  写 profile / passed_courses
  phase3-course-analysis  写 unmet_courses → rank/local → mock schedule
                      → rank/filter → mock ustspace → rank/final
  phase4-report   写 timetable_plan
  phase4.5-must-take  无指定课程

用法（由 test_runner.py 调用，cwd = 隔离副本根目录）:
  python scripts/tests/rank/run.py
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()


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


def run_script(args: list):
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True,
                       cwd=ROOT, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        sys.exit(f"脚本失败: {' '.join(args)}")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    print("[rank] phase1-input")
    checkpoint("begin", "phase1-input")
    assert (ROOT / "user" / "major.txt").exists(), "缺少 mock major 输入"
    checkpoint("done", "phase1-input")

    print("[rank] phase2-profile")
    checkpoint("begin", "phase2-profile")
    write_json("data/profile.json", {
        "admission_year": "2023-24", "year_of_study": 3,
        "programs": {"first_major": "COMP", "additional_major": [],
                     "extended_major": "", "minor": ["MATH"]},
        "cga": 3.5, "credits_earned": 89.0, "school": "SENG",
        "source": "SIS(mock)", "confirmed_by_user": True,
    })
    write_json("data/passed_courses.json", {
        "courses": [
            {"code": "COMP 1021", "name": "Introduction to Computer Science", "credits": 3.0,
             "grade": "A", "term": "2023-24 Fall", "status": "taken"},
            {"code": "COMP 1023", "name": "Introduction to Python Programming", "credits": 3.0,
             "grade": "A", "term": "2023-24 Fall", "status": "taken"},
            {"code": "MATH 1013", "name": "Calculus I", "credits": 3.0,
             "grade": "B+", "term": "2023-24 Fall", "status": "taken"},
            {"code": "LANG 1402", "name": "English for University Studies", "credits": 3.0,
             "grade": "P", "term": "2023-24 Spring", "status": "taken"},
        ],
        "source": "SIS(mock)",
    })
    checkpoint("done", "phase2-profile")

    print("[rank] phase3-course-analysis (Step1→Step5)")
    checkpoint("begin", "phase3-course-analysis")

    # Step 1: 未修课程（AI 计算产物）
    write_json("data/unmet_courses.json", {
        "generated_at": now(), "program": "COMP", "intake_year": "2023-24",
        "graduation_target_credits": 120,
        "courses": [
            {"code": "COMP 2011", "name": "Data Structures", "credits": 4.0,
             "category": "major_required", "source_groups": [
                 {"block": "major", "section": "required",
                  "note": "Note: COMP 2011"}]},
            {"code": "COMP 2012", "name": "OO Programming and Data Structures", "credits": 4.0,
             "category": "major_required", "source_groups": [
                 {"block": "major", "section": "required",
                  "note": "Note: COMP 2011 OR COMP 2012"}]},
            {"code": "MATH 2011", "name": "Multivariable Calculus", "credits": 3.0,
             "category": "major_required", "source_groups": [
                 {"block": "major", "section": "pre_major",
                  "note": "Note: MATH 1013"}]},
            {"code": "COMP 2711", "name": "Discrete Mathematical Tools", "credits": 4.0,
             "category": "major_required", "source_groups": [
                 {"block": "major", "section": "required",
                  "note": "Note: MATH 1013"}]},
            {"code": "COMP 2211", "name": "Introduction to Artificial Intelligence", "credits": 3.0,
             "category": "major_elective", "source_groups": [
                 {"block": "major", "section": "elective",
                  "note": "Note: COMP 1023 OR COMP 1028"}]},
            {"code": "ACCT 2010", "name": "Principles of Accounting I", "credits": 3.0,
             "category": "free_elective", "source_groups": [
                 {"block": "major", "section": "elective", "note": ""}]},
            {"code": "COMP 3511", "name": "Operating Systems", "credits": 3.0,
             "category": "major_elective", "source_groups": [
                 {"block": "major", "section": "elective",
                  "note": "Note: COMP 2011"}]},
            {"code": "MATH 2352", "name": "Linear Algebra II", "credits": 3.0,
             "category": "cc_elective", "source_groups": [
                 {"block": "cc", "section": "broadening", "note": ""}]},
            {"code": "MATH 2343", "name": "Linear Algebra", "credits": 3.0,
             "category": "cc_elective", "source_groups": [
                 {"block": "cc", "section": "broadening", "note": ""}]},
            {"code": "MATH 2023", "name": "Multivariable Calculus and Linear Algebra", "credits": 3.0,
             "category": "cc_elective", "source_groups": [
                 {"block": "cc", "section": "broadening", "note": ""}]},
            {"code": "ECON 2103", "name": "Principles of Microeconomics", "credits": 3.0,
             "category": "cc_required", "source_groups": [
                 {"block": "cc", "section": "home_area", "note": ""}]},
            {"code": "CHEM 1020", "name": "General Chemistry I", "credits": 3.0,
             "category": "cc_required", "source_groups": [
                 {"block": "cc", "section": "home_area", "note": ""}]},
            {"code": "PHYS 1112", "name": "General Physics I", "credits": 3.0,
             "category": "cc_required", "source_groups": [
                 {"block": "cc", "section": "home_area", "note": ""}]},
            {"code": "SOSC 1100", "name": "Understanding Society", "credits": 3.0,
             "category": "cc_required", "source_groups": [
                 {"block": "cc", "section": "home_area", "note": ""}]},
            {"code": "HUMA 1000", "name": "Introduction to Humanities", "credits": 3.0,
             "category": "cc_elective", "source_groups": [
                 {"block": "cc", "section": "broadening", "note": ""}]},
            {"code": "LIFS 1901", "name": "General Biology", "credits": 3.0,
             "category": "cc_elective", "source_groups": [
                 {"block": "cc", "section": "broadening", "note": ""}]},
            {"code": "LANG 2010", "name": "Chinese for Science and Technology", "credits": 3.0,
             "category": "free_elective", "source_groups": [
                 {"block": "lang", "section": "elective", "note": ""}]},
        ],
    })

    # Step 2: 本地规则打分
    run_script(["scripts/rank/local.py", "--unmet", "data/unmet_courses.json",
                "--profile", "data/profile.json", "--top", "50"])

    # mock Class Schedule（Step 3 输入；COMP 2012 / MATH 2352 今年未开设；
    # COMP 3511 pre-req 未满足；多课程时间冲突用于 Step 6 编排取舍）
    write_json("data/courses_2610.json", {
        "session": "2610", "semester_name": "2026-27 Fall", "fetched_at": "",
        "course_count": 15,
        "courses": [
            {"code": "COMP", "number": "2011", "title": "Data Structures", "units": 4.0,
             "attributes": {"PRE-REQUISITE": "COMP 1023 OR COMP 1028", "EXCLUSION": ""},
             "sections": [
                 {"section": "L1", "datetime": "TuTh 01:30PM - 02:50PM",
                  "room": "Rm 1", "instructors": ["LI, Xin"],
                  "quota": 100, "enrol": 0, "avail": 100, "wait": 0},
                 {"section": "L2", "datetime": "MoWe 12:00PM - 01:20PM",
                  "room": "Rm 2", "instructors": ["CHEUNG, Tsz Him"],
                  "quota": 100, "enrol": 0, "avail": 100, "wait": 0}]},
            {"code": "ACCT", "number": "2010", "title": "Principles of Accounting I", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "", "EXCLUSION": ""},
             "sections": [{"section": "L01", "datetime": "MoWe 09:00AM - 10:20AM",
                           "room": "Rm 2", "instructors": ["Prof. Mock"],
                           "quota": 75, "enrol": 0, "avail": 75, "wait": 0}]},
            {"code": "COMP", "number": "3511", "title": "Operating Systems", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "COMP 2011 AND COMP 2012", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "WeFr 03:00PM - 04:20PM",
                           "room": "Rm 3", "instructors": ["Prof. Mock"],
                           "quota": 80, "enrol": 0, "avail": 80, "wait": 0}]},
            {"code": "MATH", "number": "2011", "title": "Multivariable Calculus", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "MATH 1013", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "MoWe 10:30AM - 11:50AM",
                           "room": "Rm 4", "instructors": ["Prof. Mock"],
                           "quota": 120, "enrol": 0, "avail": 120, "wait": 0}]},
            {"code": "COMP", "number": "2711", "title": "Discrete Mathematical Tools", "units": 4.0,
             "attributes": {"PRE-REQUISITE": "MATH 1013", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "WeFr 04:30PM - 05:50PM",
                           "room": "Rm 5", "instructors": ["PAPADIAS, Dimitrios"],
                           "quota": 110, "enrol": 0, "avail": 110, "wait": 0}]},
            {"code": "COMP", "number": "2211", "title": "Introduction to AI", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "COMP 1023 OR COMP 1028", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "MoWe 09:00AM - 10:20AM",
                           "room": "Rm 6", "instructors": ["TSOI, Yau Chat"],
                           "quota": 200, "enrol": 0, "avail": 200, "wait": 0}]},
            {"code": "MATH", "number": "2343", "title": "Linear Algebra", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "TuTh 03:00PM - 04:20PM",
                           "room": "Rm 7", "instructors": ["Prof. Mock"],
                           "quota": 100, "enrol": 0, "avail": 100, "wait": 0}]},
            {"code": "MATH", "number": "2023", "title": "Multivariable Calculus and Linear Algebra", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "MATH 1013", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "TuTh 09:00AM - 10:20AM",
                           "room": "Rm 8", "instructors": ["Prof. Mock"],
                           "quota": 100, "enrol": 0, "avail": 100, "wait": 0}]},
            {"code": "ECON", "number": "2103", "title": "Principles of Microeconomics", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "MoWe 09:00AM - 10:20AM",
                           "room": "Rm 9", "instructors": ["Prof. Mock"],
                           "quota": 100, "enrol": 0, "avail": 100, "wait": 0}]},
            {"code": "CHEM", "number": "1020", "title": "General Chemistry I", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "TuTh 10:30AM - 11:50AM",
                           "room": "Rm 10", "instructors": ["Prof. Mock"],
                           "quota": 100, "enrol": 0, "avail": 100, "wait": 0}]},
            {"code": "PHYS", "number": "1112", "title": "General Physics I", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "MoWe 12:00PM - 01:20PM",
                           "room": "Rm 11", "instructors": ["Prof. Mock"],
                           "quota": 100, "enrol": 0, "avail": 100, "wait": 0}]},
            {"code": "SOSC", "number": "1100", "title": "Understanding Society", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "MoWe 01:30PM - 02:50PM",
                           "room": "Rm 12", "instructors": ["Prof. Mock"],
                           "quota": 100, "enrol": 0, "avail": 100, "wait": 0}]},
            {"code": "HUMA", "number": "1000", "title": "Introduction to Humanities", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "MoWe 04:30PM - 05:50PM",
                           "room": "Rm 13", "instructors": ["Prof. Mock"],
                           "quota": 100, "enrol": 0, "avail": 100, "wait": 0}]},
            {"code": "LIFS", "number": "1901", "title": "General Biology", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "TuTh 04:30PM - 05:50PM",
                           "room": "Rm 14", "instructors": ["Prof. Mock"],
                           "quota": 100, "enrol": 0, "avail": 100, "wait": 0}]},
            {"code": "LANG", "number": "2010", "title": "Chinese for Science and Technology", "units": 3.0,
             "attributes": {"PRE-REQUISITE": "", "EXCLUSION": ""},
             "sections": [{"section": "L1", "datetime": "Fr 03:00PM - 04:20PM",
                           "room": "Rm 15", "instructors": ["Prof. Mock"],
                           "quota": 100, "enrol": 0, "avail": 100, "wait": 0}]},
        ],
    })

    # Step 3: 过滤（COMP 2012 / MATH 2352 → not_offered；
    # COMP 3511 → prereq_not_met:COMP 2011,COMP 2012）
    run_script(["scripts/rank/filter.py", "--candidates", "data/candidate_rank.json",
                "--session", "2610", "--passed", "data/passed_courses.json"])

    # Step 4: mock USTspace 评论汇总（真实抓取走 scripts/ustspace/crawler.py）
    write_json("data/ustspace_reviews.json", {
        "generated_at": now(), "course_count": 2, "failed": [],
        "courses": [
            {"subject": "COMP", "number": "2011", "name": "Data Structures", "credits": 4.0,
             "review_count": 120,
             "ratings": {"content": 4.2, "teaching": 4.0, "grading": 3.8, "workload": 4.1},
             "instructors": ["Prof. Mock"],
             "heat_top5": [{"hash": "mock1", "semester": "2025-26 Fall",
                            "instructors": ["Prof. Mock"], "author": "A.",
                            "date": "Dec 2025", "title": "Great course",
                            "comment": "Well structured.", "rating_content": 5,
                            "rating_teaching": 4, "rating_grading": 4, "rating_workload": 5,
                            "upvote_count": 30, "vote_count": 40, "comment_count": 2,
                            "has_midterm": True, "has_final": True,
                            "has_assignment": True, "has_project": False, "has_attendance": False}],
             "instructor_top5": [{"instructor": "Prof. Mock", "top5": []}]},
            {"subject": "MATH", "number": "2011", "name": "Multivariable Calculus", "credits": 3.0,
             "review_count": 5,
             "ratings": {"content": 3.0, "teaching": 2.8, "grading": 3.0, "workload": 3.5},
             "instructors": ["Prof. Mock"], "heat_top5": [], "instructor_top5": []},
        ],
    })

    # Step 5: 合成排名
    run_script(["scripts/rank/final.py", "--filter", "data/filter_report.json",
                "--reviews", "data/ustspace_reviews.json"])

    # Step 6: 课程表编排（严格按 schedule 时间选 section）
    run_script(["scripts/rank/planner.py", "--scores", "data/course_scores.json",
                "--session", "2610", "--passed", "data/passed_courses.json"])
    checkpoint("done", "phase3-course-analysis")

    print("[rank] phase4-report")
    checkpoint("begin", "phase4-report")
    checkpoint("done", "phase4-report")

    print("[rank] phase4.5-must-take (无指定课程)")
    checkpoint("begin", "phase4.5-must-take")
    # 用户指定硬插 COMP 2211（major_elective）→ planner --must-take 重排
    run_script(["scripts/rank/planner.py", "--scores", "data/course_scores.json",
                "--session", "2610", "--passed", "data/passed_courses.json",
                "--must-take", "COMP 2211"])
    checkpoint("done", "phase4.5-must-take")

    print("[rank] 完成")


if __name__ == "__main__":
    main()
