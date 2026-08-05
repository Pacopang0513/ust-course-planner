#!/usr/bin/env python3
"""
cookie 获取与预检 — scripts/cookies_setup.py
============================================
解决 credentials/cookies.txt 的获取与有效期问题。约束：AI 不接触 cookie 明文，
本脚本负责全部用户交互与验证闭环，只向 AI 输出"状态"。

三种模式:
  python3 scripts/cookies_setup.py --check              # 预检（phase1 确认点 P1 用）
  python3 scripts/cookies_setup.py                      # 交互引导：粘贴 → 写入 → 自动验证
  python3 scripts/cookies_setup.py --print-bookmarklet  # 输出书签代码（一键复制当前域 cookie）

--check 输出每项状态（OK / EXPIRED / MISSING / UNREACHABLE），
绝不打印任何 cookie 值；全部 OK 退出 0，否则退出 1。
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COOKIE_FILE = ROOT / "credentials" / "cookies.txt"

HEADERS = {"User-Agent": "Mozilla/5.0 (course-arranger cookie check)"}

# SIS（PeopleSoft）真实 Student Center 页的正特征。无 cookie 时 SIS 可能返回
# 200 的多种壳页面（登录页/空壳），仅凭失效 marker 判定不可靠（2026-08 实测
# 响应不稳定），故用正特征：只有出现真实页面特征才算 OK，其余一律判失效。
SIS_URL = ("https://sisprod.psft.ust.hk/psc/SISPROD/EMPLOYEE/HRMS/c/"
           "SA_LEARNER_SERVICES.SSS_STUDENT_CENTER.GBL")
SIS_OK_MARKERS = ["icsid", "derived_sss_scl_sss_more_academics", "derived_sstsnav"]

# USTspace（csrf token 能提取 = 会话有效）
USTSPACE_URL = "https://ust.space/review/COMP2011"
CSRF_RE = re.compile(r'<meta name=["\']csrf_token["\'] content=["\']([^"\']*)["\']')

REQUIRED_KEYS = ["PS_TOKEN", "ustspace_session"]


# ── 探测 ──────────────────────────────────────────────

def check_sis(cookies: dict) -> tuple:
    """→ (状态, 说明)。正特征判定：只有出现真实 Student Center 页面特征才算 OK，
    其余（登录壳/未授权/空壳/异常）一律判失效，宁可误报不可误放。"""
    if not cookies.get("PS_TOKEN"):
        return "MISSING", "缺少 PS_TOKEN"
    try:
        r = requests.get(SIS_URL, headers=HEADERS, cookies=cookies, timeout=20)
    except requests.RequestException as e:
        return "UNREACHABLE", f"无法连接 SIS（{type(e).__name__}，稍后重试）"
    low = r.text[:300_000].lower()
    if r.status_code == 200 and any(m in low for m in SIS_OK_MARKERS):
        return "OK", "PS_TOKEN 有效"
    return "EXPIRED", "PS_TOKEN 已失效（未取得 Student Center 页面）"


def check_ustspace(cookies: dict) -> tuple:
    """→ (状态, 说明)。"""
    if not cookies.get("ustspace_session"):
        return "MISSING", "缺少 ustspace_session"
    try:
        r = requests.get(USTSPACE_URL, headers=HEADERS, cookies=cookies, timeout=20)
        if r.status_code == 200 and CSRF_RE.search(r.text):
            return "OK", "ustspace_session 有效"
        return "EXPIRED", "ustspace_session 已失效（无法取得会话）"
    except requests.RequestException as e:
        return "UNREACHABLE", f"无法连接 ust.space（{type(e).__name__}，稍后重试）"


# ── 文件读写 ──────────────────────────────────────────

def load_cookies(path: Path) -> dict:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def save_cookies(path: Path, cookies: dict):
    """按固定 key=value 格式写回（保留注释行之前的全部键）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in sorted(cookies.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_paste(text: str) -> dict:
    """解析用户粘贴内容：bookmarklet 的 JSON / 一行或多个 key=value。"""
    text = text.strip().lstrip("\ufeff")
    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return {str(k): str(v) for k, v in obj.items()}
        except json.JSONDecodeError:
            pass
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            if k.strip():
                out[k.strip()] = v.strip()
    return out


# ── 输出 ──────────────────────────────────────────────

def run_check(cookies: dict) -> int:
    rows = {
        "SIS (PS_TOKEN)": check_sis(cookies),
        "USTspace (ustspace_session)": check_ustspace(cookies),
    }
    print("cookie 预检（不显示值）:")
    all_ok = True
    for name, (status, note) in rows.items():
        mark = {"OK": "[OK]", "EXPIRED": "[失效]", "MISSING": "[缺失]",
                "UNREACHABLE": "[网络]"}[status]
        print(f"  {mark} {name:22} {note}")
        all_ok = all_ok and status == "OK"
    if all_ok:
        print("OK: 凭据就绪，可以开始流程")
        return 0
    print("未全部就绪：运行 `python3 scripts/cookies_setup.py` 重新获取，或只重贴失效键。")
    return 1


BOOKMARKLET = (
    "javascript:(function(){try{var c={};"
    "document.cookie.split('; ').forEach(function(p){"
    "var i=p.indexOf('=');if(i>0)c[p.slice(0,i)]=p.slice(i+1)});"
    "var s=JSON.stringify(c);"
    "if(navigator.clipboard&&navigator.clipboard.writeText){"
    "navigator.clipboard.writeText(s).then("
    "function(){alert('已复制 '+Object.keys(c).length+' 个 cookie，粘贴到 cookies_setup.py')},"
    "function(){prompt('手动复制:',s)})}else{prompt('手动复制:',s)}"
    "}catch(e){alert('失败: '+e)}})();"
)


def print_bookmarklet():
    print("在浏览器地址栏新建书签，网址填以下内容（一行）:\n")
    print(BOOKMARKLET)
    print("""
用法：分别登录 SIS 与 ust.space 后，在对应页面点击该书签 → cookie 自动复制到
剪贴板 → 运行 `python3 scripts/cookies_setup.py` 粘贴提交。

限制：书签只能读取当前域的非 httpOnly cookie。SIS 的 PS_TOKEN 若为 httpOnly
（书签复制不到），请用 F12 → Network → 请求头 Cookie 手动复制，或直接粘贴
登录后地址栏里的 JSESSIONID/PS_TOKEN（引导模式支持单键粘贴）。
""")


# ── 交互引导 ──────────────────────────────────────────

GUIDE = """\
SIS cookie（PS_TOKEN）：
  1. 浏览器打开 https://sisprod.psft.ust.hk 并完成登录（含 MFA）
  2. F12 → Network → 刷新页面 → 点第一个请求 → 复制 Cookie 请求头
     （或使用 bookmarklet：--print-bookmarklet）
USTspace cookie（ustspace_session）：
  1. 浏览器打开 https://ust.space 并完成登录
  2. 同上（F12 或 bookmarklet）
"""


def interactive(path: Path):
    print("== cookie 获取引导 ==")
    print(GUIDE)
    print("粘贴内容（一行一个 key=value，或 bookmarklet 复制的 JSON 整段），")
    print("粘贴完成后按回车（空行）提交。只更新需要更新的键即可。\n")
    lines = []
    for line in sys.stdin:
        if line.strip() == "":
            break
        lines.append(line)
    pasted = parse_paste("".join(lines))
    if not pasted:
        print("未解析到任何 key=value，未做修改。")
        sys.exit(1)

    merged = load_cookies(path)
    for k, v in pasted.items():
        if k in ("PS_TOKEN", "ustspace_session", "JSESSIONID",
                 "PS_TOKENEXPIRE", "csrf_token") or not v:
            merged[k] = v
    # 只保留脚本认识的键，避免把无关粘贴写进凭据文件
    keep = {k: v for k, v in merged.items() if k in REQUIRED_KEYS + ["JSESSIONID", "PS_TOKENEXPIRE"]}
    save_cookies(path, keep)
    print(f"已更新 {path}（{len(keep)} 个键）\n")
    sys.exit(run_check(keep))


def main():
    ap = argparse.ArgumentParser(description="cookie 获取与预检（AI 不接触明文）")
    ap.add_argument("--check", action="store_true", help="预检当前凭据有效性")
    ap.add_argument("--print-bookmarklet", action="store_true",
                    help="输出一键复制 cookie 的书签代码")
    ap.add_argument("--cookie-file", default=str(DEFAULT_COOKIE_FILE),
                    help="cookie 文件路径（默认 credentials/cookies.txt）")
    args = ap.parse_args()

    path = Path(args.cookie_file)

    if args.print_bookmarklet:
        print_bookmarklet()
        return 0
    if args.check:
        return run_check(load_cookies(path))
    interactive(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
