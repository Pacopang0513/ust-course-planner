#!/usr/bin/env python3
"""
R4 阶段顺序检查 — checkpoint.py
===============================
维护 data/checkpoint.json，强制 phase 顺序执行，禁止跳阶段。

阶段顺序（固定）:
  phase1-input -> phase2-profile -> phase3-course-analysis
  -> phase4-report -> phase4.5-must-take

用法:
  python scripts/harness/checkpoint.py status           # 显示当前状态
  python scripts/harness/checkpoint.py begin <phase>    # 开始阶段（校验前置已完成）
  python scripts/harness/checkpoint.py done <phase>     # 完成阶段
  python scripts/harness/checkpoint.py reset            # 清空检查点

checkpoint.json 结构:
  { "completed": ["phase2-profile", ...],
    "current": "phase3-course-analysis" | null,
    "updated_at": "ISO 时间" }
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT = ROOT / "data" / "checkpoint.json"

PHASE_ORDER = [
    "phase1-input",
    "phase2-profile",
    "phase3-course-analysis",
    "phase4-report",
    "phase4.5-must-take",
]


def _prereqs(phase: str) -> list:
    if phase not in PHASE_ORDER:
        sys.exit(f"[R4] 错误: 未知阶段 '{phase}'，合法阶段: {', '.join(PHASE_ORDER)}")
    idx = PHASE_ORDER.index(phase)
    return PHASE_ORDER[:idx]


def load() -> dict:
    if CHECKPOINT.exists():
        try:
            return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[R4] 错误: data/checkpoint.json 损坏（{e}），请先 reset")
            sys.exit(1)
    return {"completed": [], "current": None, "updated_at": None}


def save(state: dict):
    state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def cmd_status():
    state = load()
    completed = set(state.get("completed", []))
    current = state.get("current")
    print(f"[R4] 当前检查点: data/checkpoint.json")
    for phase in PHASE_ORDER:
        mark = "X" if phase in completed else ("->" if phase == current else " ")
        print(f"  [{mark}] {phase}")
    if current and current in PHASE_ORDER:
        print(f"[R4] 进行中: {current}")
        anomaly = [
            p for p in PHASE_ORDER
            if p in completed and PHASE_ORDER.index(p) > PHASE_ORDER.index(current)
        ]
        if anomaly:
            print(f"[R4] 已完成的后续阶段(异常): {anomaly}")


def cmd_begin(phase: str):
    _prereqs(phase)
    state = load()
    completed = set(state.get("completed", []))
    missing = [p for p in _prereqs(phase) if p not in completed]
    if missing:
        print(f"[R4] FAIL: 跳阶段 — '{phase}' 的前置未完成: {', '.join(missing)}")
        sys.exit(1)
    # 已完成的阶段允许重复 begin（支持全流程重跑/续跑）；但正在进行的其他阶段必须先 done
    cur = state.get("current")
    if cur and cur != phase:
        print(f"[R4] FAIL: '{cur}' 尚未 done，不能 begin '{phase}'")
        sys.exit(1)
    state["current"] = phase
    save(state)
    print(f"[R4] OK: begin {phase}")


def cmd_done(phase: str):
    _prereqs(phase)
    state = load()
    completed = set(state.get("completed", []))
    missing = [p for p in _prereqs(phase) if p not in completed]
    if missing:
        print(f"[R4] FAIL: 跳阶段 — '{phase}' 的前置未完成: {', '.join(missing)}")
        sys.exit(1)
    if state.get("current") != phase:
        print(f"[R4] FAIL: '{phase}' 未处于进行中（current={state.get('current')}），先 begin")
        sys.exit(1)
    completed.add(phase)
    state["completed"] = [p for p in PHASE_ORDER if p in completed]
    state["current"] = None
    save(state)
    print(f"[R4] OK: done {phase}")


def cmd_reset():
    save({"completed": [], "current": None, "updated_at": None})
    print("[R4] OK: 检查点已清空")


def main():
    parser = argparse.ArgumentParser(description="R4 阶段顺序检查")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="显示状态")
    for name in ("begin", "done"):
        p = sub.add_parser(name, help=f"{name} 阶段")
        p.add_argument("phase", choices=PHASE_ORDER)
    sub.add_parser("reset", help="清空")

    args = parser.parse_args()
    if args.cmd == "status":
        cmd_status()
    elif args.cmd == "begin":
        cmd_begin(args.phase)
    elif args.cmd == "done":
        cmd_done(args.phase)
    elif args.cmd == "reset":
        cmd_reset()


if __name__ == "__main__":
    main()
