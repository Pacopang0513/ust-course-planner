#!/usr/bin/env python3
"""
ustplan — UST 课表统一入口
==========================
产品化 CLI：把 checkpoint / jobs / step 合约 / manifest / 报告渲染打包成一个命令面。
AI 只调用本入口，不再直接拼底层脚本命令。

命令一览:
  init                          初始化运行目录（幂等）
  doctor                        环境预检
  start [--session X] [--force] 开始新一轮运行（run_id + 后台 wcq_full）
  status                        运行总览（阶段/任务/产物/决策/下一步）
  resume                        下一步建议（断点续跑指引）
  step <name> [--finalize] [--force]  执行 step 合约（step1/3/4/5/6）
  phase begin|done <phase>      阶段推进（含数据检查）
  job start|status|wait|clean <job-id> [-- cmd...]   后台任务（并行时间线）
  plan [--target N] [--must-take C...] [--exclude C...]  step6 快捷重排
  report [--plan plan-N]        渲染 final_report.md（机械段落）
  grid [--plan N] [--html]      课程表周历（终端 ASCII / HTML 导出）
  decisions set <KEY> '<json>'  记录用户决策（审计）
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from harness import contracts, decisions, manifest  # noqa: E402
from harness.config import load as load_config  # noqa: E402
from harness.config import previous_sessions, semester_of_session  # noqa: E402

PY = sys.executable
JOBS_PY = ROOT / "scripts" / "harness" / "jobs.py"
CHECKPOINT_PY = ROOT / "scripts" / "harness" / "checkpoint.py"
UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run(args: list, cwd=ROOT, capture=True):
    return subprocess.run([PY, *args], cwd=cwd, capture_output=capture,
                          env=UTF8_ENV, text=True, encoding="utf-8",
                          errors="replace")


def _history_subjects_file(ctx: dict) -> Path:
    """step5 产物 course_scores.json 的候选课程 → subject 名单
    （data/history_subjects.json，wcq_history job 的 --subjects-file 输入）。"""
    p = Path(str(ctx["root"])) / "data" / "history_subjects.json"
    subjects = set()
    scores_path = Path(str(ctx["root"])) / "data" / "course_scores.json"
    if scores_path.exists():
        try:
            scores = json.loads(scores_path.read_text(encoding="utf-8"))
            for c in list(scores.get("courses", [])) + \
                    list(scores.get("ranked_out", [])):
                code = str(c.get("code", "")).split()
                if code and code[0].isalpha():
                    subjects.add(code[0].upper())
        except (OSError, json.JSONDecodeError):
            pass
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(subjects), ensure_ascii=False), encoding="utf-8")
    return p


def _job_default_cmd(ctx, job_id: str) -> list:
    """预定义 job 命令（覆盖可从 CLI 传 -- cmd 自定义）"""
    c = ctx
    cmds = {
        "wcq_full": [str(ROOT / "scripts" / "wcq" / "crawler.py"),
                     "--session", c["session"] or "latest"],
        "buckets_pre": [str(ROOT / "scripts" / "rank" / "buckets.py"),
                        "--profile", str(ROOT / "data" / "profile.json"),
                        "--session", c["session"] or "latest",
                        "--track", c["track"] or "NONE",
                        "--passed", str(ROOT / "data" / "passed_courses.json")],
        "sis_fetch": [str(ROOT / "scripts" / "sis" / "parser.py"), "--fetch",
                      "--cookie-file", str(ROOT / "credentials" / "cookies.txt")],
        "ustspace_pre": [str(ROOT / "scripts" / "ustspace" / "crawler.py"),
                         "--codes-file", str(ROOT / "data" / "filter_report.json"),
                         "--cookie-file", str(ROOT / "credentials" / "cookies.txt")],
        "wcq_history": [str(ROOT / "scripts" / "wcq" / "history_fetch.py"),
                        "--session", c["session"] or "latest",
                        "--subjects-file", str(_history_subjects_file(ctx))],
    }
    cmd = cmds.get(job_id) or []
    # sis_fetch：已知真实 session 时注入（Pre-Enroll 页 STRM 必须为有效 term code，
    # 空 STRM 返回 JS 空壳无网格数据——2026-08 实测）
    if job_id == "sis_fetch" and c.get("session") and \
            re.fullmatch(r"\d{4}", str(c["session"])):
        cmd = cmd + ["--session", str(c["session"])]
    # wcq_full：入学年份已知时注入 --admission-year，顺带抓 Common Core 池
    # （否则只抓 subject 页，cc_courses 缺失需人工补跑）
    if job_id == "wcq_full":
        ay = c.get("admission_year") or manifest.resolve_admission_year(ctx["root"])
        if ay:
            cmd = cmd + ["--admission-year", ay]
    return cmd


def _session_term_label(session: str) -> str:
    """2610 → '2026-27 Fall'（用于与 SIS pre-enroll 页 term 比对）"""
    s = str(session or "")
    if not re.fullmatch(r"\d{4}", s):
        return ""
    y = int(s[:2]) + 2000
    sem = semester_of_session(s)
    return f"{y}-{str(y + 1)[2:]} {sem}" if sem else ""


def _warn_pre_enroll_term_mismatch(session: str):
    """预选课学期校验：SIS 页面 term 由会话决定（URL STRM 不切学期），
    非选课季抓到的 pre_enrolled 可能是旧学期数据 → 醒目 WARN 供 P2 核对。"""
    pe_path = ROOT / "data" / "pre_enrolled.json"
    if not pe_path.exists():
        return
    try:
        pe = json.loads(pe_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return
    term = str(pe.get("term") or "").strip()
    want = _session_term_label(session)
    if term and want and term != want:
        print(f"  ! 预选课学期 [{term}] ≠ 目标学期 [{want}]：SIS 页面显示的是"
              f"会话默认学期，pre_enrolled 可能非目标学期数据。\n"
              f"    P2 核对时说明：若页面 term 非目标学期，预选课不视为固定选课"
              f"（评分 +{_pre_enroll_boost_pct()}% 与 drop 建议可能不适用）。")


def _pre_enroll_boost_pct() -> str:
    try:
        cfg = load_config()
        return f"{float(cfg['scoring']['pre_enroll_boost']) * 100:.0f}"
    except Exception:
        return "20"


def _adopt_job_outputs(ctx, job_id: str):
    """job 完成后收录产物到 manifest；wcq_full 顺带解析 session"""
    # wcq_history：产物按前两个学期展开（data/courses_{prev}.json）
    if job_id == "wcq_history":
        prevs = previous_sessions(ctx.get("session") or "")
        for p in prevs:
            ok, errs = manifest.record_artifact(ctx["root"],
                                                f"data/courses_{p}.json",
                                                "courses", job_id)
            if not ok:
                print(f"  ! 产物 data/courses_{p}.json 未收录: {'; '.join(errs)}")
        return
    spec = contracts.JOBS.get(job_id, {})
    for rel_tpl, schema in spec.get("outputs", []):
        rel = rel_tpl.format(session=ctx["session"] or "")
        ok, errs = manifest.record_artifact(ctx["root"], rel, schema, job_id)
        if not ok:
            print(f"  ! 产物 {rel} 未收录: {'; '.join(errs)}")
    if job_id == "wcq_full":
        newest = _newest_session(ctx["root"])
        if newest:
            m = manifest.load(ctx["root"])
            # 检测到真实数字 session（如 2610）即更新：'latest' 只是配置占位，
            # 首次空跑可能产出 courses_latest.json（0 门课），不得让其锁死 session
            cur = m.get("session")
            if not cur or not re.fullmatch(r"\d{4}", str(cur)):
                m["session"] = newest
                m["updated_at"] = _now()
                _write_manifest(ctx["root"], m)
                print(f"  -> 检测到 session: {newest}（已写入 manifest，"
                      f"P1 请与用户确认）")
            for rel, schema in spec.get("outputs", []):
                manifest.record_artifact(ctx["root"],
                                         rel.format(session=newest),
                                         schema, job_id)
    if job_id == "sis_fetch":
        _warn_pre_enroll_term_mismatch(ctx.get("session"))
    if job_id == "ustspace_pre" or job_id == "buckets_pre":
        pass


def _newest_session(root: Path):
    """data/ 下 courses_*.json 的数字 session（2610 式）按文件名取最大；
    无数字 session 时退回 mtime 最新（兼容旧产物名 courses_latest.json）。"""
    files = sorted((root / "data").glob("courses_*.json"),
                   key=lambda p: p.stem[len("courses_"):] if
                   p.stem[len("courses_"):].isdigit() else "0")
    numeric = [p.stem[len("courses_"):] for p in files
               if p.stem[len("courses_"):].isdigit()]
    if numeric:
        return max(numeric, key=int)
    if files:
        return files[-1].stem[len("courses_"):]
    return None


def _write_manifest(root: Path, m: dict):
    (root / "data" / "manifest.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 命令实现 ──────────────────────────────────────────────

def cmd_init(args):
    for d in ("data", "output", "cache", "credentials", "user", "config"):
        (ROOT / d).mkdir(parents=True, exist_ok=True)
    print("[ustplan] OK: 运行目录就绪（data/output/cache/credentials/user）")


def cmd_doctor(args):
    r = _run([str(ROOT / "scripts" / "harness" / "doctor.py")] +
             (["--cookies-only"] if args.cookies_only else []))
    sys.stdout.write(r.stdout)
    sys.exit(r.returncode)


def cmd_start(args):
    m = manifest.load()
    if m and m.get("started_at") and not args.force:
        print(f"[ustplan] 已存在运行（run_id={m['run_id']}，{m['started_at']}）。"
              f"如需重开: ustplan start --force")
        sys.exit(1)
    m = manifest.init(session=args.session,
                      admission_year=args.admission_year)
    print(f"[ustplan] 新运行开始: run_id={m['run_id']}")
    ctx = contracts.ctx_for()
    cfg = load_config()
    timeout = cfg.get("jobs", {}).get("wcq_full", {}).get("timeout_minutes", 25)
    cmd = _job_default_cmd(ctx, "wcq_full")
    r = _run([str(JOBS_PY), "start", "wcq_full", "--timeout", str(timeout),
              "--force", "--"] + cmd)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.exit(r.returncode)
    # 自动进入 phase1-input（checkpoint 链起点，避免 AI 忘记 begin）
    r2 = _run([str(CHECKPOINT_PY), "begin", "phase1-input"])
    sys.stdout.write(r2.stdout)
    print("\n[ustplan] 下一步: 向用户收集 P1（两个登录令牌 + major + track + 学期确认）")


def cmd_status(args):
    m = manifest.load()
    cp = {}
    cp_p = ROOT / "data" / "checkpoint.json"
    if cp_p.exists():
        cp = json.loads(cp_p.read_text(encoding="utf-8"))
    d = decisions.load()
    cfg = load_config()

    if not m:
        print("[ustplan] 尚无运行记录。开始新运行: ustplan start")
        sys.exit(0)

    print(f"[ustplan] run {m['run_id']} | session={m.get('session') or '?'} "
          f"| 入学={m.get('admission_year') or '?'} | 开始 {m.get('started_at')}")
    print(f"\n阶段（checkpoint）:")
    for phase in ("phase1-input", "phase2-profile", "phase3-course-analysis",
                  "phase4-report", "phase4.5-must-take"):
        if phase in cp.get("completed", []):
            mark, tag = "X", ""
        elif phase == cp.get("current"):
            mark, tag = "->", "（进行中）"
        else:
            mark, tag = " ", ""
        print(f"  [{mark}] {phase}{tag}")
    steps = m.get("steps") or {}
    if steps:
        print("\nstep 进度:")
        for s in contracts.STEP_ORDER:
            st = steps.get(s, {}).get("status", " ")
            print(f"  [{st}] {s} {contracts.STEPS[s]['title']}")

    print("\n后台任务:")
    jobs_dir = ROOT / "data" / "jobs"
    names = sorted(p.stem for p in jobs_dir.glob("*.started")) if jobs_dir.is_dir() else []
    if not names:
        print("  （无）")
    for jid in names:
        r = _run([str(JOBS_PY), "status", jid], capture=True)
        line = r.stdout.strip().splitlines()
        print("  " + (line[0] if line else f"{jid}: ?"))

    arts = m.get("artifacts") or {}
    if arts:
        print("\n产物:")
        for rel, info in sorted(arts.items()):
            ver = f"v{info['schema_version']}" if info.get("schema_version") else "-"
            print(f"  {rel:44} ✓{ver:4} by {info.get('produced_by', '?')}")

    print(f"\n决策: {decisions.track()}")
    # 凭据有效期提醒（TTL，config → credentials.ttl_hours；警告级别）
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from credentials import ttl_warning
        warn = ttl_warning(float((cfg.get("credentials") or {}).get("ttl_hours", 12)))
        if warn:
            print(f"  ~ {warn}（运行 `python3 scripts/cookies_setup.py --check` 查看，"
                  f"`--listen` 一键刷新）")
    except Exception:  # noqa: BLE001  TTL 提醒为附加信息，失败不影响
        pass
    print("\n下一步: " + resume_text(m, cp, d, cfg))


def resume_text(m: dict, cp: dict, d: dict, cfg: dict) -> str:
    if cp.get("current") == "phase1-input":
        return "P1: 收集两个登录凭证 + major/minor/extended_major（三状态：代码/NA）+ " \
               "track + 目标学期，确认后 " \
               "`ustplan decisions set P1 '{...}'` → `ustplan phase done phase1-input`"
    if cp.get("current") == "phase2-profile":
        return "P2: 画像确认后 `ustplan decisions set P2 '{...}'` → " \
               "`ustplan phase done phase2-profile`"
    if cp.get("current") == "phase3-course-analysis":
        step = contracts.next_step(contracts.ctx_for())
        if step:
            return (f"执行 {step}（{contracts.STEPS[step]['title']}）: "
                    f"`ustplan step {step}`"
                    + ("；AI 精读后 `ustplan step step4 --finalize`" if step == "step4" else "")
                    + " → 确认点 P" + {"step1": "3", "step3": "3", "step4": "3→5",
                                       "step5": "3→5", "step6": "3→5"}[step])
        return "步骤全部完成：展示方案（P5 弱化为展示，用户可要求修改）→ " \
               "`ustplan phase done phase3-course-analysis`"
    if cp.get("current") == "phase4-report":
        return "`ustplan report [--plan plan-N]` 渲染报告，AI 补口碑摘要/建议后 " \
               "`ustplan phase done phase4-report`"
    if cp.get("current") == "phase4.5-must-take":
        return "询问必选课；有则 `ustplan plan --must-take ...`；" \
               "完成后 `ustplan phase done phase4.5-must-take`"
    return "无进行中阶段：`ustplan start` 开始新运行"


def cmd_resume(args):
    m = manifest.load()
    cp = {}
    cp_p = ROOT / "data" / "checkpoint.json"
    if cp_p.exists():
        cp = json.loads(cp_p.read_text(encoding="utf-8"))
    d = decisions.load()
    cfg = load_config()
    if not m:
        print("[ustplan] 尚无运行记录。开始新运行: ustplan start")
        sys.exit(0)
    print(resume_text(m, cp, d, cfg))


def cmd_step(args):
    step = args.step
    if step not in contracts.STEPS:
        sys.exit(f"[ustplan] 未知 step '{step}'，可选: {', '.join(contracts.STEPS)}")
    ctx = contracts.ctx_for()
    spec = contracts.STEPS[step]

    if not args.finalize:
        errs = contracts.step_precheck(ctx, step, force=args.force)
        if errs:
            print(f"[ustplan] step {step} 前置检查失败:")
            for e in errs:
                print(f"  ! {e}")
            sys.exit(1)

    print(f"[ustplan] step {step}: {spec['title']}")
    cmd = spec["cmd"](ctx)
    print("$ python " + " ".join(cmd))
    r = _run(cmd)
    if r.returncode != 0:
        manifest.step_failed(ROOT, step)
        sys.exit(f"[ustplan] step {step} 执行失败（exit {r.returncode}）")

    errs = contracts.step_postcheck(ctx, step)
    if errs:
        manifest.step_failed(ROOT, step)
        print("[ustplan] step 后置校验失败:")
        for e in errs:
            print(f"  ! {e}")
        sys.exit(1)

    for rel, schema in spec["outputs"]:
        ok, e2 = manifest.record_artifact(ROOT, rel, schema, spec["produced_by"])
        if not ok:
            print(f"  ! 产物 {rel} 未收录: {'; '.join(e2)}")

    if spec.get("ai_edit") and not args.finalize:
        print(f"\n[ustplan] 基架已生成（{spec['outputs'][0][0]}）。"
              f"AI 精读 USTspace 评论填写 d_rating 等字段后，"
              f"运行 `ustplan step {step} --finalize` 完成本步")
        sys.exit(0)

    manifest.step_done(ROOT, step)
    _print_summary(step, spec, ctx)
    print(f"\n[ustplan] step {step} 完成，下一步: {contracts.next_step(ctx) or 'P5 确认'}")


def _print_summary(step: str, spec: dict, ctx: dict):
    if not spec.get("summary"):
        return
    key = spec["summary"]
    rel = spec["outputs"][0][0]
    p = ROOT / rel
    if not p.exists():
        return
    data = json.loads(p.read_text(encoding="utf-8"))
    import importlib
    stats = importlib.import_module("report.stats")
    fn = {"unmet": stats.stats_unmet, "filter": stats.stats_filter,
          "summary": stats.stats_summary, "scores": lambda d: stats.stats_scores(d, 15),
          "plans": stats.stats_plans}.get(key)
    if fn:
        print("\n===== " + spec["title"] + " 摘要 =====")
        print(fn(data))


def cmd_phase(args):
    phase = args.phase
    if phase not in contracts.PHASES:
        sys.exit(f"[ustplan] 未知阶段 '{phase}'，可选: {', '.join(contracts.PHASES)}")
    if args.action == "begin":
        ctx = contracts.ctx_for()
        errs = contracts.phase_begin_checks(ctx, phase)
        if errs:
            print("[ustplan] phase begin 数据检查失败:")
            for e in errs:
                print(f"  ! {e}")
            sys.exit(1)
        r = _run([str(CHECKPOINT_PY), "begin", phase])
        sys.stdout.write(r.stdout)
        sys.exit(r.returncode)
    # done
    ctx = contracts.ctx_for()
    errs = contracts.PHASES[phase]["done_checks"](ctx)
    if errs:
        print(f"[ustplan] {phase} 完成条件未满足:")
        for e in errs:
            print(f"  ! {e}")
        sys.exit(1)
    r = _run([str(CHECKPOINT_PY), "done", phase])
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.exit(r.returncode)
    manifest.phase_done(ROOT, phase)
    print(f"[ustplan] 已记录 {phase} 完成（manifest）")
    if phase == "phase2-profile":
        print("       下一步: checkpoint begin phase3-course-analysis → "
              "ustplan step step1 → ...")


def cmd_job(args):
    ctx = contracts.ctx_for()
    jid = args.job_id
    cfg = load_config()
    timeout = (cfg.get("jobs", {}).get(jid, {}) or {}).get("timeout_minutes", 15)

    if args.action == "start":
        cmd = args.cmd or _job_default_cmd(ctx, jid)
        if not cmd:
            sys.exit(f"[ustplan] 未预定义 {jid} 命令，请用 `-- cmd...` 指定")
        r = _run([str(JOBS_PY), "start", jid, "--timeout", str(timeout)]
                 + (["--force"] if args.force else []) + ["--"] + cmd)
        sys.stdout.write(r.stdout)
        sys.exit(r.returncode)
    if args.action in ("status", "wait"):
        r = _run([str(JOBS_PY), args.action, jid] +
                 (["--timeout", str(args.timeout)] if args.action == "wait" else []),
                 capture=True)
        line = r.stdout.strip().splitlines()
        if line:
            print(line[0])
        # status 输出 "done（exit=0）"；wait 输出 "完成（exit=0）"——统一按
        # 任务成功结束判断（exit 0），完成即收录产物到 manifest
        done_line = line[0] if line else ""
        finished = r.returncode == 0 and ("done" in done_line
                                          or "完成" in done_line)
        if finished:
            _adopt_job_outputs(ctx, jid)
        elif args.action == "wait":
            sys.stdout.write(r.stdout)
            sys.stderr.write(r.stderr)
        sys.exit(r.returncode)
    if args.action == "clean":
        r = _run([str(JOBS_PY), "clean", jid])
        sys.stdout.write(r.stdout)
        sys.exit(r.returncode)


def cmd_plan(args):
    """step6 快捷重排（must-take / exclude / target 覆盖），含决策记录"""
    if args.must_take:
        decisions.set_decision(ROOT, "phase4.5",
                               {"must_take": args.must_take})
    if args.exclude:
        d = decisions.load()
        p5 = d.get("P5") or {}
        p5["exclude"] = args.exclude
        decisions.set_decision(ROOT, "P5", p5)
    if args.target:
        d = decisions.load()
        p3 = d.get("P3") or {}
        p3["target_credits"] = args.target
        decisions.set_decision(ROOT, "P3", p3)
    ns = argparse.Namespace(step="step6", finalize=False, force=args.force)
    cmd_step(ns)


def cmd_report(args):
    r = _run([str(ROOT / "scripts" / "report" / "render.py"),
              "--plan", args.plan or "plan-1",
              "--session", manifest.resolve_session() or ""])
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    sys.exit(r.returncode)


def cmd_grid(args):
    r = _run([str(ROOT / "scripts" / "report" / "render_grid.py"),
              "--plan", args.plan or "1"]
             + (["--html"] if args.html else []))
    sys.stdout.write(r.stdout)
    sys.exit(r.returncode)


def cmd_decisions(args):
    if args.action == "set":
        if args.value_file:
            try:
                # utf-8-sig：兼容 PowerShell 5.1 写出的带 BOM UTF-8 文件
                value = json.loads(
                    Path(args.value_file).read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError) as e:
                sys.exit(f"[ustplan] decisions set: 无法读取 {args.value_file}（{e}）")
        else:
            value = _parse_decision_value(args.key, args.value)
        decisions.set_decision(ROOT, args.key, value)
        print(f"[ustplan] 决策已记录: {args.key} = {json.dumps(value, ensure_ascii=False)}")
    else:
        d = decisions.load()
        print(json.dumps(d, ensure_ascii=False, indent=2))


def _auto(v: str):
    """bool/null/数字自动转换，其余保留字符串。
    session 等 4 位数字字符串保持字符串（decisions schema 要求 string）；"""
    if v in ("true", "True"):
        return True
    if v in ("false", "False"):
        return False
    if v in ("null", "None"):
        return None
    try:
        if "." in v or "e" in v.lower():
            return float(v)
        return int(v)
    except ValueError:
        return v


def _parse_decision_value(key: str, value) -> dict:
    """值解析：接受 JSON 字符串或 k=v 键值对（兼容 PowerShell 引号剥离）。
    JSON 形式必须整体以 { 开头；否则按 'k=v k=v' 组装为对象。
    布尔/数字自动转换（true/false/null/数字），其余保留字符串。
    schema 类型约束：session 保持字符串；overrides/must_take/exclude 等数组
    字段支持 JSON 数组（'[]'）或逗号分隔字符串。"""
    if value is None:
        return {}
    joined = " ".join(value)
    if joined.lstrip().startswith("{"):
        try:
            return json.loads(joined)
        except json.JSONDecodeError as e:
            sys.exit(f"[ustplan] decisions set: JSON 解析失败（{e}）")
    obj = {}
    last_key = None
    for tok in joined.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            last_key = k
            obj[k] = v
        elif last_key is not None:
            obj[last_key] = obj[last_key] + " " + tok
        else:
            sys.exit(f"[ustplan] decisions set: 无法解析 '{tok}'（需 key=value 或 JSON）")
    return {k: _typed(k, v) for k, v in obj.items()}


ARRAY_KEYS = {"overrides", "must_take", "exclude", "corrections", "minor",
              "additional_major", "extended_major"}
STRING_KEYS = {"session", "major", "track", "semester", "admission_year",
               "chosen_plan"}


def _typed(key: str, v: str):
    """按 decisions schema 语义类型化：数组键解析 JSON 数组/逗号分隔；
    session 等字符串键保持字符串（禁止 int('2610')）；其余走 _auto。"""
    if key in ARRAY_KEYS:
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                pass
        return [x.strip() for x in v.split(",") if x.strip()]
    if key in STRING_KEYS:
        return v
    return _auto(v)


def main():
    ap = argparse.ArgumentParser(description="ustplan — UST 课表统一入口")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)

    p = sub.add_parser("doctor", help="环境预检")
    p.add_argument("--cookies-only", action="store_true")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("start", help="开始新一轮运行")
    p.add_argument("--session", default=None, help="目标学期（默认 config/latest）")
    p.add_argument("--admission-year", default=None)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_start)

    sub.add_parser("status", help="运行总览").set_defaults(fn=cmd_status)
    sub.add_parser("resume", help="下一步建议").set_defaults(fn=cmd_resume)

    p = sub.add_parser("step", help="执行 step 合约")
    p.add_argument("step", choices=list(contracts.STEPS))
    p.add_argument("--finalize", action="store_true", help="AI 编辑后完成本步（step4）")
    p.add_argument("--force", action="store_true", help="跳过前置检查")
    p.set_defaults(fn=cmd_step)

    p = sub.add_parser("phase", help="阶段推进")
    p.add_argument("action", choices=["begin", "done"])
    p.add_argument("phase", choices=list(contracts.PHASES))
    p.set_defaults(fn=cmd_phase)

    p = sub.add_parser("job", help="后台任务（并行时间线）")
    p.add_argument("action", choices=["start", "status", "wait", "clean"])
    p.add_argument("job_id")
    p.add_argument("--timeout", type=int, default=1800,
                   help="wait 等待秒数（默认 1800）")
    p.add_argument("--force", action="store_true", help="start 覆盖重跑")
    p.add_argument("cmd", nargs="*", help="自定义命令（-- 后；缺省用预定义）")
    p.set_defaults(fn=cmd_job)

    p = sub.add_parser("plan", help="step6 快捷重排（must-take/exclude/target）")
    p.add_argument("--target", type=float, default=None, help="目标学分覆盖")
    p.add_argument("--must-take", nargs="+", default=[], help="硬插课程")
    p.add_argument("--exclude", nargs="+", default=[], help="排除课程")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("report", help="渲染 final_report.md")
    p.add_argument("--plan", default="plan-1", help="选定方案（P5）")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("grid", help="课程表周历")
    p.add_argument("--plan", default="1", help="方案序号（默认 1）")
    p.add_argument("--html", action="store_true", help="导出 HTML 文件")
    p.set_defaults(fn=cmd_grid)

    p = sub.add_parser("decisions", help="决策日志")
    p.add_argument("action", choices=["set", "show"])
    p.add_argument("key", nargs="?", default=None)
    p.add_argument("value", nargs="*", default=None,
                   help="值：JSON 字符串（{ 开头）或 k=v k=v 键值对（兼容 PowerShell）")
    p.add_argument("--value-file", default=None,
                   help="从 JSON 文件读取值（绕过 shell 引号；如 --value-file tmp_p1.json）")
    p.set_defaults(fn=cmd_decisions)

    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    args.fn(args)


if __name__ == "__main__":
    main()
