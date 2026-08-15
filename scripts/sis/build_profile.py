#!/usr/bin/env python3
"""
SIS 画像基架生成 — scripts/sis/build_profile.py
================================================
Phase 2 机械转换（所有用户一致，AI 不重复从零构建）：
  输入 course_history（+ 可选 transcript / decisions P1 / 目标学期）
  → 输出 data/profile.json + data/passed_courses.json 基架（confirmed_by_user=false）

AI 仅需：复核产物、补充 cga（transcript 缺失时问用户）、确认后置
confirmed_by_user=true。规则与 skills/phase2-profile/SKILL.md 一致：
  - status 白名单：taken/transferred/exempted/in_progress 计入已确定；
    incomplete（挂科）/audit（旁听）/unknown 不算（保留在未修清单）。
  - 无成绩且 term == 目标学期 → in_progress（含 "&nbsp;" 空成绩）。
  - admission_year = 最早修读学期学年；year_of_study = 学年差 + 1（Fall 起算）。
  - programs 回写 decisions.P1（first_major / additional_major / extended_major / minor）。
  - school 按专业前缀推断（可 --school 覆盖；AI 按 AR 豁免情况复核）。

用法:
  python3 scripts/sis/build_profile.py --session 2610 [--course-history cache/sis/sis_course_history.json]
  python3 scripts/sis/build_profile.py --session 2610 --transcript cache/sis/sis_transcript.json
  python3 scripts/sis/build_profile.py --session 2610 --school ""          # 学院要求豁免时置空
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from harness.config import semester_of_session  # noqa: E402

TERM_RE = re.compile(r"^(\d{4})-(\d{2}) (Fall|Spring|Summer|Winter)")
# 计入"已确定"的白名单（与 filter.PASSED_STATUSES / phase2 skill 一致）
KEEP_STATUSES = ("taken", "transferred", "exempted", "in_progress")
# 专业前缀 → 学院（AI 复核：AR 若声明豁免则以 AR 为准，--school "" 置空）
SCHOOL_BY_PREFIX = {
    "COMP": "SENG", "COSC": "SENG", "CPEG": "SENG", "ELEC": "SENG",
    "CENG": "SENG", "MECH": "SENG", "CIVL": "SENG", "BIEN": "SENG",
    "IEEM": "SENG", "ISDN": "SENG", "MATH": "SSCI", "PHYS": "SSCI",
    "CHEM": "SSCI", "DSCT": "SSCI", "LIFS": "SSCI", "OCES": "SSCI",
    "ENVR": "SSCI", "BIOT": "SSCI", "ACCT": "SBM", "ECON": "SBM",
    "FINA": "SBM", "MARK": "SBM", "MGMT": "SBM", "IS": "SBM",
}


def _session_term_label(session: str) -> str:
    """2610 → '2026-27 Fall'"""
    s = str(session or "")
    if not re.fullmatch(r"\d{4}", s):
        return ""
    y = int(s[:2]) + 2000
    sem = semester_of_session(s)
    return f"{y}-{str(y + 1)[2:]} {sem}" if sem else ""


def _load(path, name: str) -> dict:
    if not Path(path).exists():
        sys.exit(f"错误: 缺少 {name}: {path}")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        sys.exit(f"错误: {path} 不是合法 JSON（{e}）")


def build_passed(course_history: dict, target_term_label: str) -> list:
    """course_history → passed_courses.courses[]（status 判定与 phase2 skill 一致）"""
    out = []
    for c in course_history.get("courses", []):
        code = (c.get("code") or "").strip()
        if not code:
            continue
        grade = (c.get("grade") or "").replace("\u00a0", "").replace("&nbsp;", "").strip()
        term = (c.get("term") or "").strip()
        status = (c.get("status") or "unknown").strip()
        if status == "taken" and not grade and term == target_term_label:
            status = "in_progress"  # 目标学期已注册未出成绩
        out.append({
            "code": code,
            "credits": float(c.get("units") or c.get("credits") or 0),
            "grade": grade or "PENDING",
            "term": term,
            "status": status,
        })
    return out


def infer_admission_year(courses: list) -> str:
    terms = []
    for c in courses:
        m = TERM_RE.match(c.get("term", ""))
        if m and c.get("status") in ("taken", "in_progress", "transferred"):
            terms.append(f"{m.group(1)}-{m.group(2)}")
    return sorted(terms)[0] if terms else ""


def infer_year_of_study(admission_year: str, target_label: str) -> int:
    m = TERM_RE.match(target_label or "")
    if not m:
        return 0
    try:
        adm = int(admission_year.split("-")[0])
    except (ValueError, AttributeError):
        return 0
    return max(1, int(m.group(1)) - adm + 1)


def infer_school(major: str) -> str:
    s = (major or "").strip()
    return SCHOOL_BY_PREFIX.get(s.upper().split()[0] if s else "", "")


def main():
    ap = argparse.ArgumentParser(description="SIS 画像基架生成（Phase 2 机械转换）")
    ap.add_argument("--session", required=True, help="目标学期代码（如 2610）")
    ap.add_argument("--course-history",
                    default=str(ROOT / "cache" / "sis" / "sis_course_history.json"))
    ap.add_argument("--transcript",
                    default=str(ROOT / "cache" / "sis" / "sis_transcript.json"),
                    help="可选：读取 CGA（缺失则 profile.cga=null）")
    ap.add_argument("--decisions", default=str(ROOT / "data" / "decisions.json"),
                    help="P1 程序字段（major/minor/extended_major）；缺省仅读已有文件")
    ap.add_argument("--school", default=None,
                    help="学院代码覆盖（如 'SENG'；AR 豁免时传空串 ''）")
    ap.add_argument("--out-dir", default=str(ROOT / "data"))
    args = ap.parse_args()

    ch = _load(args.course_history, "course_history")
    courses = ch.get("courses", [])
    target_label = _session_term_label(args.session)

    passed = build_passed(ch, target_label)
    passed_courses = {"source": "sis_course_history", "courses": passed}

    admission_year = infer_admission_year(courses)
    if not admission_year:
        sys.exit("错误: 无法从课程历史推断入学年份（无 taken/in_progress 记录），"
                 "需用户提供")

    programs = {}
    d_path = Path(args.decisions)
    if d_path.exists():
        p1 = (json.loads(d_path.read_text(encoding="utf-8-sig")).get("P1") or {})
        majors = p1.get("major") or []
        if isinstance(majors, str):
            majors = [majors]
        majors = [m for m in majors if m and str(m).strip().upper() != "NA"]
        if majors:
            programs["first_major"] = majors[0]
            programs["additional_major"] = majors[1:]
        minor = p1.get("minor") or []
        if isinstance(minor, str):
            minor = [] if str(minor).strip().upper() == "NA" else [minor]
        programs["minor"] = minor
        ext = str(p1.get("extended_major") or "").strip()
        if ext and ext.upper() != "NA":
            programs["extended_major"] = ext

    first_major = programs.get("first_major") or courses[0].get("code", "")[:4]
    school = args.school if args.school is not None else infer_school(first_major)

    credits = sum(c["credits"] for c in passed
                  if c["status"] in KEEP_STATUSES)
    cga = None
    if Path(args.transcript).exists():
        try:
            cga = json.loads(Path(args.transcript).read_text(encoding="utf-8-sig")) \
                .get("cga")
        except json.JSONDecodeError:
            pass

    profile = {
        "admission_year": admission_year,
        "year_of_study": infer_year_of_study(admission_year, target_label),
        "programs": programs,
        "cga": cga,
        "credits_earned": float(credits),
        "school": school,
        "source": "sis_course_history",
        "confirmed_by_user": False,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "passed_courses.json").write_text(
        json.dumps(passed_courses, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"passed: {len(passed)} 门（学分 {credits}）")
    print(f"in_progress: {[c['code'] for c in passed if c['status'] == 'in_progress']}")
    print(f"exempted: {[c['code'] for c in passed if c['status'] == 'exempted']}")
    print(f"挂科/旁听（不扣减，保留可重修）: "
          f"{[c['code'] for c in passed if c['status'] not in KEEP_STATUSES]}")
    print(f"profile: 入学 {admission_year} / Year {profile['year_of_study']} / "
          f"school={school or '（未推断，需人工）'}")
    print(f"产物 -> {out_dir}/profile.json, {out_dir}/passed_courses.json")
    print("AI 后续: 复核画像 → 补充 CGA（如缺失）→ 用户确认后置 confirmed_by_user=true")


if __name__ == "__main__":
    main()
