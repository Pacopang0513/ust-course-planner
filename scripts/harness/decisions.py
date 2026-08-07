#!/usr/bin/env python3
"""
用户决策日志 — scripts/harness/decisions.py
===========================================
记录 P1-P5 各确认点的用户回答（审计 + 断点续跑依据），落 data/decisions.json。
schema: templates/schemas/decisions.schema.json。

用法（库 API）:
  from harness.decisions import load, set_decision, get_decision
  set_decision(root, "P3", {"confirmed": True, "target_credits": 15})
  set_decision(root, "phase4.5", {"must_take": ["PHYS 4291"]})
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISIONS = ROOT / "data" / "decisions.json"


def load(root=None) -> dict:
    p = Path(root) / "data" / "decisions.json" if root else DECISIONS
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"[DECISIONS] 错误: {p} 损坏（{e}）")


def set_decision(root, key: str, value) -> dict:
    """记录/覆盖一个确认点回答；返回最新 decisions 全量"""
    d = load(root)
    d[key] = value
    d["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write(root, d)
    return d


def get_decision(root, key: str):
    return load(root).get(key)


def track(root=None) -> str:
    """当前决策点清单（供 AI 展示）。P4/P5 已并入 P3（过滤结果随学分确认
    展示、方案展示后用户可要求修改），不再作为独立强制确认点。"""
    d = load(root)
    order = ["P1", "P2", "P3", "phase4.5"]
    return ", ".join(f"{k}✓" if k in d else f"{k}?" for k in order)


def _write(root, d: dict):
    p = Path(root) / "data" / "decisions.json" if root else DECISIONS
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="决策日志工具")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show", help="显示全部决策")
    p.set_defaults(fn=lambda a: print(json.dumps(load(), ensure_ascii=False, indent=2)))
    p = sub.add_parser("set", help="记录决策: set <KEY> '<json 值>'")
    p.add_argument("key")
    p.add_argument("value")
    p.set_defaults(fn=lambda a: print("[DECISIONS] OK:", json.dumps(
        set_decision(None, a.key, json.loads(a.value)), ensure_ascii=False)))
    args = ap.parse_args()
    args.fn(args)
