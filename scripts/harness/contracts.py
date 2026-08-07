#!/usr/bin/env python3
"""
Step/Phase 合约表 — scripts/harness/contracts.py
=================================================
产品化核心：把"某一步该跑什么命令、前置要求、后置校验、摘要"固化为数据表，
AI 只需 `ustplan.py step <name>` 一次调用，不读文档猜命令。

每个 step 合约:
  phase      所属 checkpoint 阶段（须 begin 后执行）
  title      中文名
  inputs     必填输入 [(relpath, schema)]
  optional   可选输入 [(relpath, schema)]（存在则校验，缺失跳过）
  cmd(ctx)   命令构建（session/track/学分等运行期状态经 ctx 注入，
             消灭 skill 文档里的硬编码 2610）
  outputs    产物 [(relpath, schema)]（执行成功后校验 + 记入 manifest）
  ai_edit    是否需要 AI 人工编辑后 --finalize（step4 review_summary）
  summary    stats.py 汇总节名（unmet/filter/reviews/summary/scores/plans）

job 合约:
  outputs    任务完成后要收录的产物（schema 可空 = 仅记录哈希）

phase 合约:
  done_checks  确认点通过后的硬性检查（返回错误列表）
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.config import load as load_config  # noqa: E402
from harness import decisions, manifest  # noqa: E402

STEP_ORDER = ["step1", "step3", "step4", "step5", "step6"]
PHASE3 = "phase3-course-analysis"

JOBS = {
    "wcq_full": {
        "title": "WCQ 全量抓取",
        "outputs": [("data/courses_{session}.json", "courses"),
                    ("data/cc_courses_{session}.json", "cc_courses")],
    },
    "buckets_pre": {
        "title": "未修 bucket 预计算（无需 cookie）",
        "outputs": [("data/unmet_courses.json", "unmet_courses")],
    },
    "sis_fetch": {
        "title": "SIS 抓取",
        "outputs": [("cache/sis/sis_student_info.json", None),
                    ("cache/sis/sis_course_history.json", None),
                    ("cache/sis/sis_transcript.json", None),
                    ("cache/sis/sis_academic_req.json", None),
                    ("cache/sis/sis_pre_enroll.json", None)],
    },
    "ustspace_pre": {
        "title": "USTspace 评论抓取",
        "outputs": [("data/ustspace_reviews.json", "ustspace_reviews")],
    },
}

STEPS = {
    "step1": {
        "phase": PHASE3,
        "title": "未修课程计算（bucket 化）",
        "inputs": [("data/profile.json", "profile"),
                   ("data/passed_courses.json", "passed_courses")],
        "optional": [("data/pre_enrolled.json", "pre_enroll")],
        "cmd": lambda ctx: [
            str(ctx["root"] / "scripts" / "rank" / "buckets.py"),
            "--profile", str(ctx["root"] / "data" / "profile.json"),
            "--session", ctx["session"],
            "--track", ctx["track"] or "NONE",
            "--passed", str(ctx["root"] / "data" / "passed_courses.json"),
        ] + (["--pre-enrolled", str(ctx["root"] / "data" / "pre_enrolled.json")]
             if ctx["pre_enrolled"] else []),
        "outputs": [("data/unmet_courses.json", "unmet_courses")],
        "summary": "unmet",
        "produced_by": "step1",
    },
    "step3": {
        "phase": PHASE3,
        "title": "候选课程过滤（对今年排期）",
        "inputs": [("data/unmet_courses.json", "unmet_courses"),
                   ("data/passed_courses.json", "passed_courses")],
        "optional": [],
        "cmd": lambda ctx: [
            str(ctx["root"] / "scripts" / "rank" / "filter.py"),
            "--session", ctx["session"],
            "--passed", str(ctx["root"] / "data" / "passed_courses.json"),
        ] + [a for c in (ctx["overrides"] or []) for a in ("--override", c)],
        "outputs": [("data/filter_report.json", "filter_report")],
        "summary": "filter",
        "produced_by": "step3",
    },
    "step4": {
        "phase": PHASE3,
        "title": "USTspace 评论精读（基架 + AI 精读 D 组件）",
        "inputs": [("data/filter_report.json", "filter_report"),
                   ("data/ustspace_reviews.json", "ustspace_reviews")],
        "optional": [],
        "cmd": lambda ctx: [
            str(ctx["root"] / "scripts" / "rank" / "review_summary_build.py"),
            "--session", ctx["session"],
        ],
        "outputs": [("data/review_summary.json", "review_summary")],
        "summary": "summary",
        "ai_edit": True,
        "produced_by": "step4",
    },
    "step5": {
        "phase": PHASE3,
        "title": "Bucket 评分合成（A+B+C+D）",
        "inputs": [("data/filter_report.json", "filter_report"),
                   ("data/ustspace_reviews.json", "ustspace_reviews")],
        "optional": [("data/review_summary.json", "review_summary")],
        "cmd": lambda ctx: [
            str(ctx["root"] / "scripts" / "rank" / "bucket_score.py"),
            "--session", ctx["session"],
        ],
        "outputs": [("data/course_scores.json", "course_scores")],
        "summary": "scores",
        "produced_by": "step5",
    },
    "step6": {
        "phase": PHASE3,
        "title": "课程表编排（目标学分驱动）",
        "inputs": [("data/course_scores.json", "course_scores")],
        "optional": [("data/pre_enrolled.json", "pre_enroll")],
        "cmd": lambda ctx: [
            str(ctx["root"] / "scripts" / "rank" / "planner.py"),
            "--scores", str(ctx["root"] / "data" / "course_scores.json"),
            "--session", ctx["session"],
            "--passed", str(ctx["root"] / "data" / "passed_courses.json"),
            "--target-credits", str(ctx["target_credits"]),
        ] + ([f"--pre-enrolled", str(ctx["root"] / "data" / "pre_enrolled.json")]
             if ctx["pre_enrolled"] else [])
          + (["--must-take", *ctx["must_take"]] if ctx["must_take"] else [])
          + (["--exclude", *ctx["exclude"]] if ctx["exclude"] else [])
          + ([f"--credits-override",
              *[f"{k}={v}" for k, v in ctx["credits_overrides"].items()]]
             if ctx["credits_overrides"] else []),
        "outputs": [("output/timetable_plan.json", "timetable_plan")],
        "summary": "plans",
        "produced_by": "step6",
    },
}

PHASES = {
    "phase1-input": {
        "title": "输入准备（凭证 + major + track + 学期）",
        "done_checks": lambda ctx: _phase1_checks(ctx),
    },
    "phase2-profile": {
        "title": "用户画像（SIS 权威 + 确认）",
        "done_checks": lambda ctx: _phase2_checks(ctx),
    },
    "phase3-course-analysis": {
        "title": "课程分析（step1→step3→step4→step5→step6 + P5）",
        "done_checks": lambda ctx: _phase3_checks(ctx),
    },
    "phase4-report": {
        "title": "总结报告",
        "done_checks": lambda ctx: _phase4_checks(ctx),
    },
    "phase4.5-must-take": {
        "title": "必选课询问（可选）",
        "done_checks": lambda ctx: [],
    },
}


def _checkpoint(root_p: Path) -> dict:
    p = root_p / "data" / "checkpoint.json"
    if not p.exists():
        return {"completed": [], "current": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"completed": [], "current": None}


def ctx_for(root=None):
    """运行期上下文：config + manifest + decisions + checkpoint 合并解析"""
    root_p = Path(root) if root else Path(__file__).resolve().parents[2]
    cfg = load_config(root=root_p)
    m = manifest.load(root_p) or {}
    d = decisions.load(root_p)
    p1 = d.get("P1") or {}
    p3 = d.get("P3") or {}
    p4 = d.get("P4") or {}
    p5 = d.get("P5") or {}
    p45 = d.get("phase4.5") or {}
    pre = (root_p / "data" / "pre_enrolled.json").exists()
    return {
        "root": root_p,
        "session": str(m.get("session") or p1.get("session") or cfg.get("session")
                       or "latest"),
        "admission_year": m.get("admission_year") or cfg.get("admission_year"),
        "track": str(p1.get("track")) if p1.get("track") else None,
        "overrides": p4.get("overrides") or [],
        "target_credits": p3.get("target_credits") or
                          cfg["defaults"]["target_credits"],
        "must_take": (p45.get("must_take") or []) + (p5.get("must_take") or []),
        "exclude": p5.get("exclude") or [],
        "credits_overrides": p5.get("credits_overrides") or {},
        "chosen_plan": p5.get("chosen_plan"),
        "pre_enrolled": pre,
        "cfg": cfg,
        "checkpoint": _checkpoint(root_p),
    }


def _phase1_checks(ctx) -> list:
    errs = []
    d = decisions.load(ctx["root"])
    p1 = d.get("P1") or {}
    # P1 程序字段三状态：缺失=空置（不通过）；'NA'=明确无；否则=课程代码。
    # 必须显式填写 major/minor/extended_major 三个字段（防漏读扩展主修/副修）。
    for f in ("major", "minor", "extended_major"):
        v = str(p1.get(f) or "").strip()
        if not v:
            errs.append(f"P1 未确认：缺少 {f}（三状态：填入代码 / NA=没有，空置不通过）")
    if not p1.get("session"):
        errs.append("P1 未确认：缺少目标学期 session")
    return errs


def _phase2_checks(ctx) -> list:
    errs = []
    d = decisions.load(ctx["root"])
    p2 = d.get("P2") or {}
    if not p2.get("confirmed"):
        errs.append("P2 未确认：画像未获用户确认")
    for rel, schema in (("data/profile.json", "profile"),
                        ("data/passed_courses.json", "passed_courses")):
        errs += manifest.validate_artifact(ctx["root"], rel, schema)
    return errs


def _phase3_checks(ctx) -> list:
    """phase3 完成条件（确认点已精简为 P3 一次）：
    step1-6 全部 done + P3（未修确认 + 目标学分）已记录。
    P4/P5 不再强制（过滤结果随 P3 展示；方案展示后用户可要求修改）。"""
    errs = []
    d = decisions.load(ctx["root"])
    p3 = d.get("P3") or {}
    if not p3.get("confirmed"):
        errs.append("P3 未确认：未修清单 + 目标学分未获用户确认")
    m = manifest.load(ctx["root"]) or {}
    for step in STEP_ORDER:
        if (m.get("steps") or {}).get(step, {}).get("status") != "done":
            errs.append(f"{step} 未完成（{STEPS[step]['title']}）")
    return errs


def _phase4_checks(ctx) -> list:
    errs = []
    report = ctx["root"] / "output" / "final_report.md"
    if not report.exists():
        errs.append("缺少 output/final_report.md（先 ustplan report）")
    errs += manifest.validate_artifact(ctx["root"], "output/timetable_plan.json",
                                       "timetable_plan")
    return errs


def step_precheck(ctx, step: str, force: bool = False) -> list:
    """前置检查：阶段状态 + 输入存在且 schema 合法 + step 顺序"""
    spec = STEPS[step]
    errs = []
    if force:
        return errs
    cp = ctx["checkpoint"] or load_checkpoint()
    if cp.get("current") != spec["phase"]:
        errs.append(f"{step} 要求当前阶段为 {spec['phase']}（当前 "
                    f"current={cp.get('current')}）；先 ustplan phase begin "
                    f"{spec['phase']}")
    m = manifest.load(ctx["root"]) or {}
    idx = STEP_ORDER.index(step)
    done = {s for s, v in (m.get("steps") or {}).items()
            if isinstance(v, dict) and v.get("status") == "done"}
    missing_prev = [s for s in STEP_ORDER[:idx] if s not in done]
    if missing_prev:
        errs.append(f"{step} 前置步骤未完成: {', '.join(missing_prev)}")
    for rel, schema in spec["inputs"]:
        errs += manifest.validate_artifact(ctx["root"], rel, schema)
    for rel, schema in spec["optional"]:
        if (ctx["root"] / rel).exists():
            errs += manifest.validate_artifact(ctx["root"], rel, schema)
    return errs


def step_postcheck(ctx, step: str) -> list:
    """后置检查：产物存在 + schema 合法"""
    spec = STEPS[step]
    errs = []
    for rel, schema in spec["outputs"]:
        errs += manifest.validate_artifact(ctx["root"], rel, schema)
    return errs


def phase_begin_checks(ctx, phase: str) -> list:
    """begin 前的数据检查（checkpoint 顺序由 checkpoint.py 保证）"""
    errs = []
    if phase == PHASE3:
        for rel, schema in (("data/profile.json", "profile"),
                            ("data/passed_courses.json", "passed_courses")):
            errs += manifest.validate_artifact(ctx["root"], rel, schema)
    return errs


def next_step(ctx) -> str:
    """根据 manifest 与 checkpoint 推断下一步 step（None = 全部完成）"""
    cp = ctx["checkpoint"] or load_checkpoint()
    if cp.get("current") != PHASE3:
        return None
    m = manifest.load(ctx["root"]) or {}
    done = {s for s, v in (m.get("steps") or {}).items()
            if isinstance(v, dict) and v.get("status") == "done"}
    for step in STEP_ORDER:
        if step not in done:
            return step
    return None
