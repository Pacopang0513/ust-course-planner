#!/usr/bin/env python3
"""
统一配置 — scripts/harness/config.py
====================================
集中管理全部产品参数（config/ustplan.json，schema: templates/schemas/config.schema.json）。
脚本与 CLI 统一经 load() 读取；config 文件缺失时使用内置默认（与既有脚本行为一致）。

用法:
  from harness.config import load
  cfg = load()                # 项目根 config/ustplan.json（缺失 → 内置默认）
  cfg = load(path="x.json")   # 显式指定配置文件
  cfg = load(root=tmp)        # 指定项目根（隔离副本测试）
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "ustplan.json"

DEFAULTS = {
    "session": "latest",
    "admission_year": None,
    "defaults": {
        "target_credits": 15,
        "plans": 3,
        "top_per_bucket": 3,
        "credits_min": 12,
        "credits_max": 18,
        "candidate_pool": 50,
        "graduation_credits": 120,
        "unmet_credit_mode": "median",
    },
    "scoring": {
        "baseline": 2.5,
        "weights": {"a": 30.0, "b": 20.0, "c": 25.0, "d": 25.0},
        "professor": {"teaching": 0.3, "grading": 0.3, "content": 0.2, "workload": 0.2},
        "heat_tiers": [
            {"min_reviews": 80, "points": 25.0},
            {"min_reviews": 60, "points": 20.0},
            {"min_reviews": 40, "points": 15.0},
            {"min_reviews": 20, "points": 10.0},
            {"min_reviews": 5, "points": 5.0},
        ],
        "min_reviews_for_score": 5,
        "weight_penalty_per_missing": 0.2,
        "level_bonus": {"1": 5, "2": 3, "3": 1},
    },
    "history": {
        "threshold": 0.5,
        "penalty_pct": 10,
    },
    "jobs": {
        "wcq_full": {"timeout_minutes": 25},
        "buckets_pre": {"timeout_minutes": 5},
        "sis_fetch": {"timeout_minutes": 10},
        "ustspace_pre": {"timeout_minutes": 15},
        "wcq_history": {"timeout_minutes": 15},
    },
    "credentials": {
        "ttl_hours": 12,
    },
    "semesters": {"Fall": 10, "Winter": 20, "Spring": 30, "Summer": 40},
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path=None, root=None) -> dict:
    """加载配置：config/ustplan.json（可缺省）叠加内置默认，返回合并结果。"""
    root_p = Path(root) if root else ROOT
    p = Path(path) if path else (root_p / "config" / "ustplan.json")
    cfg = _merge(DEFAULTS, {})
    if p.exists():
        try:
            cfg = _merge(cfg, json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            sys.exit(f"错误: 配置文件 {p} 不是合法 JSON（{e}）")
    return cfg


def semester_of_session(session: str, cfg: dict = None) -> str:
    """session 尾号 → 学期名（2610→Fall / 2620→Winter / 2630→Spring / 2640→Summer）。
    学期→尾号映射的唯一权威是 config/ustplan.json → semesters（默认
    {Fall:10, Winter:20, Spring:30, Summer:40}——2026-08 实测 wcq 索引页下拉
    逐项确认：2610=2026-27 Fall、2520=2025-26 Winter、2530=2025-26 Spring、
    2540=2025-26 Summer；注意 subject 页模板固定显示当前学期，不可作为依据）；
    未知尾号（如 2540 之外的奇数值）返回 ""（调用方降级）。"""
    sem = (cfg or DEFAULTS).get("semesters") or DEFAULTS["semesters"]
    tail = str(session or "")[2:]
    for name, code in sem.items():
        if str(code).zfill(2) == tail:
            return name
    return ""


def previous_sessions(session: str, cfg: dict = None, n: int = 2) -> list:
    """目标 session 的前 N 个学期（日历倒序，返回越早越靠后）。
    按 4 位学期码（YYSS，SS∈{10,20,30,40}=Fall/Winter/Spring/Summer）回退：
      Fall   2610 → [2540(Summer), 2530(Spring)]
      Winter 2620 → [2610(Fall),   2540(Summer)]
      Spring 2630 → [2620(Winter), 2610(Fall)]
      Summer 2640 → [2630(Spring), 2620(Winter)]
    未知/非法 session 返回 []（调用方降级跳过历史对照）。"""
    s = str(session or "")
    if not re.fullmatch(r"\d{4}", s):
        return []
    sem = (cfg or DEFAULTS).get("semesters") or DEFAULTS["semesters"]
    codes = sorted(sem.values())
    tail = int(s[2:])
    if tail not in codes:
        return []
    steps = []
    yy, tt = int(s[:2]), tail
    for _ in range(max(1, n)):
        tt -= 10
        if tt < codes[0]:
            tt = codes[-1]
            yy -= 1
        steps.append(f"{yy:02d}{tt:02d}")
    return steps[:n]


def validate_schema(cfg: dict, schema_dir=None) -> list:
    """用 config.schema.json 校验配置，返回错误列表（R2 语义复用）。"""
    schema_dir = Path(schema_dir) if schema_dir else ROOT / "templates" / "schemas"
    schema = schema_dir / "config.schema.json"
    if not schema.exists():
        return []
    try:
        from jsonschema import Draft7Validator
    except ImportError:
        sys.exit("缺少依赖 jsonschema，请先运行: python -m pip install jsonschema")
    return [f"config: {e.message}" for e in Draft7Validator(
        json.loads(schema.read_text(encoding="utf-8"))).iter_errors(cfg)]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="配置预览/校验")
    ap.add_argument("--path", default=None, help="配置文件路径（默认 config/ustplan.json）")
    ap.add_argument("--check", action="store_true", help="仅校验 schema，不打印")
    args = ap.parse_args()
    cfg = load(path=args.path)
    errors = validate_schema(cfg)
    if errors:
        print("[CONFIG] FAIL:")
        for e in errors:
            print(e)
        sys.exit(1)
    if not args.check:
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
    else:
        print("[CONFIG] OK: 配置合法（权重 A/B/C/D = "
              f"{cfg['scoring']['weights']['a']}/{cfg['scoring']['weights']['b']}/"
              f"{cfg['scoring']['weights']['c']}/{cfg['scoring']['weights']['d']}）")
