#!/usr/bin/env python3
"""
ugcourse 课程目录解析器 — course_catalog.py（async 并发）
==========================================================
抓取 Program & Course Catalog 的 ugcourse 课程详情页（公开数据，无 cookie）。

每门课输出: 代码 / 标题 / 学分 / 属性(prerequisite/corequisite/exclusion/
co-list/equivalent/previous-codes/delivery) / 描述。供 phase3 做可修性检查。

用法:
  python3 scripts/prog_crs/course_catalog.py --all --year <YEAR>
  python3 scripts/prog_crs/course_catalog.py --subject COMP --year <YEAR>
  python3 scripts/prog_crs/course_catalog.py --list-subjects
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import requests

BASE = "https://prog-crs.hkust.edu.hk"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "database" / "course_catalog"
HEADERS = {"User-Agent": "Mozilla/5.0 (course-arranger build script)"}

CODE_RE = re.compile(r"([A-Z]{3,4})\s?(\d{4}[A-Z]?)")

# 标准属性名（页面上同一属性可能有两种渲染形态）
ATTR_NAMES = [
    "Intended Learning Outcomes", "Prerequisite(s)", "Corequisite(s)",
    "Exclusion(s)", "Cross-Campus Equivalent Course", "Mode of Delivery",
    "Medium of Instruction", "Reading Material", "Alternate code(s)",
    "Background", "Co-list with", "Remarks", "Description",
]
# 合并键：页面将 "Previous Course Code(s) <旧课号> <属性名>" 渲染在同一行，
# 例如 "Previous Course Code(s) CENG 2110 Prerequisite(s)"
MERGED_KEY = re.compile(
    r"^Previous Course Code\(s\)\s+(.+?)\s+((?:"
    + "|".join(re.escape(a) for a in ATTR_NAMES)
    + r"))$"
)


def split_key(key: str) -> list:
    """归一化属性键：合并键拆成标准键，返回 [(键, 文本覆盖或 None)]"""
    m = MERGED_KEY.match(key)
    if m:
        return [("Previous Course Code(s)", m.group(1)), (m.group(2), None)]
    return [(key, None)]


def _get(url: str) -> str:
    for _ in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                return r.text
        except requests.RequestException:
            pass
    return ""


def _strip(html: str) -> str:
    html = re.sub(r"<[^>]+>", " ", html)
    html = html.replace("&amp;", "&").replace("&nbsp;", " ").replace("&#39;", "'")
    return re.sub(r"\s+", " ", html).strip()


def parse_course_block(block: str) -> dict:
    m_code = re.search(r'class="crse-code">(.*?)</div>', block)
    m_title = re.search(r'class="crse-title">(.*?)</div>', block)
    m_unit = re.search(r'class="crse-unit">(.*?)</div>', block)
    if not (m_code and m_title and m_unit):
        return None
    code = _strip(m_code.group(1))
    title = _strip(m_title.group(1))
    unit = _strip(m_unit.group(1))
    credits = 0.0
    m = re.search(r"([\d.]+)\s*Credit", unit)
    if m:
        credits = float(m.group(1))

    attrs = {}
    for row in re.finditer(
        r'<div class="data-row[^"]*">\s*<div class="header"[^>]*>(.*?)</div>\s*<div class="data">(.*?)</div>\s*</div>',
        block, re.DOTALL,
    ):
        key = _strip(row.group(1)).rstrip(":")
        val = _strip(row.group(2))
        if not key:
            continue
        codes = [f"{a} {b}" for a, b in CODE_RE.findall(val)]
        for k, prev in split_key(key):
            if prev is not None:
                # 合并键中的 "Previous Course Code(s)" 部分：值即旧课号文本
                attrs[k] = {"text": prev,
                            "codes": [f"{a} {b}" for a, b in CODE_RE.findall(prev)]}
            else:
                attrs[k] = {"text": val, "codes": codes}

    return {"code": code, "title": title, "credits": credits, "attributes": attrs}


def parse_subject(html: str, subj: str, url: str, year: str) -> dict:
    courses, dropped = [], 0
    for block in re.split(r'<li class="crse accordion-item">', html)[1:]:
        try:
            c = parse_course_block(block)
        except (AttributeError, TypeError):
            c = None
        if c is None:
            dropped += 1
            continue
        courses.append(c)
    return {"subject": subj, "year": year, "courses": courses,
            "source": {"url": url}, "dropped_blocks": dropped}


def list_subjects(year: str, html: str) -> list:
    seen, subs = set(), []
    for href, subj in re.findall(r'href="(/ugcourse/' + year + r'/([A-Z0-9]+)/?)"', html):
        if subj not in seen:
            seen.add(subj)
            subs.append((subj, f"{BASE}{href}"))
    return subs


async def run(args) -> int:
    sem = asyncio.Semaphore(args.concurrency)
    idx_html = await asyncio.to_thread(_get, f"{BASE}/ugcourse")
    if not idx_html:
        sys.exit("错误: 无法抓取 ugcourse 索引页")
    subjects = list_subjects(args.year, idx_html)

    if args.list_subjects:
        print("\n".join(f"{s}  {u}" for s, u in subjects))
        return 0

    if args.subject:
        targets = [(s, u) for s, u in subjects if s == args.subject.upper()]
        if not targets:
            sys.exit(f"错误: 找不到 subject {args.subject}")
    elif args.all:
        targets = subjects
    else:
        sys.exit("请指定 --all 或 --subject")

    out = OUT / args.year
    out.mkdir(parents=True, exist_ok=True)

    async def fetch(s, u):
        p = out / f"{s}.json"
        if not args.force and p.exists():
            return s, None, "skip"
        async with sem:
            html = await asyncio.to_thread(_get, u)
        if not html:
            return s, None, "fail"
        return s, parse_subject(html, s, u, args.year), "ok"

    ok = skip = fail = 0
    for s, data, status in await asyncio.gather(*[fetch(s, u) for s, u in targets]):
        if status == "skip":
            print(f"  [SKIP] {s}: 已存在")
            skip += 1
            continue
        if status == "fail" or data is None:
            print(f"  ❌ {s}: 抓取失败")
            fail += 1
            continue
        p = out / f"{s}.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        msg = f"（跳过 {data['dropped_blocks']} 个残缺块）" if data["dropped_blocks"] else ""
        print(f"  ✅ {s}: {len(data['courses'])} 门课{msg} -> {p}")
        ok += 1
    print(f"\n完成: {ok}/{len(targets)}（skip {skip}, fail {fail}）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="ugcourse 课程目录解析器（async）")
    ap.add_argument("--year", default="")
    ap.add_argument("--all", action="store_true", help="抓取全部 subject")
    ap.add_argument("--subject", help="抓取单个 subject")
    ap.add_argument("--list-subjects", action="store_true")
    ap.add_argument("--force", action="store_true", help="强制重抓已存在文件")
    ap.add_argument("--concurrency", type=int, default=8, help="并发数（默认 8）")
    args = ap.parse_args()
    if not args.year:
        sys.exit("错误: 缺少 --year（入学年份，如运行中由 ustplan status 查询）")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
