#!/usr/bin/env python3
"""
R4 后台任务管理 — jobs.py
=========================
把耗时抓取（wcq / SIS / USTSPACE）以脱离进程方式后台运行，
与用户问答时间线并行：AI 每次提问前 start，用户回复后 status。
进程在本脚本退出后继续运行（Windows: DETACHED_PROCESS；POSIX: 新会话）。

用法:
  python scripts/harness/jobs.py start <job-id> [--timeout N] [--force] -- <cmd...>
  python scripts/harness/jobs.py status <job-id>
  python scripts/harness/jobs.py list
  python scripts/harness/jobs.py wait <job-id> [--timeout SECONDS]
  python scripts/harness/jobs.py kill <job-id>
  python scripts/harness/jobs.py clean <job-id>

文件（data/jobs/ 下；刻意不用 .json 后缀，避免被 schema 校验扫描）:
  <id>.started    JSON: {job_id, worker_pid, target_pid, cmd, timeout_minutes, started_at}
  <id>.done       JSON: {exit_code, timed_out, killed, started_at, finished_at, cmd}
  <id>.log        目标命令 stdout/stderr（含 worker 自身输出）

退出码:
  start: 0 成功; 1 拒绝（仍在运行 / 已完成未清理）
  status/list: 0 正常; 1 任务不存在
  wait: 0 成功; 1 任务失败; 2 等待超时; 3 任务崩溃
  kill: 0 已终止; 1 任务不存在
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOBS_DIR = ROOT / "data" / "jobs"
PY = sys.executable

PID_ALIVE_GRACE_SEC = 300  # PID 复用防护宽限：timeout 之外的存活判定余量

# 统一 UTF-8 输出（Windows GBK 控制台会因 ✓ 等字符崩溃）
UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

JOB_ID_RE = re.compile(r"[A-Za-z0-9_.-]+$")
WAIT_POLL_SEC = 2
DEFAULT_WAIT_TIMEOUT = 1800


def _utf8_stdio():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _flags() -> int:
    if os.name == "nt":
        return (getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return 0


def _job_paths(job_id: str) -> dict:
    return {
        "started": JOBS_DIR / f"{job_id}.started",
        "done": JOBS_DIR / f"{job_id}.done",
        "log": JOBS_DIR / f"{job_id}.log",
    }


def _load(path: Path) -> dict:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"[JOBS] 警告: {path.name} 损坏，按缺失处理")
        return None


def _write(path: Path, obj: dict):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _pid_alive(pid: int, started: dict = None) -> bool:
    """PID 是否存活。started 提供 job 记录时附加"时间窗"校验：worker 生命周期
    受 timeout_minutes 约束（worker 超时自动击杀），记录早于 timeout+宽限仍
    "存活"的 PID 几乎必是系统复用（Windows 常见：SearchFilterHost 等进程占用
    旧 worker PID），按已退出处理——否则会误报"仍在运行"卡死 start/kill。"""
    if not pid or pid <= 0:
        return False
    if started:
        try:
            st = datetime.fromisoformat(str(started.get("started_at") or ""))
            timeout = float(started.get("timeout_minutes") or 0)
            if timeout > 0 and (datetime.now(timezone.utc) - st).total_seconds() \
                    > timeout * 60 + PID_ALIVE_GRACE_SEC:
                return False
        except (ValueError, TypeError):
            pass
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            return str(pid) in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_tree(pid: int):
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True, timeout=15)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _patch_started(job_id: str, **kw):
    p = _job_paths(job_id)["started"]
    obj = _load(p) or {}
    obj.update(kw)
    _write(p, obj)


def _cleanup_job(job_id: str, started: dict):
    """清理任务记录前先击杀可能残留的孤儿进程（否则 .log 句柄被占用删不掉）。
    PID 复用防护：仅击杀时间窗内"真正属于本 job"的进程。"""
    for key in ("target_pid", "worker_pid"):
        pid = started.get(key)
        if pid and _pid_alive(pid, started):
            _kill_tree(pid)
    for f in JOBS_DIR.glob(f"{job_id}.*"):
        try:
            f.unlink()
        except OSError as e:
            print(f"[JOBS] 警告: 清理 {f.name} 失败（{e}）")


def _write_done(job_id: str, exit_code: int, timed_out: bool,
                killed: bool, started_at: str, cmd: list):
    _write(_job_paths(job_id)["done"], {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "killed": killed,
        "started_at": started_at,
        "finished_at": _now(),
        "cmd": cmd,
    })


# ── 内部：worker（脱离进程本体，负责超时击杀与 done 标记）─────

def _run_job(job_id: str, timeout_minutes: float, cmd: list):
    started_at = _now()
    log_path = _job_paths(job_id)["log"]
    timed_out = killed = False
    exit_code = 126
    # Windows 下 .py 脚本不能直接作为可执行文件启动（WinError 193），
    # 统一经解释器执行，保证全平台行为一致。
    if cmd and str(cmd[0]).lower().endswith(".py"):
        cmd = [PY, *cmd]
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as log:
            proc = subprocess.Popen(
                cmd, cwd=ROOT, stdout=log, stderr=log,
                creationflags=_flags(),
                start_new_session=(os.name != "nt"),
            )
            _patch_started(job_id, target_pid=proc.pid)
            try:
                exit_code = proc.wait(
                    timeout=(timeout_minutes * 60) if timeout_minutes else None)
            except subprocess.TimeoutExpired:
                _kill_tree(proc.pid)
                exit_code, timed_out = 124, True
    except FileNotFoundError:
        print(f"[JOBS] {job_id}: 命令不存在: {cmd[0]}")
        exit_code = 127
    except Exception as e:  # noqa: BLE001  worker 必须收尾
        print(f"[JOBS] {job_id}: 启动失败: {e}")
        exit_code = 126
    finally:
        _write_done(job_id, exit_code, timed_out, killed, started_at, cmd)


def _cmd_run_job(args):
    _run_job(args.job_id, args.timeout, args.cmd)


# ── 主命令 ──────────────────────────────────────────────

def cmd_start(args):
    if not JOB_ID_RE.match(args.job_id):
        sys.exit(f"[JOBS] 错误: 非法 job-id '{args.job_id}'（仅字母数字 _ . -）")
    if not args.cmd:
        sys.exit("[JOBS] 错误: 缺少命令（`--` 后跟要后台执行的命令）")
    paths = _job_paths(args.job_id)

    if paths["done"].exists() and not args.force:
        done = _load(paths["done"])
        sys.exit(f"[JOBS] FAIL: {args.job_id} 已完成（exit {done['exit_code']}），"
                 f"需 --force 重跑")
    if paths["started"].exists():
        started = _load(paths["started"]) or {}
        if _pid_alive(started.get("worker_pid"), started):
            sys.exit(f"[JOBS] FAIL: {args.job_id} 仍在运行，禁止重复启动"
                     f"（kill 或等待完成后再 start）")
        print(f"[JOBS] 提示: {args.job_id} 上次运行异常退出，清理后重启")
        _cleanup_job(args.job_id, started)

    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    with open(paths["log"], "w", encoding="utf-8", errors="replace") as log:
        try:
            proc = subprocess.Popen(
                [PY, str(__file__), "_run-job", args.job_id,
                 "--timeout", str(args.timeout), "--", *args.cmd],
                cwd=ROOT, stdout=log, stderr=log,
                creationflags=_flags(), env=UTF8_ENV,
                start_new_session=(os.name != "nt"),
            )
        except OSError as e:
            sys.exit(f"[JOBS] 错误: 后台进程启动失败: {e}")
        _write(paths["started"], {
            "job_id": args.job_id,
            "worker_pid": proc.pid,
            "target_pid": None,
            "cmd": args.cmd,
            "timeout_minutes": args.timeout,
            "started_at": _now(),
        })
    print(f"[JOBS] OK: {args.job_id} 已后台启动（worker pid {proc.pid}，"
          f"日志 data/jobs/{args.job_id}.log）")


def _state_of(job_id: str) -> str:
    """running / done / crashed"""
    paths = _job_paths(job_id)
    if paths["done"].exists():
        return "done"
    started = _load(paths["started"]) or {}
    if _pid_alive(started.get("worker_pid"), started):
        return "running"
    return "crashed"


def cmd_status(args):
    paths = _job_paths(args.job_id)
    started = _load(paths["started"])
    if not started:
        sys.exit(f"[JOBS] 错误: 任务 {args.job_id} 不存在（未 start 或已 clean）")
    if paths["done"].exists():
        done = _load(paths["done"])
        tag = "timeout" if done.get("timed_out") else ("killed" if done.get("killed") else "exit")
        print(f"[JOBS] {args.job_id}: done（{tag}={done['exit_code']}，"
              f"耗时 {(datetime.fromisoformat(done['finished_at']) - datetime.fromisoformat(done['started_at'])).total_seconds():.0f}s）")
        sys.exit(0)
    if _pid_alive(started.get("worker_pid"), started):
        secs = (datetime.now(timezone.utc) - datetime.fromisoformat(started["started_at"])).total_seconds()
        print(f"[JOBS] {args.job_id}: running（worker pid {started['worker_pid']}，"
              f"已运行 {secs:.0f}s）")
        sys.exit(0)
    print(f"[JOBS] {args.job_id}: crashed（worker 进程不存在且未产出 done）")
    sys.exit(0)


def cmd_list(args):
    started_files = sorted(JOBS_DIR.glob("*.started"))
    if not started_files:
        print("[JOBS] 无后台任务记录（data/jobs/ 为空）")
        sys.exit(0)
    for f in started_files:
        job_id = f.name[: -len(".started")]
        st = _state_of(job_id)
        if st == "done":
            done = _load(_job_paths(job_id)["done"])
            detail = (f"timeout({done['exit_code']})" if done.get("timed_out")
                      else f"killed" if done.get("killed")
                      else f"exit({done['exit_code']})")
        elif st == "running":
            started = _load(f) or {}
            detail = f"pid {started.get('worker_pid')}"
        else:
            detail = "-"
        print(f"  [{st:7}] {job_id}  {detail}")
    sys.exit(0)


def cmd_wait(args):
    paths = _job_paths(args.job_id)
    if not paths["started"].exists():
        sys.exit(f"[JOBS] 错误: 任务 {args.job_id} 不存在")
    deadline = time.monotonic() + args.timeout
    while True:
        if paths["done"].exists():
            done = _load(paths["done"])
            tag = "timeout" if done.get("timed_out") else ("killed" if done.get("killed") else "exit")
            print(f"[JOBS] {args.job_id}: 完成（{tag}={done['exit_code']}）")
            sys.exit(0 if done["exit_code"] == 0 else 1)
        started = _load(paths["started"]) or {}
        if not _pid_alive(started.get("worker_pid"), started):
            print(f"[JOBS] {args.job_id}: crashed（worker 进程不存在）")
            sys.exit(3)
        if time.monotonic() >= deadline:
            print(f"[JOBS] {args.job_id}: 等待超时（{args.timeout}s 仍在运行）")
            sys.exit(2)
        time.sleep(WAIT_POLL_SEC)


def cmd_kill(args):
    paths = _job_paths(args.job_id)
    started = _load(paths["started"])
    if not started:
        sys.exit(f"[JOBS] 错误: 任务 {args.job_id} 不存在")
    for key in ("worker_pid", "target_pid"):
        pid = started.get(key)
        if pid and _pid_alive(pid, started):
            _kill_tree(pid)
    if not paths["done"].exists():
        _write_done(args.job_id, -9, False, True, started.get("started_at", _now()),
                    started.get("cmd", []))
    print(f"[JOBS] OK: {args.job_id} 已终止")
    sys.exit(0)


def cmd_clean(args):
    found = list(JOBS_DIR.glob(f"{args.job_id}.*"))
    if not found:
        sys.exit(f"[JOBS] 提示: {args.job_id} 无记录")
    started = _load(_job_paths(args.job_id)["started"]) or {}
    _cleanup_job(args.job_id, started)
    print(f"[JOBS] OK: {args.job_id} 记录已清理")
    sys.exit(0)


def main():
    _utf8_stdio()
    parser = argparse.ArgumentParser(description="R4 后台任务管理（并行时间线）")
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("start", help="后台启动任务（脱离进程，不阻塞）")
    p.add_argument("job_id")
    p.add_argument("--timeout", type=float, default=0.0,
                   help="超时分钟数（0=不超时），超时自动击杀并标记 failed(timeout)")
    p.add_argument("--force", action="store_true", help="覆盖已完成记录重跑")
    p.add_argument("cmd", nargs="*", help="命令（用 -- 分隔，其后参数不会被解析为选项）")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser("status", help="查询任务状态（running/done/crashed）")
    p.add_argument("job_id")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("list", help="列出全部任务记录")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("wait", help="阻塞等待任务完成")
    p.add_argument("job_id")
    p.add_argument("--timeout", type=int, default=DEFAULT_WAIT_TIMEOUT,
                   help=f"等待秒数上限（默认 {DEFAULT_WAIT_TIMEOUT}）")
    p.set_defaults(fn=cmd_wait)

    p = sub.add_parser("kill", help="终止任务（含子进程树）")
    p.add_argument("job_id")
    p.set_defaults(fn=cmd_kill)

    p = sub.add_parser("clean", help="清理任务记录（允许重新 start）")
    p.add_argument("job_id")
    p.set_defaults(fn=cmd_clean)

    # 内部命令：worker 入口（勿手动调用）
    p = sub.add_parser("_run-job", help=argparse.SUPPRESS)
    p.add_argument("job_id")
    p.add_argument("--timeout", type=float, default=0.0)
    p.add_argument("cmd", nargs="*")
    p.set_defaults(fn=_cmd_run_job)

    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
