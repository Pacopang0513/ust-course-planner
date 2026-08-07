#!/usr/bin/env python3
"""
运行清单 — scripts/harness/manifest.py
======================================
维护 data/manifest.json：run 状态追踪（run_id / session / 产物 sha256 +
schema 版本 / step 完成记录）。与 checkpoint.json（顺序）互补：
manifest 管"做了什么、产物是谁产生的"，checkpoint 管"现在该做什么"。

用法（库 API，供 ustplan.py / contracts.py 调用）:
  from harness.manifest import load, init, record_artifact, step_done, phase_done
  m = load(root)                    # 读清单；不存在返回 None
  init(root, run_id, session, admission_year)  # 新建/重置清单
  ok, errs = record_artifact(root, "data/courses_<SESSION>.json", "courses", "wcq_full")
                                    # 校验 + 记录 sha256/schema 版本
  step_done(root, "step1")          # 记录 step 完成
  phase_done(root, "phase1-input")  # 记录 phase 完成时间
  resolve_session(root, cfg)        # 优先级：manifest → config → None
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "manifest.json"
SCHEMA_DIR = ROOT / "templates" / "schemas"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load(root=None) -> dict:
    p = Path(root) / "data" / "manifest.json" if root else MANIFEST
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"[MANIFEST] 错误: {p} 损坏（{e}），可删除后重建")


def init(root=None, run_id: str = None, session: str = None,
         admission_year=None) -> dict:
    p = Path(root) / "data" / "manifest.json" if root else MANIFEST
    p.parent.mkdir(parents=True, exist_ok=True)
    m = {
        "run_id": run_id or datetime.now().strftime("%Y%m%d-%H%M%S"),
        "started_at": _now(),
        "session": session,
        "admission_year": admission_year,
        "updated_at": _now(),
        "artifacts": {},
        "steps": {},
        "phases": {},
    }
    p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return m


def _schema_version(schema_name: str) -> int:
    p = SCHEMA_DIR / f"{schema_name}.schema.json"
    try:
        v = json.loads(p.read_text(encoding="utf-8")).get("version")
        return int(v) if isinstance(v, (int, float)) else 1
    except (OSError, json.JSONDecodeError, ValueError):
        return 1


def validate_artifact(root, relpath: str, schema_name: str) -> list:
    """产物 → 对应 schema 校验，返回错误列表（R2 语义）；schema_name=None 仅检查存在"""
    target = (Path(root) if root else ROOT) / relpath
    if not target.exists():
        return [f"缺少产物 {relpath}"]
    if not schema_name:
        return []
    from harness.schema_validate import validate_file
    schema = SCHEMA_DIR / f"{schema_name}.schema.json"
    if not schema.exists():
        return [f"缺少 schema {schema_name}.schema.json"]
    return validate_file(target, schema)


def record_artifact(root, relpath: str, schema_name: str, produced_by: str):
    """校验产物 + 记录 sha256/schema 版本；校验失败返回 (False, errors)。
    schema_name 可为 None（仅记录哈希，如 cache/ 原始产物）。"""
    m = load(root) or init(root=root)
    errors = validate_artifact(root, relpath, schema_name)
    if errors:
        return False, errors
    target = (Path(root) if root else ROOT) / relpath
    m.setdefault("artifacts", {})[relpath.replace("\\", "/")] = {
        "sha256": _sha256(target),
        "schema": schema_name,
        "schema_version": _schema_version(schema_name) if schema_name else None,
        "produced_by": produced_by,
        "produced_at": _now(),
    }
    m["updated_at"] = _now()
    _write(root, m)
    return True, []


def step_done(root, step: str):
    m = load(root) or init(root=root)
    m.setdefault("steps", {})[step] = {"status": "done", "done_at": _now()}
    m["updated_at"] = _now()
    _write(root, m)


def step_failed(root, step: str):
    m = load(root) or init(root=root)
    m.setdefault("steps", {})[step] = {"status": "failed", "done_at": _now()}
    m["updated_at"] = _now()
    _write(root, m)


def phase_done(root, phase: str):
    m = load(root) or init(root=root)
    m.setdefault("phases", {})[phase] = {"done_at": _now()}
    m["updated_at"] = _now()
    _write(root, m)


def resolve_session(root=None, cfg: dict = None) -> str:
    """session 优先级：manifest（已确认）→ config → None"""
    m = load(root)
    if m and m.get("session"):
        return m["session"]
    if cfg and cfg.get("session"):
        return cfg["session"]
    return None


def resolve_admission_year(root=None) -> str:
    m = load(root)
    return m.get("admission_year") if m else None


def _write(root, m: dict):
    p = Path(root) / "data" / "manifest.json" if root else MANIFEST
    p.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="运行清单工具")
    ap.add_argument("cmd", choices=["show", "init", "check"])
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--session", default=None)
    ap.add_argument("--admission-year", default=None)
    args = ap.parse_args()
    if args.cmd == "show":
        m = load()
        if not m:
            sys.exit("[MANIFEST] 无运行清单（data/manifest.json 不存在）")
        print(json.dumps(m, ensure_ascii=False, indent=2))
    elif args.cmd == "init":
        init(session=args.session, admission_year=args.admission_year,
             run_id=args.run_id)
        print("[MANIFEST] OK: 运行清单已初始化")
    elif args.cmd == "check":
        errors = validate_artifact(ROOT, "data/manifest.json", "manifest")
        if errors:
            for e in errors:
                print(e)
            sys.exit(1)
        print("[MANIFEST] OK: 清单结构合法")
