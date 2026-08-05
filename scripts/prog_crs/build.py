#!/usr/bin/env python3
"""
prog-crs 预构建编排器 — build.py
================================
离线一次性构建本地课程/专业库，供 phase3 运行时只读消费：

  1. crawler.py        抓取全部 curriculum PDF → cache/prog-crs/raw/
  2. parser.py         解析 → database/curriculum/{code}.json
  3. course_catalog.py 抓取 ugcourse → database/course_catalog/{subj}.json

用法:
  python3 scripts/prog_crs/build.py             # 全量构建
  python3 scripts/prog_crs/build.py --no-catalog   # 跳过课程目录
  python3 scripts/prog_crs/build.py --only catalog # 只建课程目录
  python3 scripts/prog_crs/build.py --force        # 强制重抓 PDF
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
HERE = Path(__file__).resolve().parent


def run(script: str, extra: list, step: str):
    print(f"\n=== {step}: {script} ===")
    r = subprocess.run([PY, str(HERE / script), *extra], cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"错误: {step} 失败 (exit {r.returncode})")


def main():
    ap = argparse.ArgumentParser(description="prog-crs 预构建")
    ap.add_argument("--year", default="2026-27", help="入学年份（curriculum 按年版本化）")
    ap.add_argument("--force", action="store_true", help="强制重抓 PDF")
    ap.add_argument("--no-catalog", action="store_true", help="跳过 ugcourse 课程目录")
    ap.add_argument("--only", choices=["all", "catalog", "curriculum"], default="all")
    args = ap.parse_args()
    year = args.year

    if args.only in ("all", "curriculum"):
        run("crawler.py", ["--year", year, "--force"] if args.force else ["--year", year],
            "下载 curriculum PDF")
        run("parser.py", ["--dir", f"cache/prog-crs/raw/{year}"], "解析 curriculum 候选索引")

    if args.only in ("all", "catalog") and not args.no_catalog:
        run("course_catalog.py", ["--all", "--year", year], "抓取 ugcourse 课程目录")

    marker = ROOT / "database" / "build.json"
    builds = {}
    if marker.exists():
        try:
            builds = json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            builds = {}
    builds[year] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    marker.write_text(json.dumps(builds, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(f"\n✅ 预构建完成（{year}），标记 -> {marker}")
    print(f"   已构建年份: {list(builds)}")


if __name__ == "__main__":
    main()
