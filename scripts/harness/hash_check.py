#!/usr/bin/env python3
"""
R1 只读完整性检查 — hash_check.py
=================================
对运行时只读文件集做内容哈希快照与比对。

用法:
  python scripts/harness/hash_check.py snapshot -o <snapshot.json>   # 记录只读集哈希
  python scripts/harness/hash_check.py verify  -s <snapshot.json>    # 比对，不一致 exit 1

只读集（与 docs/permissions.md 一致）:
  skills/ database/ templates/ user/ scripts/ opencode.json
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

READONLY_DIRS = ["skills", "database", "templates", "user", "scripts"]
READONLY_FILES = ["opencode.json"]

SKIP_NAMES = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def _iter_readonly_files():
    for d in READONLY_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_dir():
                continue
            if p.name in SKIP_NAMES or p.suffix in SKIP_SUFFIXES:
                continue
            yield p
    for name in READONLY_FILES:
        p = ROOT / name
        if p.exists():
            yield p


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot() -> dict:
    return {
        "files": {
            str(p.relative_to(ROOT)).replace("\\", "/"): _sha256(p)
            for p in _iter_readonly_files()
        }
    }


def verify(snapshot_path: Path) -> int:
    with open(snapshot_path, encoding="utf-8") as f:
        before = json.load(f)["files"]

    now = {
        str(p.relative_to(ROOT)).replace("\\", "/"): _sha256(p)
        for p in _iter_readonly_files()
    }

    changed = [k for k in before if k in now and before[k] != now[k]]
    removed = [k for k in before if k not in now]
    added = [k for k in now if k not in before]

    if not (changed or removed or added):
        print(f"[R1] OK: 只读集 {len(before)} 个文件哈希一致")
        return 0

    print("[R1] FAIL: 只读文件集被修改")
    for k in changed:
        print(f"  CHANGED {k}")
    for k in removed:
        print(f"  REMOVED {k}")
    for k in added:
        print(f"  ADDED   {k}")
    return 1


def main():
    parser = argparse.ArgumentParser(description="R1 只读完整性检查")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_snap = sub.add_parser("snapshot", help="生成只读集哈希快照")
    p_snap.add_argument("-o", "--output", required=True, help="快照输出路径")

    p_ver = sub.add_parser("verify", help="比对只读集哈希")
    p_ver.add_argument("-s", "--snapshot", required=True, help="快照文件路径")

    args = parser.parse_args()

    if args.cmd == "snapshot":
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = snapshot()
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[R1] snapshot: {len(data['files'])} 个文件 -> {out}")
    else:
        sys.exit(verify(Path(args.snapshot)))


if __name__ == "__main__":
    main()
