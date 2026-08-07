#!/usr/bin/env python3
"""
环境预检 — scripts/harness/doctor.py
====================================
一键检查运行环境：Python 版本 / 依赖 / 配置合法性 / cookie 状态 /
database 预构建完整性 / schema 完整性 / 运行状态一致性 / 后台任务孤儿。

用法:
  python scripts/harness/doctor.py           # 全量预检（exit 0/1）
  python scripts/harness/doctor.py --check-cookies-only
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable

REQUIRED_MODULES = ("requests", "jsonschema")


def _run(args: list, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def check_python() -> list:
    v = sys.version_info
    return [] if v >= (3, 9) else [f"Python >= 3.9 需要（当前 {v.major}.{v.minor}）"]


def check_modules() -> list:
    errs = []
    for mod in REQUIRED_MODULES:
        try:
            __import__(mod)
        except ImportError:
            errs.append(f"缺少依赖 {mod}（pip install requests jsonschema）")
    return errs


def check_config() -> list:
    sys.path.insert(0, str(ROOT / "scripts"))
    from harness.config import load, validate_schema
    try:
        cfg = load()
    except SystemExit as e:
        return [str(e)]
    errs = validate_schema(cfg)
    return [f"配置: {e}" for e in errs]


def check_cookies() -> list:
    p = ROOT / "scripts" / "cookies_setup.py"
    if not p.exists():
        return ["缺少 scripts/cookies_setup.py"]
    r = _run([PY, str(p), "--check"])
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    if not lines:
        return [f"cookie 预检无输出（exit {r.returncode}）"]
    # 仅当预检失败（非 0 退出）或含失效/缺失状态时报告；全 OK 视为通过
    bad = [ln for ln in lines
           if any(k in ln for k in ("EXPIRED", "MISSING", "UNREACHABLE"))]
    if r.returncode != 0 or bad:
        return [f"cookie: {ln}" for ln in (bad or lines)]
    return []


def check_database() -> list:
    errs = []
    p = ROOT / "database" / "build.json"
    if not p.exists():
        return ["缺少 database/build.json（未预构建？）"]
    try:
        build = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"database/build.json 损坏（{e}）"]
    years = [k for k in build if k not in ("built_at", "steps")]
    if not years:
        errs.append("database/build.json 未记录预构建年份")
    for y in years:
        d = ROOT / "database" / "curriculum" / y
        if not d.is_dir():
            errs.append(f"curriculum/{y} 目录缺失（build.json 声明但不存在）")
        elif not any(d.glob("*.json")):
            errs.append(f"curriculum/{y} 为空目录")
    return errs


def check_schemas() -> list:
    errs = []
    sd = ROOT / "templates" / "schemas"
    if not sd.is_dir():
        return ["缺少 templates/schemas/"]
    for p in sorted(sd.glob("*.schema.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if "version" not in data:
                errs.append(f"{p.name} 缺少 version 字段")
        except json.JSONDecodeError as e:
            errs.append(f"{p.name} 不是合法 JSON（{e}）")
    return errs


def check_state() -> list:
    """checkpoint / manifest / jobs 一致性"""
    errs = []
    cp = ROOT / "data" / "checkpoint.json"
    if cp.exists():
        try:
            state = json.loads(cp.read_text(encoding="utf-8"))
            for p in state.get("completed", []):
                if p not in ("phase1-input", "phase2-profile",
                             "phase3-course-analysis", "phase4-report",
                             "phase4.5-must-take"):
                    errs.append(f"checkpoint 含未知阶段: {p}")
        except json.JSONDecodeError as e:
            errs.append(f"data/checkpoint.json 损坏（{e}）")
    jobs = ROOT / "data" / "jobs"
    if jobs.is_dir():
        for started in jobs.glob("*.started"):
            done = started.with_suffix(".done")
            if done.exists():
                continue
            try:
                rec = json.loads(started.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not _pid_alive(rec.get("worker_pid")):
                errs.append(f"后台任务 {started.stem} crashed（孤儿记录，"
                            f"jobs.py clean {started.stem} 清理）")
    return errs


def _pid_alive(pid) -> bool:
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True, timeout=10).stdout
            return str(pid) in out
        except Exception:
            return False
    try:
        import os
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser(description="环境预检（doctor）")
    ap.add_argument("--cookies-only", action="store_true", help="只查 cookie 状态")
    args = ap.parse_args()

    checks = []
    if args.cookies_only:
        checks = [("cookie 状态", check_cookies())]
    else:
        checks = [
            ("Python 版本", check_python()),
            ("依赖", check_modules()),
            ("配置", check_config()),
            ("cookie 状态", check_cookies()),
            ("database 预构建", check_database()),
            ("schema 完整性", check_schemas()),
            ("运行状态", check_state()),
        ]

    all_ok = True
    for name, errs in checks:
        if errs:
            all_ok = False
            print(f"[FAIL] {name}")
            for e in errs:
                print(f"       {e}")
        else:
            print(f"[OK]   {name}")
    print("\n结果:", "全部正常，可开始运行" if all_ok else "存在问题，修复后再运行")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
