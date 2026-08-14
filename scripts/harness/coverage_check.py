#!/usr/bin/env python3
"""
五类别覆盖率硬性检查 — scripts/harness/coverage_check.py
========================================================
P3（未修清单确认）之前必跑：验证"你认为的全部课程"确实覆盖五大类别——
major / extended_major / minor / school requirement / common core，
每项都以 SIS 真实数据（cache/sis/sis_academic_req.json，权威）或本地
预构建数据源支撑。FAIL = 硬性缺口，禁止向用户展示清单；WARN = 需 AI
核对后放行（本脚本只报告，AI 不得静默忽略）。

数据源登记（每类别在哪搜、地址是什么——经验记录，供复查）：
  major curriculum    : database/curriculum/{AY}/{MAJOR}.json
                         （prog-crs.hkust.edu.hk/ugcourse/{AY}/{MAJOR}/，scripts/prog_crs/build.py 构建）
  extended_major      : database/curriculum/{AY}/EXTM-{CODE}.json（同上 EXTM-{CODE}/）
  minor               : database/curriculum/{AY}/MINOR-{CODE}.json（同上 MINOR-{CODE}/）
  school requirement  : database/curriculum/{AY}/SREQ-{SCHOOL}.json（同上 SREQ-{SCHOOL}/）
  common core 池      : data/cc_courses_{SESSION}.json
                         （w5.ab.ust.hk/wcq/cgi-bin/{SESSION}/common_core/{GROUP}/...，
                           scripts/wcq/crawler.py --admission-year <AY> --session <S>）
  common core 区域表  : database/common-core/areas_{GROUP}.json
                         （scripts/wcq/cc_areas.py --admission-year <AY>）
  SIS 权威（AR）      : cache/sis/sis_academic_req.json
                         （SIS Student Center → Academics → Academic Requirements 页，
                           scripts/sis/parser.py --fetch 抓取）
  已修/预选清单        : data/passed_courses.json（SIS Course History 派生）、data/pre_enrolled.json

规则排除登记（AR not_taken 但未修清单没有，必须能解释）：
  - 备选课：出现在未覆盖 bucket 的 note 里（如 capstone 组 "PHYS 4191 OR PHYS 4291..."）
  - 规则排除：database/course_notes/ 中 course_notes（ext_capstone_pairing /
    h_course_equivalence / track 限制等）——EMIA 4991（主修含 capstone → 只能
    EMIA 4990）、PHYS 4191（Honors 只能 4291）、SCIE 3500/4500（IRE track 专属）

用法:
  python3 scripts/harness/coverage_check.py --session 2610
  （退出码 0=OK；1=有 FAIL；2=仅 WARN）
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from harness.config import load as load_config  # noqa: E402
from harness.decisions import load as load_decisions  # noqa: E402

RE_CODE = re.compile(r"\b([A-Z]{2,4})\s*(\d{4}[A-Z]?)\b")
RE_VALID_CODE = re.compile(r"^[A-Z]{2,4}\s+\d{4}[A-Z]?$")


def norm_code(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).upper()


def load_json(p: Path) -> dict:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return None


def bucket_note_codes(buckets: list) -> set:
    """所有 bucket note 里出现的课程码（备选/OR 表达式中被覆盖的课）。"""
    out = set()
    for b in buckets:
        for a, num in RE_CODE.findall(str(b.get("note", ""))):
            out.add(norm_code(f"{a} {num}"))
    return out


def course_notes_exclusions() -> dict:
    """database/course_notes/*.json → {norm_code: [rule 名]}（规则排除的依据）。"""
    out = {}
    d = ROOT / "database" / "course_notes"
    if not d.exists():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for r in data.get("rules", []):
            rule = r.get("rule") or f.name
            for code in r.get("codes", []) or []:
                out.setdefault(norm_code(code), []).append(rule)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="五类别覆盖率硬性检查")
    ap.add_argument("--session", default="",
                    help="目标学期（如 2610；默认 config.session）")
    args = ap.parse_args(argv)

    cfg = load_config(root=ROOT)
    session = args.session or str(cfg.get("session") or "latest")
    dec = load_decisions(ROOT)
    p1 = dec.get("P1") or {}
    prof = load_json(ROOT / "data" / "profile.json") or {}
    passed = load_json(ROOT / "data" / "passed_courses.json") or {"courses": []}
    unmet = load_json(ROOT / "data" / "unmet_courses.json") or {}
    filt = load_json(ROOT / "data" / "filter_report.json") or {}
    ar = load_json(ROOT / "cache" / "sis" / "sis_academic_req.json") or {}

    ok, warn, fail = [], [], []
    AY = str(prof.get("admission_year") or "")
    prog = prof.get("programs") or {}
    school = str(prof.get("school") or "").strip().upper()
    cur_dir = ROOT / "database" / "curriculum" / AY

    # 已"考虑过"的课程集合：未修候选 ∪ 今年未开设移除 ∪ 已修（含等效课由
    # AR 判定，AR 为权威——见规则登记）。
    considered = {norm_code(c.get("code")) for c in (unmet.get("courses") or [])}
    considered |= {norm_code(c.get("code")) for c in (filt.get("removed") or [])}
    considered |= {norm_code(c.get("code")) for c in (passed.get("courses") or [])}
    notes_codes = bucket_note_codes(unmet.get("buckets") or [])
    exclusions = course_notes_exclusions()

    def ar_not_taken(group_name: str) -> list:
        out = []
        for g in ar.get("requirement_groups", []):
            if group_name(g.get("name", "")):
                out += [c.get("code", "") for c in g.get("courses", [])
                        if c.get("status") == "not_taken"]
        return out

    def check_codes(label: str, codes: list):
        """AR not_taken 名单必须被未修清单覆盖（考虑过），否则按排除登记解释。"""
        for code in codes:
            nc = norm_code(code)
            if nc in considered:
                ok.append(f"{label}: AR 未修 {code} 已在候选/已考虑")
            elif nc in notes_codes:
                ok.append(f"{label}: AR 未修 {code} 由 bucket note 备选覆盖")
            elif nc in exclusions:
                ok.append(f"{label}: AR 未修 {code} 由 course_notes 规则排除"
                          f"（{','.join(exclusions[nc])}）")
            else:
                fail.append(f"{label}: AR 未修 {code} 未被任何候选/规则覆盖 —— 漏算")

    # ── 1. major（主修，SIS AR 权威）───────────────────────────
    majors = [m for m in [prog.get("first_major")] +
              list(prog.get("additional_major") or []) if m]
    for m in majors:
        mf = cur_dir / f"{m}.json"
        if not mf.exists():
            fail.append(f"major {m}: curriculum 缺失 {mf.relative_to(ROOT)}"
                        f"（prog_crs/build.py --year {AY}）")
            continue
        ok.append(f"major {m}: curriculum 存在（{mf.name}）")
        have_major = any(str(b.get("bucket_id", "")).startswith("major")
                         for b in (unmet.get("buckets") or []))
        if not have_major:
            warn.append(f"major {m}: 未修清单无 major 桶（全部满足或脚本漏算，需核对）")
    major_groups = ar_not_taken(
        lambda n: "common core" not in n.lower() and "ext" not in n.lower())
    check_codes("major", major_groups)

    # ── 2. extended_major（扩展主修）────────────────────────────
    ext = str(prog.get("extended_major") or "").strip()
    if ext and ext.upper() != "NA":
        ef = cur_dir / f"EXTM-{ext}.json"
        if not ef.exists():
            fail.append(f"extended_major {ext}: curriculum 缺失 {ef.relative_to(ROOT)}"
                        f"（应为 EXTM-{ext}.json）")
        else:
            ok.append(f"extended_major {ext}: curriculum 存在（EXTM-{ext}.json）")
        have_ext = any(str(b.get("bucket_id", "")).startswith("ext")
                       for b in (unmet.get("buckets") or []))
        if not have_ext:
            warn.append(f"extended_major {ext}: 未修清单无 ext 桶（全部满足或漏算，需核对）")
        check_codes("extended_major",
                    ar_not_taken(lambda n: "ext" in n.lower()))
    else:
        ok.append("extended_major: NA（未声明）")

    # ── 3. minor（副修）────────────────────────────────────────
    minors = prog.get("minor") or []
    if isinstance(minors, str):
        minors = [minors]
    minors = [x for x in minors if str(x).strip().upper() != "NA"]
    if minors:
        for m in minors:
            mf = cur_dir / f"MINOR-{m}.json"
            if not mf.exists():
                warn.append(f"minor {m}: curriculum 缺失 {mf.relative_to(ROOT)}"
                            f"（prog_crs/build.py --year {AY}；副修不纳入未修清单）")
            else:
                ok.append(f"minor {m}: curriculum 存在（MINOR-{m}.json）")
    else:
        ok.append("minor: 未声明（[]）")

    # ── 4. school requirement（学院要求）────────────────────────
    if school:
        sf = cur_dir / f"SREQ-{school}.json"
        if not sf.exists():
            warn.append(f"school {school}: SREQ-{school}.json 缺失"
                        f"（可能该学年无独立学院要求，如 SENG 2025-26 起；"
                        f"以 SIS AR 判定为准）")
        else:
            ok.append(f"school {school}: SREQ 存在（SREQ-{school}.json）")
            have_school = any(str(b.get("bucket_id", "")).startswith("school")
                              for b in (unmet.get("buckets") or []))
            if not have_school:
                ok.append(f"school {school}: 未修清单无 school 桶"
                          f"（学院要求已全部满足）")
    else:
        warn.append("school: profile.school 缺失，无法核查学院要求")

    # ── 5. common core（通识）──────────────────────────────────
    cc_path = ROOT / "data" / f"cc_courses_{session}.json"
    cc_groups = [g for g in ar.get("requirement_groups", [])
                 if "common core" in g.get("name", "").lower()]
    cc_all_satisfied = all(g.get("overall_status") == "satisfied"
                           for g in cc_groups)
    have_cc = any(str(b.get("bucket_id", "")).startswith("cc")
                  for b in (unmet.get("buckets") or []))
    if not cc_path.exists():
        if cc_all_satisfied:
            ok.append("common core: CC 池未抓取，但 AR 显示全部满足")
        else:
            fail.append(f"common core: CC 课程池缺失 {cc_path.relative_to(ROOT)}"
                        f"（CC 缺口无法核算；先跑 wcq/crawler.py"
                        f" --admission-year {AY} --session {session}）")
    else:
        ok.append(f"common core: CC 池存在（{cc_path.name}）")
        if cc_all_satisfied and not have_cc:
            ok.append("common core: AR 显示全部满足")
        elif not have_cc:
            fail.append("common core: AR 显示 CC 未全部满足，但未修清单无 cc 桶"
                        "（CC 缺口漏算）")
        else:
            ok.append(f"common core: 未修清单含 cc 桶"
                      f"（{sum(1 for b in unmet.get('buckets', [])
                              if str(b.get('bucket_id', '')).startswith('cc'))} 个）")

    # ── 输出 ────────────────────────────────────────────────────
    print("五类别覆盖率检查（session %s，入学 %s）:" % (session, AY or "?"))
    for line in ok:
        print(f"  [OK]   {line}")
    for line in warn:
        print(f"  [WARN] {line}")
    for line in fail:
        print(f"  [FAIL] {line}")
    print(f"结论: OK={len(ok)} WARN={len(warn)} FAIL={len(fail)}"
          f" → {'通过' if not fail else '存在硬性缺口，禁止 P3 确认'}")
    return 1 if fail else (2 if warn else 0)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
