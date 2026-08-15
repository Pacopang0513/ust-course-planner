#!/usr/bin/env python3
"""
候选课程过滤 — scripts/rank/filter.py
=====================================
Step 3：对照本学年 Class Schedule（data/courses_{session}.json，由
scripts/wcq/crawler.py 产出）过滤候选：
  1. 今年未开设（不在 schedule）→ 删除
  2. pre-requisite 未满足（对照 schedule 页内联 PRE-REQUISITE + 已修课程）→ 删除
  3. 仅限特定专业学生（Attributes/Remarks 中 "For ... students only"）→ 提示
移除总结写入 data/filter_report.json（供 AI 复核后确认）。

用法:
  python3 scripts/rank/filter.py --session <SESSION>   # 默认读 data/unmet_courses.json（step1 产物）
  python3 scripts/rank/filter.py --session <SESSION> \
      --passed data/passed_courses.json --output data/filter_report.json
  python3 scripts/rank/filter.py --lookup "PHYS 3152" --session <SESSION>   # 本地查课（不联网）

注：--candidates 参数名沿用旧链，默认已指向 unmet_courses.json（产品化输入）；

本地匹配约定（效率固定，见 step1/step3 skill）：
  - 匹配对象是结构化 JSON（courses_{session}.json / cc_courses_{session}.json），
    禁止对 cache/wcq/raw/ 原始 HTML 正则——本地建规范化索引后 O(1) 命中
  - 课号规范化：统一大写、去空格/点（phys 3152 → PHYS3152）；保留字母后缀
    （LANG 1416C ≠ LANG 1416、COMP 4981H ≠ COMP 4981）
  - CC 区域页与 subject 页重复收录同一课 → 去重取 subject 页版本（setdefault）
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 课号提取（PRE-REQUISITE/EXCLUSION/note 文本）：负向前瞻排除描述性课号
# （'COMP 2000-level' / '2000 or above' → 不提取，防假课混入——2026-08 实测）
RE_CODE = re.compile(
    r"([A-Z]{3,4})\s*(\d{4}[A-Z]?)(?!\s*(?:-\s*level|or\s+above|or\s+below|"
    r"and\s+above|or\s+equivalent))",
    re.I)
RESTRICTED = re.compile(r"For ([A-Z /-]+) students only", re.I)

# ── pre-req 成绩要求（grading）──
# 三状态：不存在（无要求）/ 需要某 grading（逐条判定 met）/ 未填入（有 grading
# 语义但解析不出课程码或成绩，如 "Level 3 or above in HKDSE ..." → 需 AI 复核）
GRADE_ORDER = {"A+": 12, "A": 11, "A-": 10, "B+": 9, "B": 8, "B-": 7,
               "C+": 6, "C": 5, "C-": 4, "D": 3, "P": 2, "PASS": 2,
               "F": 0}
RE_GRADE_REQ = re.compile(
    r"(?:grade|level)(?:\s+of)?\s+([A-Z][+-]?|pass)\s+"
    r"(?:or\s+(?:above|better|higher)|above|better|higher)\s+in\s+"
    r"([A-Z]{3,4}\s*\d{4}[A-Z]?)",
    re.I)
RE_GRADE_PASS = re.compile(
    r"pass\s+grade\s+in\s+([A-Z]{3,4}\s*\d{4}[A-Z]?)", re.I)
RE_GRADE_SEMANTIC = re.compile(r"grade|level", re.I)


def grade_met(actual, required) -> bool:
    """成绩满足性：actual ≥ required（等级序 A+ > A > … > P/Pass > F）。
    无成绩记录（actual 空）或格式未知 → 返回 None（无法判定）。"""
    if not str(actual or "").strip():
        return None
    a = GRADE_ORDER.get(str(actual).strip().upper())
    r = GRADE_ORDER.get(str(required or "").strip().upper())
    if a is None or r is None:
        return None
    return a >= r


def parse_grading(text: str, passed_grades: dict, passed: set = None) -> list:
    """从 pre-req 文本提取成绩要求 → [{code, required, actual, met}]。
    passed_grades：{规范化课号: 成绩}（仅白名单状态且有成绩的课）。
    passed：已修课码集合（未修的课标注 not_taken=true、met=None——其成绩要求
    由课程层面 missing 覆盖，不参与成绩判定）。
    met：True 达标 / False 未达标 / None 无法判定（无成绩记录、格式未知）。"""
    out = []
    seen = set()
    for m in RE_GRADE_REQ.finditer(text or ""):
        req, code = m.group(1), re.sub(r"\s+", " ", m.group(2)).upper()
        key = (norm_code(code), req.upper())
        if key in seen:
            continue
        seen.add(key)
        ncode = norm_code(code)
        actual = passed_grades.get(ncode)
        out.append({"code": code, "required": req, "actual": actual or "",
                    "met": grade_met(actual, req),
                    "not_taken": bool(passed is not None and ncode not in passed)})
    for m in RE_GRADE_PASS.finditer(text or ""):
        code = re.sub(r"\s+", " ", m.group(1)).upper()
        key = (norm_code(code), "PASS")
        if key in seen:
            continue
        seen.add(key)
        ncode = norm_code(code)
        actual = passed_grades.get(ncode)
        out.append({"code": code, "required": "Pass", "actual": actual or "",
                    "met": grade_met(actual, "Pass"),
                    "not_taken": bool(passed is not None and ncode not in passed)})
    return out

_SEP_RE_CACHE = {}


def load_json(p: Path) -> dict:
    if not p.exists():
        sys.exit(f"错误: 找不到 {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def schedule_index(schedule: dict) -> dict:
    """{code: course}，code 如 'COMP 2011'"""
    idx = {}
    for c in schedule.get("courses", []):
        code = f"{c.get('code', '')} {c.get('number', '')}".strip()
        if code:
            idx[code] = c
    return idx


def norm_code(s: str) -> str:
    """课号规范化：大写、去空格/点 → 'PHYS3152'；保留字母后缀（1416C/4981H）"""
    return re.sub(r"[\s.]+", "", str(s)).upper()


def schedule_index_norm(schedule: dict) -> dict:
    """{规范化课号: course}，O(1) 命中；同一课号重复收录（CC 区域页 vs subject 页）
    取首个（= subject 页版本，信息更完整）"""
    idx = {}
    for c in schedule.get("courses", []):
        code = f"{c.get('code', '')} {c.get('number', '')}".strip()
        if code:
            idx.setdefault(norm_code(code), c)
    return idx


def lookup_main(args) -> int:
    """--lookup 本地查课：读 courses_{session}.json（合并 cc_courses 兜底），
    规范化课号 O(1) 命中，输出课程/属性/section 信息，不联网"""
    sched = load_json(ROOT / "data" / f"courses_{args.session}.json")
    idx = schedule_index_norm(sched)
    cc_path = ROOT / "data" / f"cc_courses_{args.session}.json"
    if cc_path.exists():
        for area in load_json(cc_path).get("areas", []):
            for c in area.get("courses", []):
                code = f"{c.get('code', '')} {c.get('number', '')}".strip()
                if code:
                    idx.setdefault(norm_code(code), c)
    for raw in args.lookup:
        key = norm_code(raw)
        c = idx.get(key)
        if c is None:
            print(f"[{raw}] 未找到（本学年未开设，或课号拼写不符）")
            continue
        attrs = c.get("attributes") or {}
        print(f"[{c.get('code')} {c.get('number')}] {c.get('title')} "
              f"({c.get('units')} units)")
        for k in ("PRE-REQUISITE", "EXCLUSION", "REMARKS"):
            if attrs.get(k):
                print(f"    {k}: {attrs[k]}")
        secs = c.get("sections") or []
        print(f"    sections: {len(secs)}")
        for s in secs:
            print(f"      {s.get('section')} | {s.get('datetime')} | {s.get('room')} | "
                  f"{', '.join(s.get('instructors') or []) or '-'} | "
                  f"quota {s.get('quota')} enrol {s.get('enrol')} avail {s.get('avail')}")
    return 0


# 计入"已修/已确定"的状态白名单（2026-08 加固：挂科/旁听/异常不得当已修）：
#   taken          已修
#   transferred    转学分（满足要求）
#   exempted       豁免（视同满足）
#   in_progress    在读（视为已确定，不再推荐）
# 排除：incomplete（挂科需重修，应保留在未修清单）、audit（旁听不计学分）、
#       unknown（解析异常，保守不扣）。status 缺失时按 taken 兼容旧数据。
PASSED_STATUSES = {"taken", "transferred", "exempted", "in_progress"}


def passed_set(passed: dict) -> set:
    """已修课程代码集合，去空格统一大写 'COMP2011' / 'COMP 2011'；
    仅收录 PASSED_STATUSES 白名单内的课程。"""
    return {re.sub(r"\s+", "", c.get("code", ""))
            for c in passed.get("courses", [])
            if c.get("code") and c.get("status", "taken") in PASSED_STATUSES}


def _split_top(text: str, sep: str) -> list:
    """按顶层分隔符切分（忽略括号内；分隔符两侧空白任意），返回去空白片段列表"""
    pat = _SEP_RE_CACHE.setdefault(
        sep, re.compile(r"\s+" + re.escape(sep.strip()) + r"\s+"))
    parts, depth, cur = [], 0, ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0:
            m = pat.match(text, i)
            if m:
                parts.append(cur)
                cur = ""
                i = m.end()
                continue
        cur += ch
        i += 1
    parts.append(cur)
    return [p for p in (s.strip() for s in parts) if p]


def _outer_parens(text: str) -> bool:
    """整个文本是否被一对最外层括号包裹（括号内的内容决定）"""
    depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i == len(text) - 1
    return False


def _eval_expr(text: str, passed: set, passed_grades: dict = None) -> tuple:
    """递归解析 pre-req 表达式 → (met: bool|None, missing)。
    - 顶层先按 OR 切分（OR 优先级最低，任一分支满足即可）——与 UST 真实文本
      格式一致（如 "(COMP 2012 OR COMP 2012H) AND COMP 2211"）
    - 分支内再按 AND 切分，必须全部满足；括号组递归求值
    - 无法解析（无课程代码的段/文本结构异常）→ None，需 AI 复核（不删除）
    - 成绩要求（grading）在叶子内判定（与 OR/AND 分支绑定）：
      课程已修但成绩不达标 → 该叶子不满足（如 PHYS 1314 要求 PHYS 1312 达某成绩）
    """
    text = text.strip()
    if not text:
        return True, []
    if not RE_CODE.search(text):
        return None, []

    def ev(t: str) -> tuple:
        t = t.strip()
        if t.startswith("(") and t.endswith(")") and _outer_parens(t):
            return _eval_expr(t[1:-1], passed, passed_grades)
        return _eval_expr(t, passed, passed_grades)

    or_parts = _split_top(text, " OR ")
    if len(or_parts) > 1:
        outcomes = [ev(p) for p in or_parts]
        if any(m is True for m, _ in outcomes):
            return True, []
        miss_all = sorted({c for m, miss in outcomes for c in miss})
        if any(m is None for m, _ in outcomes):
            return None, miss_all
        return False, miss_all

    and_parts = _split_top(text, " AND ")
    if len(and_parts) > 1:
        miss_all, has_unknown = [], False
        for p in and_parts:
            met, miss = ev(p)
            if met is False:
                return False, miss
            if met is None:
                has_unknown = True
            miss_all.extend(miss)
        return (None if has_unknown else True), sorted(set(miss_all))

    if text.startswith("(") and text.endswith(")") and _outer_parens(text):
        return _eval_expr(text[1:-1], passed, passed_grades)

    core = re.sub(r"\([^()]*\)", " ", text)
    codes = {a + b for a, b in RE_CODE.findall(core)}
    if not codes:
        return None, []
    miss = sorted(codes - passed)
    if miss:
        return False, miss
    # 课程层面已满足 → 叶子内成绩要求逐条判定（与分支绑定）
    gs = parse_grading(core, passed_grades or {})
    unk = [g for g in gs if g["met"] is None]
    if unk:
        return None, []
    bad = [g for g in gs if g["met"] is False]
    if bad:
        return False, [f"{g['code']}(成绩需{g['required']})" for g in bad]
    return True, []


def prereq_met(attr_text: str, passed: set, passed_grades: dict = None) -> tuple:
    """解析 pre-requisite 文本 → (判定, 详情)。
    - 返回 met: bool | None（None=无法解析，需 AI 复核，不删除）
    - 详情含 missing / grading（成绩要求逐条）/ note
    - grading 三状态：无要求（不存在）、有要求（逐条 met True/False）、
      grading 语义存在但无法解析（未填入 → None，需 AI 复核）"""
    if not attr_text:
        return True, {"missing": [], "grading": [], "note": "无 pre-req 约束"}
    clean = re.sub(r"\s+", " ", attr_text.strip())
    if not RE_CODE.search(clean):
        if RE_GRADE_SEMANTIC.search(clean):
            return None, {"missing": [], "grading": [],
                          "note": "pre-req 含成绩/等级要求但无课程代码，需 AI 复核"}
        return None, {"missing": [], "grading": [],
                      "note": "pre-req 文本无课程代码，需 AI 复核"}
    met, missing = _eval_expr(clean, passed, passed_grades)
    grading = parse_grading(clean, passed_grades or {}, passed)
    if met is True:
        return True, {"missing": [], "grading": grading, "note": "全部满足"}
    if met is None:
        return None, {"missing": missing, "grading": grading,
                      "note": "含无法解析段（课程或成绩要求），需 AI 复核"}
    bad = [g for g in grading if g["met"] is False and not g.get("not_taken")]
    note = "存在未满足的课程或成绩要求"
    if bad:
        note += "：" + "; ".join(
            f"{g['code']} 需{g['required']} 实得{g['actual'] or '无记录'}"
            for g in bad)
    return False, {"missing": missing, "grading": grading, "note": note}


def _resolve_catalog(args) -> Path:
    """course-catalog 目录：默认取 database/course_catalog/ 下最新入学年份目录
    （按 ARCHITECTURE 设计默认不预构建——目录不存在时返回原路径，兜底查询自然跳过）"""
    if args.course_catalog:
        return Path(args.course_catalog)
    base = ROOT / "database" / "course_catalog"
    if not base.is_dir():
        return base
    years = sorted(d.name for d in base.iterdir() if d.is_dir())
    return base / years[-1] if years else base


def _preq_text(cc: dict) -> str:
    """course_catalog attributes 值可能是 {text,codes} 对象或旧格式字符串"""
    attr = (cc.get("attributes") or {}).get("Prerequisite(s)", "")
    if isinstance(attr, dict):
        return str(attr.get("text", "") or "")
    return attr or ""


def selftest() -> int:
    """解析器自测：AND/OR 优先级、括号组、无法解析段（参考 2026-27 真实格式）"""
    passed = {"COMP1021", "COMP1023", "MATH1013"}
    ok = True

    def check(expr: str, want: bool):
        nonlocal ok
        met, missing = _eval_expr(expr, passed)
        status = "OK" if met is want else "FAIL"
        if met != want:
            ok = False
        print(f"  [{status}] {expr!r:70} → met={met} missing={missing}")

    print("== 真实格式样例 ==")
    check("COMP 1023 OR COMP 1028", True)                      # COMP 2011 的 pre-req
    check("COMP 1021 OR COMP 1022P (prior to 2025-26) OR COMP 1023 OR ISOM 3230 OR ISOM 3320 OR ISOM 3400", True)
    check("(COMP 2012 OR COMP 2012H) AND COMP 2211", False)    # COMP 3211：括号 OR 组 + AND
    # 成绩要求：无成绩数据 → 无法对照（None，需复核）；带成绩 → 逐条判定
    check("(Grade A or above in COMP 1023) OR (Grade A or above in COMP 1021 AND Pass grade in COMP 1028)", None)
    met_g, info_g = prereq_met(
        "Grade A or above in COMP 1023", passed, {"COMP1023": "B"})
    st = "OK" if met_g is False else "FAIL"
    print(f"  [{st}] 'Grade A or above in COMP 1023（已修 B）' → met={met_g} {info_g['note']}")
    ok = ok and met_g is False
    met_g2, _ = prereq_met(
        "Grade A or above in COMP 1023", passed, {"COMP1023": "A"})
    st = "OK" if met_g2 is True else "FAIL"
    print(f"  [{st}] 'Grade A or above in COMP 1023（已修 A）' → met={met_g2}")
    ok = ok and met_g2 is True
    check("Level 3 or above in HKDSE Mathematics Extended Module M1/M2", None)  # 无课程代码 → 复核
    print("== OR 优先（无括号混写） ==")
    check("COMP 2011 AND COMP 2012 OR MATH 1013", True)        # (2011 AND 2012) OR M1013 → True
    check("MATH 1013 AND COMP 2011 OR COMP 2012", False)       # (M1013 AND 2011) OR 2012 → False（旧实现会误判 True）
    check("COMP 2011 OR COMP 2012 AND MATH 1013", False)       # 2011 OR (2012 AND M1013) → False
    print("== AND / OR 基础 ==")
    check("COMP 1021 AND COMP 2011", False)
    check("COMP 1021 OR COMP 2011", True)
    check("COMP 2011 OR COMP 2012", False)
    check("(COMP 1021 OR COMP 2011) AND MATH 1013", True)
    check("", True)
    print("== 本地匹配约定（规范化/后缀/去重） ==")

    def assert_true(name: str, cond: bool):
        nonlocal ok
        print(f"  [{'OK' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    sample = {"courses": [
        {"code": "PHYS", "number": "3152", "title": "Exp Methods I", "units": 3.0,
         "attributes": {"PRE-REQUISITE": "PHYS 1113"}, "sections": []},
        {"code": "LANG", "number": "1416C", "title": "Chinese", "units": 3.0,
         "attributes": {}, "sections": []},
        {"code": "COMP", "number": "4981H", "title": "Final Year Thesis", "units": 6.0,
         "attributes": {}, "sections": []},
    ]}
    idx = schedule_index_norm(sample)
    assert_true("规范化 'phys 3152' → PHYS3152 命中",
                idx.get(norm_code("phys 3152")) is not None)
    assert_true("字母后缀保留 LANG1416C",
                idx.get(norm_code("LANG1416C")) is not None)
    assert_true("后缀不混淆（COMP4981 ≠ COMP4981H）",
                idx.get(norm_code("COMP4981")) is None)
    sample["courses"].append(
        {"code": "PHYS", "number": "3152", "title": "dup copy", "units": 3.0,
         "attributes": {}, "sections": []})
    assert_true("CC/subject 重复收录取首个（subject 页版本）",
                schedule_index_norm(sample).get("PHYS3152")["title"] == "Exp Methods I")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="候选课程过滤（今年开设 + pre-reg，bucket 版）")
    ap.add_argument("--candidates", default=str(ROOT / "data" / "unmet_courses.json"),
                    help="未修清单（bucket 化，step1 产物）")
    ap.add_argument("--session", default="", help="学期代码，对应 data/courses_{session}.json")
    ap.add_argument("--passed", default=str(ROOT / "data" / "passed_courses.json"))
    ap.add_argument("--course-catalog", default="",
                    help="课程目录目录（pre-req 兜底；默认不预构建，存在 database/course_catalog/ 时自动用）")
    ap.add_argument("--output", default=str(ROOT / "data" / "filter_report.json"))
    ap.add_argument("--fill", type=int, default=0,
                    help="kept 不足该数量时自动从候选池补位（默认 0=不补）")
    ap.add_argument("--override", action="append", default=[],
                    help="用户豁免课程 code（如 'PHYS 4291'）：即使硬性删除也放回 kept 并标 user_overridden（教授/系豁免 pre-req 场景）")
    ap.add_argument("--lookup", action="append", default=[],
                    help="本地查课：按规范化课号（如 'PHYS 3152'）从 courses_{session}.json 查询课程与 section（不联网、不依赖候选产物），可多次指定")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if not args.session:
        sys.exit("错误: 缺少 --session（学期代码；运行中的学期可由 ustplan status 查询）")

    if args.selftest:
        sys.exit(selftest())

    if args.lookup:
        sys.exit(lookup_main(args))

    candidates = load_json(Path(args.candidates))
    schedule = load_json(ROOT / "data" / f"courses_{args.session}.json")
    passed = load_json(Path(args.passed)) if Path(args.passed).exists() else {"courses": []}
    done = passed_set(passed)
    # 已修课程成绩表（grading 检查用）：仅白名单状态且有成绩的课
    passed_grades = {re.sub(r"\s+", "", c.get("code", "")).upper(): c.get("grade")
                     for c in passed.get("courses", [])
                     if c.get("code") and c.get("grade")
                     and c.get("status", "taken") in PASSED_STATUSES}
    catalog_dir = _resolve_catalog(args)

    sched = schedule_index(schedule)
    sched_norm = schedule_index_norm(schedule)
    cc_path = ROOT / "data" / f"cc_courses_{args.session}.json"
    if cc_path.exists():
        for area in load_json(cc_path).get("areas", []):
            for c in area.get("courses", []):
                code = f"{c.get('code', '')} {c.get('number', '')}".strip()
                if code:
                    sched_norm.setdefault(norm_code(code), c)
    kept, removed = [], []
    overrides = set(args.override or [])
    bucket_meta = {b["bucket_id"]: b for b in candidates.get("buckets", [])}

    def eval_one(c):
        code = c.get("code", "")
        sc = sched.get(code)
        reasons = []
        pre = ""
        # 未开设课程的 pre-req 上下文为空（此前 UnboundLocalError：not_offered
        # 分支直接 return 时 info 未定义——必修今年不开设时真实触发）
        info = {"missing": [], "grading": [], "note": ""}
        if sc is None:
            reasons.append("not_offered_this_year")
        else:
            # pre-req 检查（schedule 页内联 pre-requisite，优先；缺则查 course_catalog）
            pre = (sc.get("attributes") or {}).get("PRE-REQUISITE", "")
            if not pre:
                cat_file = catalog_dir / f"{code.split()[0]}.json"
                if cat_file.exists():
                    cat = load_json(cat_file)
                    for cc in cat.get("courses", []):
                        if cc.get("code", "").replace(" ", "") == code.replace(" ", ""):
                            pre = _preq_text(cc)
                            break
            ok, info = prereq_met(pre, done, passed_grades)
            if ok is False:
                reasons.append(f"prereq_not_met:{','.join(info['missing'])}")
            elif ok is None:
                reasons.append(f"prereq_unknown:{info['note'][:60]}")
            if info.get("grading"):
                for g in info["grading"]:
                    if g["met"] is False:
                        reasons.append(
                            f"grading_not_met:{g['code']}需{g['required']}"
                            f"实得{g['actual'] or '无记录'}")
                    elif g["met"] is None:
                        reasons.append(
                            f"grading_unknown:{g['code']}需{g['required']}"
                            f"（无成绩记录可对照）")
            # 仅限特定专业提示
            rem = (sc.get("attributes") or {}).get("REMARKS", "")
            m = RESTRICTED.search(rem)
            if m:
                reasons.append(f"restricted:{m.group(1).strip()}")
        return code, sc, reasons, pre, info.get("grading", [])

    for c in candidates.get("courses", []):
        code, sc, reasons, pre_text, grading = eval_one(c)
        entry = {
            "code": code,
            "name": c.get("name", ""),
            "credits": c.get("credits"),
            "category": c.get("category"),
            "bucket_id": c.get("bucket_id"),
            "bucket_quota": c.get("bucket_quota"),
            "schedule_found": sc is not None,
            "sections": len(sc.get("sections") or []) if sc else 0,
            "prereq": {"text": pre_text,
                       "met": (None if any(r.startswith("prereq_unknown")
                                           or r.startswith("grading_unknown")
                                           for r in reasons)
                               else False if any(r.startswith("prereq_not_met")
                                                 or r.startswith("grading_not_met")
                                                 for r in reasons)
                               else True),
                       "missing": [m for r in reasons if r.startswith("prereq_not_met:")
                                   for m in r.split(":", 1)[1].split(",")],
                       "grading": grading},
            "exclusion": {"text": (sc.get("attributes") or {}).get("EXCLUSION", "") if sc else "",
                          "codes": [f"{a} {b}" for a, b in RE_CODE.findall(
                              (sc.get("attributes") or {}).get("EXCLUSION", ""))] if sc else [],
                          "conflicts_with_passed": []},
            "filter_reasons": reasons,
        }
        # EXCLUSION 与已修课程重叠提示（排课阶段 planner 强制互斥检查）
        if sc and entry["exclusion"]["codes"]:
            blocked = [x for x in entry["exclusion"]["codes"]
                       if norm_code(x) in done]
            if blocked:
                entry["exclusion"]["conflicts_with_passed"] = blocked
                entry["filter_reasons"] = reasons + \
                    [f"excluded_by_passed:{','.join(blocked)}"]
        # 硬性删除：仅"今年未开设"；pre-req 未满足 → 保留 + 标记（waiver 是
        # 处理路径，评分与排课不考虑 pre-req；step6 输出 waiver_required 提醒）
        hard = [r for r in reasons if r.startswith("not_offered")]
        if hard and code not in overrides:
            removed.append(entry)
        else:
            if hard and code in overrides:
                entry["filter_reasons"] = reasons + ["user_overridden"]
            kept.append(entry)

    # 补位：kept < --fill 阈值时，从候选池按分数/顺序补入
    filled_from = []
    if args.fill and len(kept) < args.fill:
        need = args.fill - len(kept)
        done_set = {c["code"] for c in kept} | {c["code"] for c in removed}
        for c in candidates.get("courses", []):
            if need <= 0:
                break
            if c["code"] in done_set:
                continue
            code, sc, reasons, pre_text, _grading = eval_one(c)
            done_set.add(code)
            hard = [r for r in reasons if r.startswith("not_offered")]
            if hard:
                continue
            kept.append({
                "code": code, "name": c.get("name", ""),
                "credits": c.get("credits"), "category": c.get("category"),
                "bucket_id": c.get("bucket_id"), "bucket_quota": c.get("bucket_quota"),
                "schedule_found": sc is not None,
                "sections": len(sc.get("sections") or []) if sc else 0,
                "prereq": {"text": pre_text, "met": None, "missing": []},
                "exclusion": {"text": "", "codes": [], "conflicts_with_passed": []},
                "filter_reasons": reasons + ["filled_from_truncated"],
            })
            filled_from.append(code)
            need -= 1
        if filled_from:
            print(f"补位: kept < {args.fill}，补入 {len(filled_from)} 门: "
                  f"{', '.join(filled_from)}")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session": args.session,
        "input_count": len(candidates.get("courses", [])),
        "kept_count": len(kept),
        "removed_count": len(removed),
        "kept": kept,
        "removed": removed,
        "note": ("removed=今年未开设（pre-req 不足不作为删除理由，只标记 waiver）；"
                 "kept 中的 filter_reasons 可能含 prereq_not_met/prereq_unknown/"
                 "excluded_by_passed/restricted/user_overridden 等提示；"
                 "prereq 字段记录 pre-req 原文与判定，供 Step 6 输出 waiver_required"),
        "overrides": sorted(overrides),
    }
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"过滤完成: 输入 {out['input_count']} -> 保留 {len(kept)} / 移除 {len(removed)}")
    for r in removed:
        print(f"  - {r['code']}: {','.join(r['filter_reasons'])}")
    print(f"产物 -> {dest}")


if __name__ == "__main__":
    main()
