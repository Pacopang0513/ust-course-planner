#!/usr/bin/env python3
"""
HKUST SIS (PeopleSoft) 数据解析器
=================================
解析 SIS Production 系统中的个人学术数据：
  - Student Center → 学生基本信息
  - Course History → 课程历史（已修/在读/转学分）
  - Academic Requirements → 毕业要求进度

用法：
  python scripts/sis/parser.py                                # 解析 cache/sis 下已保存的 raw HTML
  python scripts/sis/parser.py --fetch                        # 用 cookie 重新抓取 + 解析
  python scripts/sis/parser.py --cookie-file credentials/cookies.txt  # 指定 cookie 文件

输出：
  cache/sis/sis_course_history.json   课程历史
  cache/sis/sis_academic_req.json     学术要求
  cache/sis/sis_student_info.json     学生信息
"""

import re
import json
import sys
import argparse
from pathlib import Path
from html import unescape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

# ── 配置 ──────────────────────────────────────────────
BASE_URL = "https://sisprod.psft.ust.hk"
PSC_BASE = f"{BASE_URL}/psc/SISPROD/EMPLOYEE/HRMS/c"
ROOT = Path(__file__).resolve().parents[2]
# 项目约定：默认输入/输出目录（原始 HTML + 中间 JSON）
DEFAULT_DIR = str(ROOT / "cache" / "sis")

# Student Center 下拉菜单选项值（实际使用到的）
DROPDOWN_VALUES = {
    "course_history": "2050",
    "academic_requirements": "3010",
    "grades": "1030",
    "transcript": "2035",
}

# PS_TOKEN 过期时 PeopleSoft 返回 200 的"未授权"页面特征（见 WEBSITE_STRUCTURE.md §8.4）
AUTH_FAIL_MARKERS = [
    "you are not authorized",
    "not authorized to",
    "invalid login",
    "session has expired",
    "cas.ust.hk",
]

TERM_RE = re.compile(r"(\d{4})-(\d{2})\s+(Fall|Spring|Summer|Winter)")

# ── 通用工具 ──────────────────────────────────────────

def _is_auth_failure(html: str) -> bool:
    """检测 200 状态码下的登录失效页特征"""
    low = html[:200_000].lower()
    return any(m in low for m in AUTH_FAIL_MARKERS)


def _get_with_retry(url: str, cookies: dict, timeout: int = 30,
                    data: dict = None, allow_redirects: bool = True,
                    retries: int = 3) -> requests.Response:
    """GET/POST + 重试；返回最后一次响应（不 raise，由调用方判断）"""
    last = None
    for _ in range(retries):
        try:
            if data is not None:
                last = SESSION.post(url, data=data, cookies=cookies,
                                    allow_redirects=allow_redirects, timeout=timeout)
            else:
                last = SESSION.get(url, cookies=cookies, timeout=timeout)
            if last.status_code == 200:
                return last
        except requests.RequestException:
            pass
    if last is None:
        raise RuntimeError(f"请求失败（重试 {retries} 次）: {url}")
    return last


def clean_html(text: str) -> str:
    """去除 HTML 标签，解码 HTML 实体，压缩空白"""
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_by_id(html: str, field_id: str, default: str = "") -> str:
    """
    从 PeopleSoft HTML 中按 ID 提取字段值。
    支持多种渲染模式（单/双引号属性）：
      <div id='win0divXXX'><span id='XXX'>VALUE</span></div>
      <span id='XXX'>VALUE</span>
      <input id='XXX' value='VALUE'>
    """
    patterns = [
        rf"id='{re.escape(field_id)}'\s*>\s*<span[^>]*>([^<]*)</span>",
        rf'id="{re.escape(field_id)}"\s*>\s*<span[^>]*>([^<]*)</span>',
        rf"id='{re.escape(field_id)}'\s*>\s*([^<]*)<",
        rf'id="{re.escape(field_id)}"\s*>\s*([^<]*)<',
        rf"id='{re.escape(field_id)}'[^>]*value='([^']*)'",
        rf'id="{re.escape(field_id)}"[^>]*value="([^"]*)"',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m and m.group(1).strip():
            return m.group(1).strip()
    return default


# ── 数据抓取 ──────────────────────────────────────────
# 会话保持：POST 导航依赖 GET 时下发的 PS_TOKENEXPIRE 等 cookie
SESSION = requests.Session()


def fetch_student_center(cookies: dict) -> str:
    """获取 Student Center 页面（psc content servlet），返回 HTML"""
    url = f"{PSC_BASE}/SA_LEARNER_SERVICES.SSS_STUDENT_CENTER.GBL"
    resp = _get_with_retry(url, cookies)
    if _is_auth_failure(resp.text):
        raise RuntimeError("SIS 返回未授权页面 — PS_TOKEN 已过期，请重新登录后更新 credentials/cookies.txt")
    return resp.text


def fetch_page_via_nav(cookies: dict, dropdown_value: str) -> str:
    """
    通过 Student Center 的下拉菜单导航到目标页面。
    1. GET Student Center → 提取 ICSID 与 ICStateNum
    2. POST 导航请求 → 跟随 302 重定向 → 获取目标页 HTML
    """
    # Step 1: 获取 ICSID 与 ICStateNum（隐藏字段随会话变化，必须动态提取）
    sc_html = fetch_student_center(cookies)
    m = re.search(r"ICSID'\s*id='ICSID'\s*value='([^']*)'", sc_html)
    if not m:
        raise RuntimeError("无法从 Student Center 提取 ICSID，cookie 可能已过期")
    icsid = m.group(1)
    m2 = re.search(
        r"name='ICStateNum'[^>]*id='ICStateNum'[^>]*value='([^']*)'", sc_html)
    icstate = m2.group(1) if m2 else "3"

    # Step 2: POST 导航
    post_data = {
        "ICType": "Panel",
        "ICElementNum": "0",
        "ICStateNum": icstate,
        "ICAction": "DERIVED_SSS_SCL_SSS_GO_1",
        "ICModelCancel": "0",
        "ICXPos": "0",
        "ICYPos": "0",
        "ResponsetoDiffFrame": "-1",
        "TargetFrameName": "None",
        "FacetPath": "None",
        "ICSID": icsid,
        "DERIVED_SSS_SCL_SSS_MORE_ACADEMICS": dropdown_value,
    }

    url = f"{PSC_BASE}/SA_LEARNER_SERVICES.SSS_STUDENT_CENTER.GBL"
    resp = _get_with_retry(url, cookies, data=post_data, allow_redirects=True)
    if _is_auth_failure(resp.text):
        raise RuntimeError("SIS 返回未授权页面 — PS_TOKEN 已过期，请重新登录后更新 credentials/cookies.txt")
    return resp.text


# ── 解析函数 ──────────────────────────────────────────

def parse_student_info(html: str) -> dict:
    """从任意 SIS 页面提取学生基本信息"""
    name_raw = ""
    for fid in ["DERIVED_SSTSNAV_PERSON_NAME", "DERIVED_SSTSKV_PERSON_NAME"]:
        name_raw = clean_html(extract_by_id(html, fid))
        if name_raw:
            break

    # 尝试分离中英文名
    name_en = ""
    name_zh = ""
    if "," in name_raw:
        parts = name_raw.split(",", 1)
        name_en = parts[0].strip()
        # 后半部分可能包含中文名
        rest = parts[1].strip() if len(parts) > 1 else ""
        zh_match = re.search(r"[一-鿿]{2,}", rest)
        name_zh = zh_match.group(0) if zh_match else rest

    # 提取系统隐藏信息
    hidden_info = {}
    m = re.search(r"db='([^']*)'\s*user='([^']*)'\s*component='([^']*)'", html)
    if m:
        hidden_info = {"database": m.group(1), "userid": m.group(2), "component": m.group(3)}

    return {
        "name_full": name_raw,
        "name_en": name_en,
        "name_zh": name_zh,
        "system_info": hidden_info,
    }


def parse_course_history(html: str) -> dict:
    """解析 Course History 页面，提取所有课程记录"""
    student = parse_student_info(html)

    courses = []
    for i in range(100):  # 最多 100 门课
        code = extract_by_id(html, f"CRSE_NAME${i}")
        if not code:
            break

        desc = extract_by_id(html, f"CRSE_DESCR${i}")
        grade = extract_by_id(html, f"CRSE_GRADE${i}")
        term = extract_by_id(html, f"CRSE_TERM${i}")
        units_str = extract_by_id(html, f"CRSE_UNITS${i}")

        try:
            units = float(units_str) if units_str else 0.0
        except ValueError:
            units = 0.0

        # 判断课程状态（Course History 网格只有 NAME/DESCR/GRADE/TERM/UNITS 五字段，
        # 无 CRSE_STATUS；在读课程表现为无成绩 + 有修读学期）
        if grade in ("T",):
            course_status = "transferred"
        elif grade in ("EX",):
            course_status = "exempted"
        elif grade in ("AU",):
            course_status = "audit"
        elif grade in ("I",):
            course_status = "incomplete"
        elif not grade and term:
            course_status = "in_progress"
        elif grade:
            course_status = "taken"
        else:
            course_status = "unknown"

        courses.append({
            "index": i,
            "code": code,
            "description": desc,
            "grade": grade,
            "term": term,
            "units": units,
            "status": course_status,
        })

    # 汇总统计
    taken_count = sum(1 for c in courses if c["status"] == "taken")
    in_progress_count = sum(1 for c in courses if c["status"] == "in_progress")
    transferred_count = sum(1 for c in courses if c["status"] == "transferred")
    total_units = sum(c["units"] for c in courses)

    return {
        "student": student,
        "total_courses": len(courses),
        "taken_count": taken_count,
        "in_progress_count": in_progress_count,
        "transferred_count": transferred_count,
        "total_units": total_units,
        "courses": courses,
    }


def _extract_course_rows(section: str) -> list:
    """从 AR 需求组 section 提取逐课行：代码/名称/学分/学期/成绩/状态。

    PeopleSoft 网格字段以 $N 索引关联：
      CRSE_NAME$span$N / CRSE_DESCR$N / CRSE_UNITS$N / CRSE_WHEN$N
      / SAA_ACRSE_AVLVW_CRSE_GRADE_OFF$N
    有成绩或修读学期 → 已修（taken），否则未修（not_taken）。
    """
    rows = {}
    pat = re.compile(
        r"id='(CRSE_NAME|CRSE_DESCR|CRSE_UNITS|CRSE_WHEN"
        r"|SAA_ACRSE_AVLVW_CRSE_GRADE_OFF)\$(?:span\$)?(\d+)'[^>]*>"
        r"(?:<[^>]*>)*([^<]*)<"
    )
    for fid, n, val in pat.findall(section):
        v = clean_html(val).strip()
        rows.setdefault(int(n), {})[fid] = v

    out = []
    for n in sorted(rows):
        r = rows[n]
        name = r.get("CRSE_NAME", "").strip()
        if not name:
            continue
        grade = r.get("SAA_ACRSE_AVLVW_CRSE_GRADE_OFF", "")
        term = r.get("CRSE_WHEN", "")
        # 注意：CRSE_WHEN 对未修课显示的是"开课学期"（如 Fall, Spring），不可靠；
        # 只有成绩字段才是"已修"的可靠信号（未修行为 &nbsp;）。
        status = "taken" if grade else "not_taken"
        try:
            units = float(r.get("CRSE_UNITS") or 0)
        except ValueError:
            units = 0.0
        out.append({
            "index": n,
            "code": re.sub(r"\s+", " ", name).upper(),
            "description": r.get("CRSE_DESCR", "").strip(),
            "units": units,
            "term": term,
            "grade": grade,
            "status": status,
        })
    return out


# 需求状态标签（WEBSITE_STRUCTURE.md §5.2：<span class='PSLONGEDITBOX'><strong>Not Satisfied: ...</strong>）
RE_NS_ITEM = re.compile(
    r"class=([\"']?)PSLONGEDITBOX\1>\s*<strong[^>]*>"
    r"(Not Satisfied|Satisfied|In Progress):\s*(?:&nbsp;)*</strong>(.*?)</span>",
    re.DOTALL | re.IGNORECASE,
)
RE_STATUS_LABEL = re.compile(
    r"<strong[^>]*>\s*(Not Satisfied|Satisfied|In Progress)\s*[:<]",
    re.IGNORECASE,
)


def _count_statuses(html: str) -> dict:
    """统计段内/全页各状态标签出现次数（匹配 <strong>Status:</strong> 渲染）"""
    counts = {"satisfied": 0, "not_satisfied": 0, "in_progress": 0}
    for status in RE_STATUS_LABEL.findall(html):
        key = status.lower().replace(" ", "_")
        if key in counts:
            counts[key] += 1
    return counts


def parse_academic_requirements(html: str) -> dict:
    """解析 Academic Requirements 页面，提取毕业要求进度"""
    student = parse_student_info(html)

    # 提取需求分类 (PAGROUPDIVIDER)，按文档顺序切分 section
    dividers = [
        (m.start(), unescape(m.group(1).strip()))
        for m in re.finditer(r"<td class='PAGROUPDIVIDER'[^>]*>\s*(.*?)\s*</td>", html)
    ]

    # 提取所有需求状态项
    ns_items = [
        (status, desc_raw)
        for status, _, desc_raw in RE_NS_ITEM.findall(html)
    ]

    requirements = []
    for i, (status, desc_raw) in enumerate(ns_items):
        desc = clean_html(desc_raw)
        if len(desc) < 3:
            continue
        requirements.append({
            "index": i,
            "status": status.lower().replace(" ", "_"),
            "description": desc[:500],
        })

    # 需求组分类（按 divider 文档顺序切分 section，提取逐课明细）
    groups = []
    for i, (pos, div_clean) in enumerate(dividers):
        if not div_clean:
            continue
        end = dividers[i + 1][0] if i + 1 < len(dividers) else len(html)
        section_html = html[pos:end]

        # 统计该 section 中的状态（匹配 <strong>Status:</strong> 渲染）
        st = _count_statuses(section_html)
        satisfied = st["satisfied"]
        not_satisfied = st["not_satisfied"]
        in_progress = st["in_progress"]

        # 逐课明细（含已修/未修状态）
        courses = _extract_course_rows(section_html)
        course_codes = sorted({c["code"] for c in courses})

        # 提取学分要求
        credits = list(set(re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*(?:credit|Credit|unit|Unit)', section_html)))

        # 判定状态
        if not_satisfied == 0 and satisfied > 0:
            overall_status = "satisfied"
        elif not_satisfied > 0 and satisfied > 0:
            overall_status = "partially_satisfied"
        elif not_satisfied > 0:
            overall_status = "not_satisfied"
        else:
            overall_status = "unknown"

        groups.append({
            "name": div_clean,
            "overall_status": overall_status,
            "satisfied_count": satisfied,
            "not_satisfied_count": not_satisfied,
            "in_progress_count": in_progress,
            "related_courses": course_codes,
            "credits_mentioned": credits,
            "courses": courses,
        })

    # 总体状态
    total = _count_statuses(html)
    total_satisfied = total["satisfied"]
    total_not_satisfied = total["not_satisfied"]
    total_in_progress = total["in_progress"]

    return {
        "student": student,
        "requirement_groups": groups,
        "requirement_items": requirements,
        "summary": {
            "total_requirement_groups": len(groups),
            "total_satisfied_markers": total_satisfied,
            "total_not_satisfied_markers": total_not_satisfied,
            "total_in_progress_markers": total_in_progress,
        },
    }


# ── 文件加载器（统一走 scripts/credentials.py，2026-08 收敛三处重复实现）──

def load_cookies_from_file(path: str) -> dict:
    """从 cookie 文件加载 cookie 字典（统一实现，兼容 UTF-8 BOM）"""
    from credentials import load_cookies
    return load_cookies(Path(path))


# ── 入学年份推断 ──────────────────────────────────────────

def parse_transcript(html: str) -> dict:
    """解析 Transcript 页面：CGA、最早 term、状态。

    PeopleSoft transcript 常见标记（不同渲染形态尽量兼容）：
      - CGA: 'Overall GPA' / 'Cumulative GPA' / 'CGA'
      - 每学期课程网格字段 STDNT_TERM$N / CRSE_NAME$N
    返回: {cga, has_cga, earliest_term, terms[], note}
    """
    cga = ""
    for pat in (r"Cumulative GPA[^\d]*([\d.]+)", r"Overall GPA[^\d]*([\d.]+)",
                r"CGA[^\d]*([\d.]+)"):
        m = re.search(pat, html)
        if m:
            cga = m.group(1)
            break

    terms = []
    for m in re.finditer(r"(\d{4}-\d{2})\s+(Fall|Spring|Summer|Winter)", html):
        terms.append(f"{m.group(1)} {m.group(2)}")
    terms = list(dict.fromkeys(terms))  # 去重保序

    note = ""
    if not cga and not terms:
        note = "Transcript 页无 CGA 与学期数据（可能为空壳/登录态异常）"
    elif not cga:
        note = "无 CGA 记录（大一新生特征：入学年份=当年）"
    return {
        "cga": float(cga) if cga else None,
        "has_cga": bool(cga),
        "earliest_term": terms[0] if terms else "",
        "terms": terms,
        "note": note,
    }


# ── Pre-Enroll（HKUST 定制 Enrollment Summary 页）─────────────────────

# 页面：SA_LEARNER_SERVICES.ZR_SSENRL_SUM_CMP.GBL?Page=ZR_SSENRL_SUM_PG
#   Confirmed Enrollment 网格前缀 ZR_ENRL_SUMC_VW（学校已确认预选/已注册）
#   Pending Enrollment 网格前缀 ZR_ENRL_SUMP_VW（待定/预选）
#   字段：ZR_CRSE_CODE / COURSE_TITLE_LONG / UNT_TAKEN / SECTION_NAME（$N 行索引）
#   注意：PeopleSoft term 由会话决定，URL STRM 参数仅触发渲染（不切学期）；
#   本页抓取的是 SIS 当前默认学期（选课季即目标学期）的预选课。
ZR_GRID_FIELDS = ["ZR_CRSE_CODE", "COURSE_TITLE_LONG", "UNT_TAKEN", "SECTION_NAME"]


def fetch_pre_enroll(cookies: dict, session_code: str) -> str:
    url = (f"{PSC_BASE}/SA_LEARNER_SERVICES.ZR_SSENRL_SUM_CMP.GBL"
           f"?Page=ZR_SSENRL_SUM_PG&Action=A&ACAD_CAREER=UGRD"
           f"&ENRL_REQUEST_ID=&INSTITUTION=HKUST&STRM={session_code}")
    resp = _get_with_retry(url, cookies)
    if _is_auth_failure(resp.text):
        raise RuntimeError("SIS 返回未授权页面 — PS_TOKEN 已过期，请重新登录后更新 credentials/cookies.txt")
    return resp.text


def parse_pre_enroll(html: str) -> dict:
    """解析 Enrollment Summary 页 → 预选/已注册课程 + 学分汇总。

    - confirmed[]：Confirmed Enrollment（学校预选/已注册，含 Remarks 列）
    - pending[]：Pending Enrollment（待定：Pending Add / Pending Drop）
    - term / total_unit_load / note
    """
    def grid(prefix: str) -> list:
        rows = {}
        pat = re.compile(
            rf"id='{re.escape(prefix)}_(ZR_CRSE_CODE|COURSE_TITLE_LONG|UNT_TAKEN|SECTION_NAME)"
            rf"\$(\d+)'[^>]*>(?:<[^>]*>)*([^<]*)<"
        )
        for fld, n, val in pat.findall(html):
            v = clean_html(val).strip()
            if v:
                rows.setdefault(int(n), {})[fld] = v
        out = []
        for n in sorted(rows):
            r = rows[n]
            code = re.sub(r"\s+", "", r.get("ZR_CRSE_CODE", "")).upper()
            if not code or len(code) < 4:
                continue
            try:
                units = float(r.get("UNT_TAKEN") or 0)
            except ValueError:
                units = 0.0
            out.append({
                "code": f"{code[:4]} {code[4:]}" if len(code) > 4 else code,
                "title": r.get("COURSE_TITLE_LONG", ""),
                "units": units,
                "section": r.get("SECTION_NAME", ""),
            })
        return out

    text = clean_html(html)
    term_m = re.search(r"(\d{4}-\d{2} (?:Fall|Spring|Summer|Winter))", text)
    load_m = re.search(
        r"Total Unit Load:\s*([\d.]+)\s*\(Confirmed:\s*([\d.]+)"
        r"\s*Pending Add:\s*([\d.]+)\s*Pending Drop:\s*([\d.]+)\)", text)

    confirmed, pending = grid("ZR_ENRL_SUMC_VW"), grid("ZR_ENRL_SUMP_VW")
    return {
        "term": term_m.group(1) if term_m else "",
        "confirmed": confirmed,
        "pending": pending,
        "total_unit_load": {
            "total": float(load_m.group(1)) if load_m else None,
            "confirmed": float(load_m.group(2)) if load_m else None,
            "pending_add": float(load_m.group(3)) if load_m else None,
            "pending_drop": float(load_m.group(4)) if load_m else None,
        },
        "note": ("Enrollment Summary 为 SIS 当前默认学期（选课季通常即目标学期）；"
                 "URL STRM 参数不切换学期（PeopleSoft 会话 term）"),
    }


def infer_admission_year(course_history: dict) -> str:
    """从课程历史最早修读学期推断入学年份（Transcript 不可用时的次选）。

    规则（固定，见 skills/phase2-profile/SKILL.md）:
      - 取所有 taken/in_progress/transferred 课程的最早 term（如 2023-24 Fall）→ 入学年份 = 2023-24
      - 无任何课程记录 → 返回 ""（无法推断，需用户提供）
    """
    terms = []
    for c in course_history.get("courses", []):
        m = TERM_RE.match(c.get("term", ""))
        if m and c.get("status") in ("taken", "in_progress", "transferred"):
            terms.append(f"{m.group(1)}-{m.group(2)}")
    return sorted(terms)[0] if terms else ""


def infer_year_of_study(admission_year: str, target_term: str = "") -> int:
    """入学年份 + 目标学期（如 2026-27 Fall）→ 年级（Year N）。

    规则：学年差 + 1；Fall 起算，规划学期早于入学年的 Fall 按 1。
    """
    m = TERM_RE.match(target_term or "")
    if not m:
        return 0
    try:
        adm = int(admission_year.split("-")[0])
    except (ValueError, AttributeError):
        return 0
    year = int(m.group(1))
    return max(1, year - adm + 1)


# ── Grades 逐学期补充（web-crawl-guide §2b 降级路径）─────────

GRADE_TOKEN_RE = re.compile(r">\s*([A-D][+-]?|F|P{1,2}|T|AU|EX|I|N)\s*<", re.IGNORECASE)


def fetch_grades(cookies: dict, raw_dir: Path) -> str:
    """抓取 Grades 页（value=1030）→ 保存 cache/sis/raw_grades.html，返回 HTML"""
    html = fetch_page_via_nav(cookies, DROPDOWN_VALUES["grades"])
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "raw_grades.html").write_text(html, encoding="utf-8")
    return html


def _parse_grades_from_rows(html: str) -> list:
    """从表格行提取 (code, grade)：每行取全部课程代码与首个成绩 token。best-effort"""
    out, seen = [], set()
    for row in re.split(r"<tr", html)[1:]:
        codes = re.findall(r"([A-Z]{3,4})\s*(\d{4}[A-Z]?)", clean_html(row))
        g = GRADE_TOKEN_RE.findall(row)
        if not codes or not g:
            continue
        for a, b in codes:
            code = f"{a} {b}"
            if code not in seen:
                seen.add(code)
                out.append({"code": code, "grade": g[0].upper()})
    return out


def parse_grades(html: str) -> dict:
    """解析 Grades 页：按学期标签切分，逐学期提取 (code, grade)。

    best-effort：PeopleSoft 字段结构未固化，缺失时以 Transcript/Course History 为准。
    """
    positions = [(m.start(), m.group(0).strip()) for m in TERM_RE.finditer(html)]
    if positions:
        chunks = []
        for i, (pos, label) in enumerate(positions):
            end = positions[i + 1][0] if i + 1 < len(positions) else len(html)
            chunks.append((label, html[pos:end]))
    else:
        chunks = [("", html)]
    per_term = []
    for label, chunk in chunks:
        rows = _parse_grades_from_rows(chunk)
        per_term.append({"term": label, "course_count": len(rows), "courses": rows})
    return {
        "terms": [label for label, _ in chunks if label],
        "per_term": per_term,
        "note": "best-effort：Grades 页字段结构未固化，缺失时以 Transcript/Course History 为准",
    }


# ── 主程序 ────────────────────────────────────────────

PE_FIXTURE = """
<span class='SSSPAGEKEYTEXT' id='DERIVED_REGFRM1_SSR_STDNTKEY_DESCR$5$' >2026-27 Fall | Undergraduate | HKUST</span>
<div id='win0divZR_ENRL_SUMC_VW_ZR_CRSE_CODE$0'><span id='ZR_ENRL_SUMC_VW_ZR_CRSE_CODE$0'>COMP2011</span></div>
<div id='win0divZR_ENRL_SUMC_VW_COURSE_TITLE_LONG$0'><span id='ZR_ENRL_SUMC_VW_COURSE_TITLE_LONG$0'>Programming with C++</span></div>
<div id='win0divZR_ENRL_SUMC_VW_UNT_TAKEN$0'><span id='ZR_ENRL_SUMC_VW_UNT_TAKEN$0'>4.0</span></div>
<div id='win0divZR_ENRL_SUMC_VW_SECTION_NAME$0'><span id='ZR_ENRL_SUMC_VW_SECTION_NAME$0'>L1</span></div>
<div id='win0divZR_ENRL_SUMP_VW_ZR_CRSE_CODE$0'><span id='ZR_ENRL_SUMP_VW_ZR_CRSE_CODE$0'>MATH2011</span></div>
<div id='win0divZR_ENRL_SUMP_VW_UNT_TAKEN$0'><span id='ZR_ENRL_SUMP_VW_UNT_TAKEN$0'>3.0</span></div>
<div id='win0divZR_ENRL_SUMP_VW_SECTION_NAME$0'><span id='ZR_ENRL_SUMP_VW_SECTION_NAME$0'>L2</span></div>
<span>Total Unit Load: 7.0 (Confirmed: 4.0 Pending Add: 3.0 Pending Drop: 0)</span>
"""


def selftest() -> int:
    """解析器自测：pre-enroll 网格解析（合成 fixture，不含真实数据）"""
    ok = True

    def check(name: str, cond: bool):
        nonlocal ok
        print(f"  [{'OK' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    pe = parse_pre_enroll(PE_FIXTURE)
    check("term 提取", pe["term"] == "2026-27 Fall")
    check("confirmed 1 门", len(pe["confirmed"]) == 1
          and pe["confirmed"][0]["code"] == "COMP 2011"
          and pe["confirmed"][0]["units"] == 4.0
          and pe["confirmed"][0]["section"] == "L1")
    check("pending 1 门", len(pe["pending"]) == 1
          and pe["pending"][0]["code"] == "MATH 2011"
          and pe["pending"][0]["units"] == 3.0)
    check("unit load 汇总", pe["total_unit_load"]["total"] == 7.0
          and pe["total_unit_load"]["confirmed"] == 4.0)
    check("空页（无课程）", parse_pre_enroll("<span>empty</span>")["confirmed"] == [])

    ch = parse_course_history(
        "<div id='win0divCRSE_NAME$0'><span id='CRSE_NAME$0'>CHEM 1011</span></div>"
        "<div id='win0divCRSE_GRADE$0'><span id='CRSE_GRADE$0'>A</span></div>"
        "<div id='win0divCRSE_TERM$0'><span id='CRSE_TERM$0'>2024-25 Fall</span></div>"
        "<div id='win0divCRSE_UNITS$0'><span id='CRSE_UNITS$0'>3.000</span></div>")
    check("course history 解析", len(ch["courses"]) == 1
          and ch["courses"][0]["code"] == "CHEM 1011"
          and ch["courses"][0]["status"] == "taken")
    return 0 if ok else 1


def main():
    # Windows 控制台默认 GBK，强制 UTF-8 输出避免 emoji 打印崩溃
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="HKUST SIS 数据解析器 — 解析 PeopleSoft 课程历史与学术要求"
    )
    parser.add_argument("--fetch", action="store_true",
                        help="重新从 SIS 抓取数据（需要 cookie）")
    parser.add_argument("--fetch-grades", action="store_true",
                        help="只抓取 Grades 页（value=1030，Transcript 不全时的补充路径）")
    parser.add_argument("--session", type=str, default="",
                        help="目标学期代码（如 2610；SIS term code 与 wcq 一致，"
                             "用于 pre-enroll 页 STRM 参数——空 STRM 页面不渲染，"
                             "--fetch 时自动从 wcq 探测最近学期）")
    parser.add_argument("--cookie-file", type=str,
                        default=str(ROOT / "credentials" / "cookies.txt"),
                        help="Cookie 文件路径 (默认: credentials/cookies.txt)")
    parser.add_argument("--selftest", action="store_true", help="解析器自测")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(selftest())

    raw_dir = Path(DEFAULT_DIR)
    OUTPUT_PATH = Path(DEFAULT_DIR)
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

    # ── 获取数据 ──
    if args.fetch or args.fetch_grades:
        # 加载 cookie
        cookie_path = Path(args.cookie_file)
        if not cookie_path.exists():
            print(f"错误：Cookie 文件不存在: {cookie_path}")
            print("请运行 `python3 scripts/cookies_setup.py` 交互式获取/写入，")
            print("或用 `--print-bookmarklet` 获取登录页一键复制书签。")
            sys.exit(1)
        cookies = load_cookies_from_file(args.cookie_file)

        if not cookies.get("PS_TOKEN"):
            print("错误：需要 PS_TOKEN（CAS 登录后的 PeopleSoft 认证令牌）")
            sys.exit(1)

        if args.fetch_grades:
            print("抓取 Grades (value=1030)...")
            raw_dir.mkdir(parents=True, exist_ok=True)
            g_html = fetch_grades(cookies, raw_dir)
            print(f"  已保存: {raw_dir / 'raw_grades.html'}（{len(g_html)} 字节）")
            if not args.fetch:
                print("Grades 页抓取完成（仅 --fetch-grades）。")
        if args.fetch:
            # session 为空时自动探测最近学期（Pre-Enroll 页 STRM 必须有效，
            # 空 STRM 返回 JS 空壳无数据——2026-08 实测；SIS term code 与 wcq 一致）
            if not args.session:
                try:
                    from wcq.crawler import latest_session
                    sess = latest_session()
                    if sess:
                        args.session = sess
                        print(f"自动探测最近学期: {args.session}（--session 未指定）")
                except Exception:
                    print("提示: 未指定 --session 且 wcq 探测失败，"
                          "Pre-Enroll 页可能无法渲染（可显式传 --session）")
            sc_html = fetch_student_center(cookies)
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / "raw_student_center.html").write_text(sc_html, encoding="utf-8")
            print(f"  已保存: {raw_dir / 'raw_student_center.html'}")

            # Pre-Enroll（HKUST 定制 Enrollment Summary：学校预选课）
            print(f"抓取 Pre-Enroll / Enrollment Summary (session {args.session})...")
            try:
                pe_html = fetch_pre_enroll(cookies, args.session)
                (raw_dir / "raw_pre_enroll.html").write_text(pe_html, encoding="utf-8")
                print(f"  已保存: {raw_dir / 'raw_pre_enroll.html'}")
            except RuntimeError as e:
                print(f"  [WARN] pre-enroll 抓取失败: {e}")

            # Course History
            print("抓取 Course History (value=2050)...")
            ch_html = fetch_page_via_nav(cookies, DROPDOWN_VALUES["course_history"])
            (raw_dir / "raw_course_history.html").write_text(ch_html, encoding="utf-8")
            print(f"  已保存: {raw_dir / 'raw_course_history.html'}")

            # Academic Requirements
            print("抓取 Academic Requirements (value=3010)...")
            ar_html = fetch_page_via_nav(cookies, DROPDOWN_VALUES["academic_requirements"])
            (raw_dir / "raw_academic_requirements.html").write_text(ar_html, encoding="utf-8")
            print(f"  已保存: {raw_dir / 'raw_academic_requirements.html'}")

            # Transcript（入学年份/CGA 权威来源）
            print("抓取 Transcript (value=2035)...")
            tr_html = fetch_page_via_nav(cookies, DROPDOWN_VALUES["transcript"])
            (raw_dir / "raw_transcript.html").write_text(tr_html, encoding="utf-8")
            print(f"  已保存: {raw_dir / 'raw_transcript.html'}")

    # ── 解析数据 ──
    print("\n解析数据...")

    # Student Info
    sc_path = raw_dir / "raw_student_center.html"
    if sc_path.exists():
        sc_html = sc_path.read_text(encoding="utf-8")
        student = parse_student_info(sc_html)
        with open(OUTPUT_PATH / "sis_student_info.json", "w", encoding="utf-8") as f:
            json.dump(student, f, ensure_ascii=False, indent=2)
        print(f"  ✅ 学生信息: {student['name_full']}")
        print(f"  📄 已保存: {OUTPUT_PATH / 'sis_student_info.json'}")
    else:
        print(f"  ⚠️  未找到: {sc_path}")

    # Course History
    ch_path = raw_dir / "raw_course_history.html"
    if ch_path.exists() and ch_path.stat().st_size > 10000:
        ch_html = ch_path.read_text(encoding="utf-8")
        ch_data = parse_course_history(ch_html)
        with open(OUTPUT_PATH / "sis_course_history.json", "w", encoding="utf-8") as f:
            json.dump(ch_data, f, ensure_ascii=False, indent=2)
        print(f"  ✅ 课程历史: {ch_data['total_courses']} 门课, "
              f"共 {ch_data['total_units']} 学分")
        print(f"     - 已修: {ch_data['taken_count']}")
        print(f"     - 在读: {ch_data['in_progress_count']}")
        print(f"     - 转学分: {ch_data['transferred_count']}")
        adm = infer_admission_year(ch_data)
        if adm:
            print(f"     - 推断入学年份: {adm}")
        print(f"  📄 已保存: {OUTPUT_PATH / 'sis_course_history.json'}")
    else:
        print(f"  ⚠️  未找到或文件太小: {ch_path}")

    # Academic Requirements
    ar_path = raw_dir / "raw_academic_requirements.html"
    if ar_path.exists() and ar_path.stat().st_size > 50000:
        ar_html = ar_path.read_text(encoding="utf-8")
        ar_data = parse_academic_requirements(ar_html)
        with open(OUTPUT_PATH / "sis_academic_req.json", "w", encoding="utf-8") as f:
            json.dump(ar_data, f, ensure_ascii=False, indent=2)
        s = ar_data["summary"]
        print(f"  ✅ 学术要求: {s['total_requirement_groups']} 个需求组")
        for g in ar_data["requirement_groups"]:
            icon = "✅" if g["overall_status"] == "satisfied" else "⚠️"
            print(f"     [{icon}] {g['name']}")
        print(f"  📄 已保存: {OUTPUT_PATH / 'sis_academic_req.json'}")
    else:
        print(f"  ⚠️  未找到或文件太小: {ar_path}")

    # Transcript（入学年份/CGA 权威来源）
    tr_path = raw_dir / "raw_transcript.html"
    if tr_path.exists() and tr_path.stat().st_size > 10000:
        tr_html = tr_path.read_text(encoding="utf-8")
        tr_data = parse_transcript(tr_html)
        with open(OUTPUT_PATH / "sis_transcript.json", "w", encoding="utf-8") as f:
            json.dump(tr_data, f, ensure_ascii=False, indent=2)
        if tr_data["has_cga"]:
            print(f"  ✅ Transcript: CGA={tr_data['cga']}，最早 term={tr_data['earliest_term']}")
        else:
            print(f"  ⚠️  Transcript: 无 CGA 记录（新生特征），最早 term={tr_data['earliest_term'] or '无'}")
        if tr_data["note"]:
            print(f"     {tr_data['note']}")
        print(f"  📄 已保存: {OUTPUT_PATH / 'sis_transcript.json'}")
    else:
        print(f"  ⚠️  未找到或文件太小: {tr_path}")

    # Pre-Enroll（学校预选课，HKUST 定制 Enrollment Summary 页）
    pe_path = raw_dir / "raw_pre_enroll.html"
    if pe_path.exists() and pe_path.stat().st_size > 10000:
        pe_data = parse_pre_enroll(pe_path.read_text(encoding="utf-8"))
        with open(OUTPUT_PATH / "sis_pre_enroll.json", "w", encoding="utf-8") as f:
            json.dump(pe_data, f, ensure_ascii=False, indent=2)
        # 同步写 data/pre_enrolled.json（step1/step5/step6 直接消费的运行期产物，
        # 与 cache 版同构同 schema；预选课视为已确定：不重复推荐、评分按
        # pre_enroll_boost 加权、占用时段）
        data_dir = ROOT / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        with open(data_dir / "pre_enrolled.json", "w", encoding="utf-8") as f:
            json.dump(pe_data, f, ensure_ascii=False, indent=2)
        total = pe_data["total_unit_load"]
        print(f"  ✅ Pre-Enroll（{pe_data['term'] or '?'}）: "
              f"confirmed {len(pe_data['confirmed'])} 门 / "
              f"pending {len(pe_data['pending'])} 门, "
              f"unit load {total['total']}")
        for c in pe_data["confirmed"] + pe_data["pending"]:
            print(f"     - {c['code']:12} [{c['section']:5}] {c['title'][:40]}")
        print(f"  📄 已保存: {OUTPUT_PATH / 'sis_pre_enroll.json'}")
        print(f"  📄 已保存: {data_dir / 'pre_enrolled.json'}")
    else:
        print(f"  ⚠️  未找到或文件太小: {pe_path}")

    # Grades（Transcript 不全时的补充来源）
    g_path = raw_dir / "raw_grades.html"
    if g_path.exists() and g_path.stat().st_size > 10000:
        g_data = parse_grades(g_path.read_text(encoding="utf-8"))
        with open(OUTPUT_PATH / "sis_grades.json", "w", encoding="utf-8") as f:
            json.dump(g_data, f, ensure_ascii=False, indent=2)
        print(f"  ✅ Grades: {len(g_data['per_term'])} 个学期段"
              + (f"（{', '.join(g_data['terms'])}）" if g_data["terms"] else ""))
        print(f"  📄 已保存: {OUTPUT_PATH / 'sis_grades.json'}")
    else:
        print(f"  ⚠️  未找到或文件太小: {g_path}")

    print(f"\n✅ 解析完成！JSON 文件保存在 {OUTPUT_PATH}/")


if __name__ == "__main__":
    main()
