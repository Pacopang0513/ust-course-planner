#!/usr/bin/env python3
"""
WCQ Class Schedule 爬虫 — scripts/wcq/crawler.py（async 并发）
================================================================
抓取 w5.ab.ust.hk/wcq 公开 Class Schedule & Quota 页面（无需 cookie），
产出 data/courses_{session}.json（含 section 时间/教室/导师/Quota/Enrol
及课程级 pre-requisite / exclusion / 属性），供：
  - Step 3 过滤（今年是否开设 / pre-reg 检查）
  - Step 4 导师配对（instructor 与 USTspace 评论对照）
  - Step 6 时间冲突检测（wcq/conflict.py 消费同一文件）

流程（固化，见 skills/web-crawl-guide/SKILL.md）:
  1. GET https://w5.ab.ust.hk/wcq/cgi-bin/{session}/ → 提取全部 subject 链接
  2. 并发 GET /wcq/cgi-bin/{session}/subject/{SUBJ} → cache/wcq/raw/{session}/{SUBJ}.html
  3. 解析每页 div.course 块：课程信息 + table.sections 行
  4. 合并多时段 section（mainRow + 后续 otherRow）→ data/courses_{session}.json
  5. （可选）Common Core：索引页下拉按入学年份组（4Y/CC22/CC25/CC26）抓区域页
     → data/cc_courses_{session}.json（该组今年开设的全部 CC 课程）

用法:
  python3 scripts/wcq/crawler.py --session 2610
  python3 scripts/wcq/crawler.py --session 2610 --subject COMP   # 单 subject
  python3 scripts/wcq/crawler.py --session 2610 --force          # 强制重抓
  python3 scripts/wcq/crawler.py --session 2610 --list-only      # 只列 subject
  python3 scripts/wcq/crawler.py --admission-year 2026-27        # Common Core 课程池
  python3 scripts/wcq/crawler.py --cc-group CC26                 # 显式指定 CC 组
  python3 scripts/wcq/crawler.py --selftest                      # 解析器自测
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://w5.ab.ust.hk"
ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "cache" / "wcq" / "raw"
DATA_DIR = ROOT / "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (course-arranger build script)"}

RE_SEMESTER = re.compile(r"(\d{4}-\d{2})\s+(Fall|Spring|Winter|Summer)")
RE_SUBJECT = re.compile(r'href="/wcq/cgi-bin/([0-9]+)/subject/([A-Z0-9]+)"')
RE_ANCHOR = re.compile(r'<a name="([A-Z0-9]+)">')
RE_SUBJECT_LINE = re.compile(r"<div class='subject'>(.*?)</div>", re.S)
RE_ATTR_ROW = re.compile(r"<tr><th[^>]*>([^<]*)</th><td[^>]*>(.*?)</td></tr>", re.S)
RE_HEADER_ROW = re.compile(r'<tr class="tableHeader"[^>]*>(.*?)</tr>', re.S)
RE_HEADER_CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S)
RE_MAIN_ROW = re.compile(
    r'<tr class="(?:newsect|sect)\w*\s+(?:sect\w+ )?mainRow">(.*?)</tr>', re.S)
RE_OTHER_ROW = re.compile(r'<tr class="\w*\s*otherRow">(.*?)</tr>', re.S)
RE_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
RE_SECTION_ID = re.compile(r"^([A-Z][0-9]+)\s*\((\d+)\)$")
RE_INSTRUCTOR = re.compile(r"<a href=\"[^\"]*instructor/[^\"]*\">([^<]+)</a>")
RE_QUOTA = re.compile(r"<td class=\"quota\"[^>]*>\s*<span>(\d+)</span>")
RE_NUM = re.compile(r"(\d+)")


def _header_map(block: str) -> dict:
    """sections 表头行 → {列名(小写): 列索引}；找不到返回空（调用方用默认列号）"""
    m = RE_HEADER_ROW.search(block)
    if not m:
        return {}
    cols = [_strip(c).lower() for c in RE_HEADER_CELL.findall(m.group(1)) if _strip(c)]
    return {c: i for i, c in enumerate(cols)}


def _get(url: str) -> tuple:
    """→ (html, fail_reason)；成功时 fail_reason=''。失败原因分类供用户排查
    （cookie 无关，WCQ 公开页；常见：timeout=繁忙/网络、HTTP xxx=服务异常）"""
    last_reason = ""
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                return r.text, ""
            last_reason = f"HTTP {r.status_code}"
        except requests.Timeout:
            last_reason = "timeout（服务器繁忙/网络慢，已重试）"
        except requests.ConnectionError:
            last_reason = "connection_error（网络不通，已重试）"
        except requests.RequestException as e:
            last_reason = f"request_error: {type(e).__name__}"
    return "", last_reason


def _strip(html: str) -> str:
    html = re.sub(r"<[^>]+>", " ", html)
    html = html.replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", html).strip()


def _to_int(s: str):
    m = RE_NUM.search(_strip(s))
    return int(m.group(1)) if m else None


# ── 解析（纯函数）───────────────────────────────────────────
def _parse_course_block(block: str, subj: str = "") -> dict:
    """单个 div.course 块 → 课程 dict；subj 非空时按课号前缀过滤"""
    m = RE_ANCHOR.search(block)
    if not m:
        return None
    anchor = m.group(1)
    if subj and not anchor.upper().startswith(subj):
        return None
    sm = RE_SUBJECT_LINE.search(block)
    title, units = "", None
    if sm:
        line = _strip(sm.group(1))
        if " - " in line:
            rest = line.split(" - ", 1)[1]
            um = re.search(r"\((?:\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*:\s*)?(\d+(?:\.\d+)?)\s+units?\)\s*$", rest)
            if um:
                units = float(um.group(1))
                title = rest[:um.start()].strip()
            else:
                title = rest.strip()
    attrs = {}
    for th, td in RE_ATTR_ROW.findall(block):
        key = _strip(th).replace("\n", " ").strip()
        if key:
            attrs[key] = _strip(td)
    return {
        "code": anchor[:4], "number": anchor[4:] if len(anchor) > 4 else "",
        "title": title, "units": units, "attributes": attrs,
        "sections": _parse_sections(block),
    }


def parse_subject_page(html: str, session: str, subj: str) -> dict:
    """单 subject 页 → courses 列表（每课含信息 + sections）"""
    courses = []
    for block in re.split(r'<div class="course">', html)[1:]:
        c = _parse_course_block(block, subj)
        if c is not None:
            courses.append(c)
    return {"subject": subj, "session": session, "courses": courses}


def parse_cc_options(html: str, session: str) -> list:
    """索引页 CC 下拉 → [{group, group_label, areas: [{code, label}]}]
    组链接路径单段（common_core/CC26），区域链接两段（common_core/CC26/47）。"""
    groups, cur = [], None
    for m in re.finditer(
        r'<a href="(/wcq/cgi-bin/[\d]+/common_core/([^"]+))">([^<]*)</a>', html
    ):
        url, path, label = m.group(1), m.group(2), m.group(3).strip()
        parts = path.split("/")
        if len(parts) == 1:  # 组（单段）
            cur = {"group": parts[0], "group_label": label, "url": url, "areas": []}
            groups.append(cur)
        elif len(parts) == 2 and cur is not None:  # 区域（两段）
            cur["areas"].append({"code": parts[1], "label": label})
    return groups


def parse_cc_page(html: str, area_label: str) -> list:
    """CC 区域页 → courses 列表（跨 subject，全部课程）"""
    courses = []
    for block in re.split(r'<div class="course">', html)[1:]:
        c = _parse_course_block(block)
        if c is not None:
            courses.append(c)
    return courses


def _parse_sections(block: str) -> list:
    """table.sections → [{section, datetime, room, instructors, quota, ...}]（合并 otherRow）"""
    hm = _header_map(block)
    i_sec, i_time, i_room, i_instr = 0, 1, 2, 3
    i_quota = hm.get("quota", 5)
    i_enrol = hm.get("enrol", 6)
    i_avail = hm.get("avail", 7)
    i_wait = hm.get("wait", 8)

    sections, main_pos = [], []
    for m in RE_MAIN_ROW.finditer(block):
        tds = RE_TD.findall(m.group(1))
        if not tds:
            continue
        sec = _strip(tds[i_sec]) if len(tds) > i_sec else ""
        sm = RE_SECTION_ID.match(sec)
        name = sm.group(1) if sm else sec
        cur = {
            "section": name, "section_id": sm.group(2) if sm else "",
            "times": [_strip(tds[i_time]) if len(tds) > i_time else ""],
            "room": _strip(tds[i_room]) if len(tds) > i_room else "",
            "instructors": RE_INSTRUCTOR.findall(tds[i_instr]) if len(tds) > i_instr else [],
            "quota": _to_int(tds[i_quota]) if len(tds) > i_quota else None,
            "enrol": _to_int(tds[i_enrol]) if len(tds) > i_enrol else None,
            "avail": _to_int(tds[i_avail]) if len(tds) > i_avail else None,
            "wait": _to_int(tds[i_wait]) if len(tds) > i_wait else None,
            "remarks": [],
        }
        sections.append(cur)
        main_pos.append((m.start(), cur))
    # otherRow：归属其前最近的 mainRow（按文档顺序），不并入最后一个 section
    for m in RE_OTHER_ROW.finditer(block):
        owner = None
        for pos, sec in main_pos:
            if pos < m.start():
                owner = sec
            else:
                break
        if owner is None:
            continue
        tds = RE_TD.findall(m.group(1))
        if not tds:
            continue
        if len(tds) > i_time and _strip(tds[i_time]):
            owner["times"].append(_strip(tds[i_time]))
        if len(tds) > i_room and _strip(tds[i_room]):
            owner["room"] = _strip(tds[i_room])
        inst = RE_INSTRUCTOR.findall(tds[i_instr]) if len(tds) > i_instr else []
        for i in inst:
            if i not in owner["instructors"]:
                owner["instructors"].append(i)

    out = []
    for s in sections:
        s["datetime"] = ", ".join(t for t in s["times"] if t)
        s.pop("times", None)
        s.pop("section_id", None)
        s.pop("remarks", None)
        out.append(s)
    return out


# ── async 抓取 ─────────────────────────────────────────────
def list_subjects(html: str, session: str) -> list:
    seen, out = set(), []
    for sess, subj in RE_SUBJECT.findall(html):
        if sess != session or subj in seen:
            continue
        seen.add(subj)
        out.append(subj)
    return sorted(out)


async def _fetch_one(subj: str, session: str, raw: Path, force: bool,
                     sem: asyncio.Semaphore) -> tuple:
    p = raw / f"{subj}.html"
    if not force and p.exists():
        return "skip", subj, ""
    url = f"{BASE}/wcq/cgi-bin/{session}/subject/{subj}"
    async with sem:
        html, reason = await asyncio.to_thread(_get, url)
    if not html:
        return "fail", subj, reason
    p.write_text(html, encoding="utf-8")
    return "ok", subj, ""


# 入学年份 → CC 组映射（与 database/common-core/README.md 一致）
CC_GROUPS = {
    "4Y": "before_2022", "CC22": "2022_2024", "CC25": "2025", "CC26": "2026_onward",
}


def admission_to_group(admission_year: str) -> str:
    """admission_year（如 2023-24）→ CC 组（4Y/CC22/CC25/CC26）"""
    m = re.match(r"(\d{4})", str(admission_year or ""))
    if not m:
        return ""
    y = int(m.group(1))
    if y <= 2021:
        return "4Y"
    if y <= 2024:
        return "CC22"
    if y == 2025:
        return "CC25"
    return "CC26"


async def _fetch_cc_area(group: str, area: dict, session: str, raw: Path,
                         sem: asyncio.Semaphore, force: bool = False) -> tuple:
    p = raw / "common_core" / f"{group}-{area['code']}.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not force and p.exists():
        return "skip", area["label"]
    url = f"{BASE}{group_area_url(group, area['code'], session)}"
    async with sem:
        status, html = await asyncio.to_thread(_get_status, url)
    if status == 404:
        # 该区域今年无课（如部分 UxOP）→ 空文件标记，避免重复请求
        p.write_text("", encoding="utf-8")
        return "empty", area["label"]
    if not html:
        return "fail", area["label"]
    p.write_text(html, encoding="utf-8")
    return "ok", area["label"]


def _get_status(url: str) -> tuple:
    """返回 (status_code, text)"""
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            return r.status_code, (r.text if r.status_code == 200 else "")
        except requests.RequestException:
            pass
    return 0, ""


def group_area_url(group: str, area_code: str, session: str) -> str:
    return f"/wcq/cgi-bin/{session}/common_core/{group}/{area_code}"


async def run(args) -> int:
    sem = asyncio.Semaphore(args.concurrency)
    raw = RAW_ROOT / args.session
    raw.mkdir(parents=True, exist_ok=True)

    idx_html, idx_reason = await asyncio.to_thread(
        _get, f"{BASE}/wcq/cgi-bin/{args.session}/")
    if not idx_html:
        sys.exit(f"错误: 无法抓取 WCQ 索引页（{idx_reason or 'w5.ab.ust.hk 不可达'}）")
    idx = idx_html
    subjects = list_subjects(idx, args.session)
    print(f"共 {len(subjects)} 个 subject（{args.session}）")

    cc_options = parse_cc_options(idx, args.session)
    if args.cc_group:
        groups = [g for g in cc_options if g["group"] == args.cc_group]
        if not groups:
            sys.exit(f"错误: CC 组 {args.cc_group} 不在下拉中: "
                     f"{[g['group'] for g in cc_options]}")
        group = groups[0]
        print(f"Common Core 组 {group['group']}（{group['group_label']}）: "
              f"{len(group['areas'])} 个区域")
        stats = {"ok": 0, "skip": 0, "fail": 0, "empty": 0}
        for status, label in await asyncio.gather(
            *[_fetch_cc_area(args.cc_group, a, args.session, raw, sem, args.force)
              for a in group["areas"]]
        ):
            stats[status] += 1
            mark = {"ok": "OK", "skip": "SKIP", "empty": "EMPTY", "fail": "FAIL"}[status]
            print(f"  [{mark}] {label}")
        # 汇总 CC 课程 → data/cc_courses_{session}.json
        label_map = {a["code"]: a["label"] for a in group["areas"]}
        cc_all, cc_dir = [], raw / "common_core"
        for p in sorted(cc_dir.glob(f"{args.cc_group}-*.html")):
            html = p.read_text(encoding="utf-8", errors="ignore")
            code = p.stem.split("-", 1)[1] if "-" in p.stem else p.stem
            label = label_map.get(code, code)
            courses = parse_cc_page(html, label)
            cc_all.append({"area_code": code, "area": label, "course_count": len(courses),
                           "courses": courses})
        cc_out = {
            "session": args.session,
            "cc_group": args.cc_group,
            "group_label": group["group_label"],
            "area_count": len(cc_all),
            "areas": cc_all,
        }
        cc_dest = DATA_DIR / f"cc_courses_{args.session}.json"
        cc_dest.write_text(json.dumps(cc_out, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        print(f"CC 课程汇总 {sum(a['course_count'] for a in cc_all)} 门 -> {cc_dest}")
        if not args.subject:
            return 0

    if args.subject:
        targets = [s for s in subjects if s == args.subject.upper()]
        if not targets:
            sys.exit(f"错误: subject {args.subject} 不在列表中")
    elif args.list_only:
        print("\n".join(subjects) if subjects else "(无 subject)")
        return 0
    else:
        targets = subjects

    stats = {"ok": 0, "skip": 0, "fail": 0}
    fail_reasons = {}
    for status, subj, reason in await asyncio.gather(
        *[_fetch_one(s, args.session, raw, args.force, sem) for s in targets]
    ):
        stats[status] += 1
        mark = {"ok": "[OK]", "skip": "[SKIP]", "fail": "[FAIL]"}[status]
        line = f"  {mark} {subj}"
        if status == "fail":
            fail_reasons[reason] = fail_reasons.get(reason, 0) + 1
            line += f"  ← {reason}"
        print(line)
    print(f"\n抓取统计: {stats}")
    if fail_reasons:
        print("失败原因汇总（可能是服务器繁忙/网络问题，可稍后 --force 重抓未成功的 subject）:")
        for reason, n in sorted(fail_reasons.items(), key=lambda x: -x[1]):
            print(f"  - {reason}: {n} 个 subject")

    # 汇总解析 → data/courses_{session}.json
    all_courses, semester = [], ""
    for p in sorted(raw.glob("*.html")):
        html = p.read_text(encoding="utf-8", errors="ignore")
        sm = RE_SEMESTER.search(html)
        if sm and not semester:
            semester = f"{sm.group(1)} {sm.group(2)}"
        data = parse_subject_page(html, args.session, p.stem)
        all_courses.extend(data["courses"])

    out = {
        "session": args.session,
        "semester_name": semester or "",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "course_count": len(all_courses),
        "courses": all_courses,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / f"courses_{args.session}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n汇总 {len(all_courses)} 门课 -> {dest}")
    return 0


def selftest() -> int:
    """解析器自测：用保存的 subject 页验证 mainRow/otherRow 合并"""
    fx = Path(__file__).resolve().parent / "fixtures"
    ok = True

    def check(name: str, cond: bool):
        nonlocal ok
        print(f"  [{'OK' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    sample = """<div class="course">
  <div class="courseanchor"><a name="ACCT3010">&nbsp;</a></div>
  <div class='subject'>ACCT 3010 - Financial Accounting I (3 units)</div>
  <div class="courseattr"><div class="popupdetail">
<table><tr><th>PRE-REQUISITE</th><td>ACCT 2010</td></tr><tr><th>EXCLUSION</th><td>ACCT 3030</td></tr></table>
  </div></div>
<table class="sections">
<tr class="newsect secteven mainRow"><td >L1 (1054)</td><td>Mo 01:30PM - 02:50PM</td><td>G012, LSK Bldg (199)</td><td class="instructor"><div class="instructorList"><a href="/wcq/cgi-bin/2610/instructor/ZANG%2C%20Amy%20Yunzhi">ZANG, Amy Yunzhi</a></div></td><td class="instructor"></td><td class="quota" align="center"><span>65</span></td><td align="center">0</td><td align="center">65</td><td align="center">0</td><td align="center"></td></tr>
<tr class="mobileInstructorRow"><td></td><td>Instructor</td></tr>
<tr class="secteven otherRow"><td><span></span></td><td>Fr 09:00AM - 10:20AM</td><td>G012, LSK Bldg (199)</td><td class="instructor"><div class="instructorList"><a href="/wcq/cgi-bin/2610/instructor/ZANG%2C%20Amy%20Yunzhi">ZANG, Amy Yunzhi</a></div></td><td class="instructor"></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr class="mobileViewDetail"><td colspan="10">detail</td></tr>
</table>
</div>"""
    d = parse_subject_page(sample, "2610", "ACCT")
    check("解析出 1 门课", len(d["courses"]) == 1)
    c = d["courses"][0]
    check("代码 ACCT 3010", c["code"] == "ACCT" and c["number"] == "3010")
    check("标题/学分", c["title"] == "Financial Accounting I" and c["units"] == 3.0)
    check("pre-req/exclusion", c["attributes"].get("PRE-REQUISITE") == "ACCT 2010"
          and c["attributes"].get("EXCLUSION") == "ACCT 3030")
    sec = c["sections"]
    check("1 个 section", len(sec) == 1)
    check("多时段合并", sec[0]["datetime"] == "Mo 01:30PM - 02:50PM, Fr 09:00AM - 10:20AM")
    check("导师", sec[0]["instructors"] == ["ZANG, Amy Yunzhi"])
    check("quota/enrol", sec[0]["quota"] == 65 and sec[0]["enrol"] == 0)

    # CC 下拉解析
    idx_sample = (
        '<li><div class="mainmenu"><a href="/wcq/cgi-bin/2610/common_core/CC26">'
        'Students admitted from 2026</a></div><ul class="submenu">'
        '<li><a href="/wcq/cgi-bin/2610/common_core/CC26/47">'
        'Common Core (HAIC) for 30-credit prog fr 26</a></li>'
        '<li><a href="/wcq/cgi-bin/2610/common_core/CC26/48">'
        'Common Core (HMW) for 30-credit prog fr 26</a></li></ul></li>'
    )
    groups = parse_cc_options(idx_sample, "2610")
    check("CC 组解析", len(groups) == 1 and groups[0]["group"] == "CC26"
          and len(groups[0]["areas"]) == 2
          and groups[0]["areas"][0]["code"] == "47")
    # 入学年份 → 组
    check("admission 映射 2023-24→CC22", admission_to_group("2023-24") == "CC22")
    check("admission 映射 2026-27→CC26", admission_to_group("2026-27") == "CC26")
    check("admission 映射 2021-22→4Y", admission_to_group("2021-22") == "4Y")
    # CC 区域页解析（跨 subject）
    cc_page = sample.replace('ACCT 3010 - Financial Accounting I (3 units)',
                             'AISC 1000A - Foundations of AI Literacy (3 units)') \
                    .replace('<a name="ACCT3010">', '<a name="AISC1000A">')
    cc_courses = parse_cc_page(cc_page, "HAIC")
    check("CC 区域页解析", len(cc_courses) == 1
          and cc_courses[0]["code"] == "AISC")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser(description="WCQ Class Schedule 爬虫（async）")
    ap.add_argument("--session", default="2610", help="学期代码（2610 = 2026-27 Fall）")
    ap.add_argument("--subject", help="只抓单个 subject")
    ap.add_argument("--cc-group", choices=["4Y", "CC22", "CC25", "CC26"],
                    help="抓指定入学年份组的 Common Core 课程（不抓 subject）")
    ap.add_argument("--admission-year", help="入学年份（如 2023-24）→ 自动选 CC 组")
    ap.add_argument("--force", action="store_true", help="强制重抓已存在页面")
    ap.add_argument("--list-only", action="store_true", help="只列出 subject 列表")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
    else:
        if args.admission_year:
            g = admission_to_group(args.admission_year)
            if not g:
                sys.exit(f"错误: 无法解析入学年份 {args.admission_year}")
            if args.cc_group and args.cc_group != g:
                sys.exit(f"错误: --cc-group {args.cc_group} 与入学年份推导的 {g} 不一致")
            args.cc_group = g
            print(f"入学年份 {args.admission_year} → Common Core 组 {g}")
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
