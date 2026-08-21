#!/usr/bin/env python3
"""
历史学期课表抓取 — scripts/wcq/history_fetch.py
==============================================
后台 job wcq_history 的执行体：对目标 session 的前两个学期（previous_sessions
推导）逐个抓取候选 subject 的 Class Schedule（WCQ 公开页，无需 cookie），
产出 data/courses_{prev}.json，供 step5.5（history_compare.py）对照
"往期是否开设 + 授课教授口碑"。

用法:
  python3 scripts/wcq/history_fetch.py --session 2610 \
      --subjects-file data/history_subjects.json
  python3 scripts/wcq/history_fetch.py --session 2610 \
      --subjects-file data/history_subjects.json --force
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from harness.config import previous_sessions  # noqa: E402
from wcq import crawler  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="历史学期课表抓取（wcq_history job 执行体）")
    ap.add_argument("--session", default="",
                    help="目标学期代码（其前两个学期会被抓取）")
    ap.add_argument("--subjects-file", default=str(ROOT / "data" / "history_subjects.json"),
                    help="subject 名单 JSON 数组（由 ustplan 从 course_scores 汇总）")
    ap.add_argument("--force", action="store_true", help="强制重抓已存在页面")
    args = ap.parse_args()
    if not args.session:
        sys.exit("错误: 缺少 --session（目标学期代码）")

    prevs = previous_sessions(args.session)
    if not prevs:
        print(f"提示: session {args.session} 无有效前序学期（非 4 位学期码），跳过")
        return 0
    p = Path(args.subjects_file)
    subjects = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    if not subjects:
        print(f"提示: subjects 文件 {p} 为空或缺失（候选课程无 subject？），跳过")
        return 0
    print(f"历史学期抓取: 目标 {args.session} ← {', '.join(prevs)}，"
          f"subjects {len(subjects)} 个")

    for prev in prevs:
        print(f"\n== 前序学期 {prev} ==")
        ns = argparse.Namespace(
            session=prev, subject=None, subjects_file=str(p),
            cc_group=None, admission_year=None, force=args.force,
            list_only=False, concurrency=8)
        asyncio.run(crawler.run(ns))
    print("\n历史学期抓取完成: " + ", ".join(
        f"data/courses_{s}.json" for s in prevs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
