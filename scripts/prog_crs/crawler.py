#!/usr/bin/env python3
"""
prog-crs 全量爬虫 — crawler.py（async 并发）
============================================
抓取 Program & Course Catalog 的全部专业要求 PDF 并提取文本。
公开静态数据，无需 cookie。支持断点续抓（已存在则跳过）。

流程:
  1. /ugprog 索引 → 全部 program code + title
  2. /ugprog/{year}/{code} → 提取 curriculum PDF 的 href（不靠猜 URL，并发）
  3. 下载 PDF → cache/prog-crs/raw/{year}/{code}.pdf（并发）
  4. pdftotext -layout → {code}.txt（并发）

用法:
  python3 scripts/prog_crs/crawler.py [--year 2026-27] [--concurrency 8]
  python3 scripts/prog_crs/crawler.py --force          # 强制重抓
  python3 scripts/prog_crs/crawler.py --list-only      # 只更新 manifest，不下载
"""

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://prog-crs.hkust.edu.hk"
ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "cache" / "prog-crs" / "raw"
MANIFEST_ROOT = ROOT / "cache" / "prog-crs"

HEADERS = {"User-Agent": "Mozilla/5.0 (course-arranger build script)"}


# ── 同步网络/子进程（经 asyncio.to_thread 并发执行）──────────
def _get(url: str) -> str:
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.text
        except requests.RequestException:
            pass
    return ""


def _get_bytes(url: str) -> bytes:
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            if r.status_code == 200 and len(r.content) >= 1000:
                return r.content
        except requests.RequestException:
            pass
    return b""


def to_text(pdf: Path, txt: Path) -> int:
    """pdftotext -layout，返回行数；失败返回 0"""
    r = subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not txt.exists():
        return 0
    return len(txt.read_text(encoding="utf-8", errors="ignore").splitlines())


# ── 解析（纯函数）───────────────────────────────────────────
def list_programs(html: str, year: str) -> list:
    seen, programs = set(), []
    for m in re.finditer(
        r'<a href="(/ugprog/' + year + r'/([A-Z0-9-]+))"[^>]*>(.*?)</a>',
        html, re.S
    ):
        href, code = m.group(1), m.group(2)
        title = re.sub(r"<[^>]+>", "", m.group(3)).strip()
        if not title or code in seen:
            continue
        seen.add(code)
        programs.append({"code": code, "title": title, "href": href})
    return programs


def parse_pdf_url(html: str, code: str) -> str:
    """从专业页 HTML 提取"Major Requirements"PDF 的 href。

    页面通常有多个 PDF 链接：School Requirements / Major Requirements / pathway，
    以锚文本含 "Major Requirements" 为准，其次按文件名匹配专业代码；
    优先 prog-crs 站内 PDF（ugadmin/prog_crs），外站 PDF 作为兜底。
    """
    code = code.lower().replace("-", "")
    candidates = []
    for m in re.finditer(r'<a[^>]+href="([^"]*\.pdf)"[^>]*>(.*?)</a>', html, re.S | re.I):
        u = m.group(1)
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip().lower()
        score = 0
        if "major requirements" in text:
            score += 2
        fn = u.lower()
        if code and code in fn.replace("-", ""):
            score += 1
        if "ugadmin" in fn or "prog_crs" in fn:
            score += 1
        if "school requirements" in text or "pathway" in text or "pw_" in fn:
            score -= 1
        candidates.append((score, urljoin(BASE, u)))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


# ── async 任务 ─────────────────────────────────────────────
async def _find_pdf(p: dict, sem: asyncio.Semaphore) -> str:
    async with sem:
        html = await asyncio.to_thread(_get, f"{BASE}{p['href']}")
    return parse_pdf_url(html or "", p["code"])


async def _download_one(p: dict, raw: Path, force: bool,
                        sem: asyncio.Semaphore) -> tuple:
    code = p["code"]
    pdf, txt = raw / f"{code}.pdf", raw / f"{code}.txt"
    if not force and txt.exists() and txt.stat().st_size > 0:
        return "skip", code, 0
    if not p.get("pdf"):
        return "fail", code, "无 PDF URL（外站）"
    async with sem:
        data = await asyncio.to_thread(_get_bytes, p["pdf"])
    if not data:
        return "fail", code, "下载失败/过小"
    pdf.write_bytes(data)
    n = await asyncio.to_thread(to_text, pdf, txt)
    if n > 5:
        return "ok", code, n
    return "fail", code, f"文本过短 ({n} 行)"


async def run(args) -> int:
    if not shutil.which("pdftotext"):
        sys.exit("错误: 缺少 pdftotext（poppler-utils）")
    sem = asyncio.Semaphore(args.concurrency)
    raw = RAW_ROOT / args.year
    raw.mkdir(parents=True, exist_ok=True)

    idx_html = await asyncio.to_thread(_get, f"{BASE}/ugprog")
    if not idx_html:
        sys.exit("错误: 无法抓取 /ugprog 索引页")
    programs = list_programs(idx_html, args.year)
    print(f"索引页共 {len(programs)} 个 program（{args.year}）")

    # 并发定位 PDF URL
    urls = await asyncio.gather(*[_find_pdf(p, sem) for p in programs])
    for p, u in zip(programs, urls):
        p["pdf"] = u
        print(f"  {p['code']}: {'PDF' if u else 'NO PDF (外站)'}")

    manifest = MANIFEST_ROOT / f"{args.year}.manifest.json"
    manifest.write_text(json.dumps(programs, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"manifest -> {manifest}")

    if args.list_only:
        return 0

    # 并发下载 + 提文本
    stats = {"ok": 0, "skip": 0, "fail": 0}
    for status, code, detail in await asyncio.gather(
        *[_download_one(p, raw, args.force, sem) for p in programs]
    ):
        stats[status] += 1
        icon = {"ok": "✅", "skip": "⏭️", "fail": "❌"}[status]
        print(f"  {icon} {code}: {detail}")
    print(f"\n统计: {stats} | 总 {len(programs)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="prog-crs 全量爬虫（async）")
    ap.add_argument("--year", default="2026-27")
    ap.add_argument("--force", action="store_true", help="强制重抓已存在的 PDF")
    ap.add_argument("--list-only", action="store_true", help="只更新 manifest，不下载")
    ap.add_argument("--concurrency", type=int, default=8, help="并发数（默认 8）")
    args = ap.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
