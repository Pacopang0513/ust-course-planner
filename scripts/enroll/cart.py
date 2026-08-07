#!/usr/bin/env python3
"""
选课写入（Enrollment Cart）— scripts/enroll/cart.py
=====================================================
把最终确认的课表方案（output/timetable_plan.json）转换为可提交的选课清单，
并接入 admlu65.ust.hk（HKUST 选课系统，Microsoft SSO 登录）的学期开放检查。

流程（enrollment-commit skill 承载，最终提交由用户人工确认——选课高风险）：
  1. build    方案 → 选课清单（code/section/学期/学分；TBA 课标注不可提交）
  2. check    admlu65 可达性 + 目标学期开放探测（未开放 → 明确提示等待）
  3. submit   引导提交：无会话/学期未开放 → 明确报错；有会话 → 输出人工
              核对清单 + 打开 Shopping Cart 指引（自动提交需 class_nbr，
              依赖 SIS Class Search 会话，框架预留，未验证前不代提交）

用法:
  python3 scripts/enroll/cart.py build --plan output/timetable_plan.json \
      --plan-id plan-1 --session <SESSION>
  python3 scripts/enroll/cart.py check --session <SESSION>
  python3 scripts/enroll/cart.py submit --session <SESSION> --cart output/enroll_cart.json
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
ADMLU_BASE = "https://admlu65.ust.hk"
SIS_CART_REL = "/psc/CS90/EMPLOYEE/HRMS/c/SA_LEARNER_SERVICES.SSR_SSENRL_CART.GBL"
HEADERS = {"User-Agent": "Mozilla/5.0 (course-arranger build script)"}
COOKIE_KEY = "admlu_session"  # admlu65 会话 cookie（用户从浏览器复制，可选）


def load_json(p: Path) -> dict:
    if not p.exists():
        sys.exit(f"错误: 找不到 {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def term_label(session: str, data_dir: Path = None) -> str:
    """学期显示名：优先取 data/courses_{session}.json 的 semester_name（数据驱动，
    新学年无需改代码）；缺失时回退 session 代码本身。"""
    p = (data_dir or ROOT / "data") / f"courses_{session}.json"
    if p.exists():
        try:
            name = load_json(p).get("semester_name", "")
            if name:
                return name
        except Exception:
            pass
    return session


def cmd_build(args):
    plan = load_json(Path(args.plan))
    plans = {p["plan_id"]: p for p in plan.get("plans", [])}
    if args.plan_id not in plans:
        sys.exit(f"错误: 方案 {args.plan_id} 不存在（可用: {', '.join(plans)}）")
    p = plans[args.plan_id]
    courses = []
    for d in p.get("course_details", []):
        tba = not d.get("sections") or all(
            str(s.get("datetime", "")).strip().upper() in ("", "TBA", "TBD")
            for s in (d.get("sections") or []))
        courses.append({
            "code": d.get("code", ""),
            "section": d.get("section", ""),
            "credits": d.get("credits"),
            "category": d.get("category", ""),
            "tba": bool(tba),
            "note": "上课时间未公布，不可提交，需等排期公布后补选" if tba else "",
        })
    out = {
        "session": args.session,
        "term": term_label(args.session,
                           Path(args.data_dir) if getattr(args, "data_dir", "") else None),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "plan_id": args.plan_id,
        "total_credits": p.get("total_credits"),
        "courses": courses,
    }
    dest = Path(args.cart)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    n_tba = sum(1 for c in courses if c["tba"])
    print(f"选课清单 {len(courses)} 门（其中 TBA 待公布 {n_tba} 门）-> {dest}")
    for c in courses:
        mark = "TBA" if c["tba"] else "  OK"
        print(f"  [{mark}] {c['code']:10} [{c['section']:4}] {c['credits']} 学分")
    if n_tba:
        print("\n提示: TBA 课程（时间未公布）不可写入，需等 Class Schedule 更新后补选；"
              "写入前请确认课程已开放选课。")


def cmd_check(args):
    """admlu65 可达性探测。根路径 200 = SSO 登录页正常；500/超时 = 未开放或维护。"""
    print(f"探测选课系统 {ADMLU_BASE} ...")
    try:
        r = requests.get(ADMLU_BASE + "/", timeout=25, headers=HEADERS,
                         allow_redirects=True)
    except requests.RequestException as e:
        print(f"[UNREACHABLE] 无法连接（{type(e).__name__}）——选课系统不可达，"
              f"可能未到开放期或网络受限")
        return 1
    low = r.text[:200_000].lower()
    if r.status_code == 200 and "sign in" in low:
        term = term_label(args.session)
        print(f"[OK] 选课系统在线（SSO 登录页正常）。")
        print(f"目标学期 {args.session}（{term}）是否已开放选课：请在浏览器登录 "
              f"{ADMLU_BASE} 后在 Enrollment / Shopping Cart 查看；"
              f"脚本无法替代登录态判断学期开放状态。")
        print(f"    提示：目标学期未开放时 Shopping Cart 会显示不可用/无课程，"
              f"以学校通知为准。")
        return 0
    print(f"[ODD] 响应异常（HTTP {r.status_code}，无登录页特征）——可能维护中或未开放")
    return 1


def cmd_submit(args):
    cart = load_json(Path(args.cart))
    cookies = {}
    cp = ROOT / "credentials" / "cookies.txt"
    if cp.exists():
        for line in cp.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cookies[k.strip()] = v.strip()
    session_key = cookies.get(COOKIE_KEY, "")
    if not session_key:
        print(f"[BLOCK] 缺少 {COOKIE_KEY}（admlu65 会话 cookie）。")
        print("  引导：浏览器登录 " + ADMLU_BASE + " → 开发者工具复制会话 cookie → "
              "写入 credentials/cookies.txt 的 " + COOKIE_KEY + "=... 行")
        return 1
    tba = [c for c in cart["courses"] if c.get("tba")]
    if tba:
        print("[BLOCK] 清单含 TBA 课程，不可提交：", ", ".join(c["code"] for c in tba))
        print("  等 Class Schedule 公布具体时间后重跑 build 再提交")
        return 1
    print(f"[OK] 会话 cookie 存在；目标学期 {cart['session']}（{cart['term']}）。")
    print(f"  请按以下核对清单在浏览器完成提交（自动提交依赖 SIS Class Search 的 "
          f"class_nbr，当前版本为人工确认流程）:")
    for c in cart["courses"]:
        print(f"    - {c['code']} [{c['section']}] {c['credits']} 学分")
    print(f"  入口：{ADMLU_BASE}{SIS_CART_REL}（需已登录 + 学期已开放）")
    print("  提交后请在 SIS 确认 Enrollment 状态；遇问题按 RUNBOOK §2 处理。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="选课写入（Enrollment Cart）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("build", help="方案 → 选课清单")
    pb.add_argument("--plan", default=str(ROOT / "output" / "timetable_plan.json"))
    pb.add_argument("--plan-id", default="plan-1")
    pb.add_argument("--session", default="")
    pb.add_argument("--data-dir", default="", help="courses_*.json 所在目录（默认 data/；测试注入用）")
    pb.add_argument("--cart", default=str(ROOT / "output" / "enroll_cart.json"))
    pb.set_defaults(fn=cmd_build)

    pc = sub.add_parser("check", help="admlu65 可达性/学期开放探测")
    pc.add_argument("--session", default="")
    pc.set_defaults(fn=cmd_check)

    ps = sub.add_parser("submit", help="提交引导（人工确认流程）")
    ps.add_argument("--session", default="")
    ps.add_argument("--cart", default=str(ROOT / "output" / "enroll_cart.json"))
    ps.set_defaults(fn=cmd_submit)

    args = ap.parse_args()
    if not args.session:
        sys.exit("错误: 缺少 --session（学期代码；运行中的学期可由 ustplan status 查询）")
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
