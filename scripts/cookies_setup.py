#!/usr/bin/env python3
"""
cookie 获取与预检 — scripts/cookies_setup.py
============================================
解决 credentials/cookies.txt 的获取与有效期问题。约束：AI 不接触 cookie 明文，
本脚本负责全部用户交互与验证闭环，只向 AI 输出"状态"。

五种模式:
  python3 scripts/cookies_setup.py --check              # 预检（含有效期 TTL 提醒）
  python3 scripts/cookies_setup.py                      # 交互引导：粘贴 → 写入 → 自动验证
  python3 scripts/cookies_setup.py --listen [--timeout N]  # 一键获取：本机接收端（浏览器扩展推送）
  python3 scripts/cookies_setup.py --print-bookmarklet  # 输出书签代码（一键复制当前域 cookie）
  python3 scripts/cookies_setup.py --token-test         # 自测（协议纯函数，无需浏览器）

--check 输出每项状态（OK / EXPIRED / MISSING / UNREACHABLE）+ TTL 提醒，
绝不打印任何 cookie 值；全部 OK 退出 0，否则退出 1。
"""

import argparse
import json
import re
import secrets
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from credentials import (DEFAULT_COOKIE_FILE, filter_known,  # noqa: E402
                         load_cookies, meta_update, save_cookies, ttl_warning)

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

# 一键获取接收端（--listen）
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT_DEFAULT = 8765
LISTEN_PORT_RANGE = 10        # 端口占用时递增尝试
DEFAULT_TIMEOUT = 120         # 秒；无请求自动退出


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


def run_check(cookies: dict, path: Path = None) -> int:
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
    # TTL 提醒（凭据年龄 vs 阈值；警告级别，不改变退出码）
    try:
        from harness.config import load as load_config
        ttl = float((load_config().get("credentials") or {}).get("ttl_hours", 12))
    except Exception:  # noqa: BLE001
        ttl = 12.0
    warn = ttl_warning(ttl, path)
    if warn:
        print(f"  ~ {warn}")
    if all_ok:
        print("OK: 凭据就绪，可以开始流程")
        return 0
    print("未全部就绪：运行 `python3 scripts/cookies_setup.py` 交互引导，"
          "或 `--listen` 一键获取（浏览器扩展按钮），或只重贴失效键。")
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
（书签复制不到），请用浏览器扩展一键获取（--listen）或 F12 → Network → 请求头
Cookie 手动复制。
""")


# ── 一键获取接收端（--listen）─────────────────────────────

def make_token() -> str:
    """6 位数字连接码（secrets 随机）。"""
    return f"{secrets.randbelow(10**6):06d}"


def handle_submit_payload(payload: dict, header_token: str,
                          expected_token: str, path: Path) -> tuple:
    """接收端协议纯函数（可单测）→ (ok: bool, message: str, merged: dict)。
    payload: {source: 'sis'|'ustspace', cookies: {...}}；
    校验连接码 → 已知键过滤 → 合并写盘 + 元数据。绝不把 cookie 值写入消息。"""
    if not header_token or not secrets.compare_digest(
            str(header_token), str(expected_token)):
        return False, "连接码不正确（请核对扩展中保存的连接码）", {}
    source = str((payload or {}).get("source") or "")
    if source not in ("sis", "ustspace"):
        return False, f"未知来源 {source!r}（应为 sis / ustspace）", {}
    cookies = filter_known((payload or {}).get("cookies") or {}, source)
    if not cookies:
        return False, f"{source} 未获取到可识别的 cookie（未登录？或页面不对）", {}
    existing = load_cookies(path)
    existing.update(cookies)
    save_cookies(existing, path)
    meta_update(source, Path(path))
    return True, f"{source} 已接收并写入（{len(cookies)} 个键）", cookies


class ListenHandler(BaseHTTPRequestHandler):
    """仅本机回环；不记录请求日志（防 cookie 值落盘）。"""
    token = ""
    cookie_file = DEFAULT_COOKIE_FILE
    received = set()          # {source, ...}
    received_lock = threading.Lock()

    def log_message(self, fmt, *args):  # 静默（不回显路径/协议）
        pass

    def do_POST(self):  # noqa: N802  HTTP 方法名固定大写
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 65536:
            self._reply(400, "bad request")
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._reply(400, "bad json")
            return
        token = self.headers.get("X-Token") or ""
        ok, msg, cookies = handle_submit_payload(
            body, token, self.token, Path(self.cookie_file))
        self._reply(200 if ok else 403, msg)
        if ok:
            src = str((body or {}).get("source") or "")
            with self.received_lock:
                self.received.add(src)
                done = {"sis", "ustspace"} <= self.received
            if done:
                print("\n两个来源均已接收，开始验证…")
                threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _reply(self, code: int, msg: str):
        data = msg.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_listen(cookie_file: Path, timeout: int = DEFAULT_TIMEOUT) -> int:
    """启动本机接收端：等待浏览器扩展推送 SIS/USTspace cookie。
    收齐两源或超时自动退出。返回退出码（0=至少收到一个源）。"""
    port = LISTEN_PORT_DEFAULT
    server = None
    for _ in range(LISTEN_PORT_RANGE):
        try:
            server = ThreadingHTTPServer((LISTEN_HOST, port), ListenHandler)
            break
        except OSError:
            port += 1
    if server is None:
        print(f"错误: 端口 {LISTEN_PORT_DEFAULT}-{port} 均被占用，"
              f"无法启动接收端（先关闭占用进程）")
        return 1
    token = make_token()
    ListenHandler.token = token
    ListenHandler.cookie_file = str(cookie_file)
    ListenHandler.received = set()
    server.timeout = 1.0

    print("== cookie 一键获取（--listen）==", flush=True)
    print(f"本机接收服务: http://{LISTEN_HOST}:{port}（仅本机可访问，{timeout} 秒无请求自动退出）", flush=True)
    print(f"连接码: {token}", flush=True)
    print(f"""
浏览器扩展（ust-cookie）设置：端口 {port}，连接码 {token}。
然后：
  1. 登录 https://sisprod.psft.ust.hk （含 MFA）→ 点扩展按钮 → 页面显示"已发送"
  2. 登录 https://ust.space → 再点扩展按钮 → 页面显示"已发送"
（也可用 F12 复制后运行本脚本粘贴提交，两种方式等价）
""", flush=True)
    deadline = datetime.now(timezone.utc).timestamp() + timeout
    got_any = False
    try:
        while datetime.now(timezone.utc).timestamp() < deadline:
            server.handle_request()
            with ListenHandler.received_lock:
                if ListenHandler.received:
                    got_any = True
                if {"sis", "ustspace"} <= ListenHandler.received:
                    break
    except KeyboardInterrupt:
        print("\n已中断")
    finally:
        server.server_close()
    if not got_any:
        print(f"超时未收到任何来源（{timeout}s）。请确认扩展设置与登录状态后重试。")
        return 1
    print("\n== 自动验证 ==")
    return run_check(load_cookies(cookie_file), cookie_file)


# ── 交互引导 ──────────────────────────────────────────

GUIDE = """\
SIS cookie（PS_TOKEN）：
  1. 浏览器打开 https://sisprod.psft.ust.hk 并完成登录（含 MFA）
  2. 推荐：运行 `--listen` 后用扩展按钮一键获取（可读 httpOnly cookie）
     或 F12 → Network → 刷新页面 → 点第一个请求 → 复制 Cookie 请求头
USTspace cookie（ustspace_session）：
  1. 浏览器打开 https://ust.space 并完成登录
  2. 同上（扩展按钮或 F12）
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
    save_cookies(merged, path)
    meta_update("paste", path)
    print(f"已更新 {path}\n")
    sys.exit(run_check(load_cookies(path), path))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="cookie 获取与预检（AI 不接触明文）")
    ap.add_argument("--check", action="store_true", help="预检当前凭据有效性（含 TTL 提醒）")
    ap.add_argument("--listen", action="store_true",
                    help="一键获取：启动本机接收端（浏览器扩展推送，可读 httpOnly）")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                    help=f"--listen 等待秒数（默认 {DEFAULT_TIMEOUT}）")
    ap.add_argument("--print-bookmarklet", action="store_true",
                    help="输出一键复制 cookie 的书签代码")
    ap.add_argument("--token-test", action="store_true",
                    help="自测接收协议纯函数（无需浏览器）")
    ap.add_argument("--cookie-file", default=str(DEFAULT_COOKIE_FILE),
                    help="cookie 文件路径（默认 credentials/cookies.txt）")
    args = ap.parse_args()

    path = Path(args.cookie_file)

    if args.token_test:
        # 自测用临时文件（不得触碰真实凭据）
        import tempfile
        tmpf = Path(tempfile.mkdtemp(prefix="ust_cred_")) / "cookies.txt"
        ok, msg, _ = handle_submit_payload(
            {"source": "sis", "cookies": {"PS_TOKEN": "x", "junk": "y"}},
            "000000", "000000", tmpf)
        print("协议自测:", "PASS" if ok and msg.startswith("sis") else f"FAIL {msg}")
        bad, bmsg, _ = handle_submit_payload(
            {"source": "sis", "cookies": {"PS_TOKEN": "x"}},
            "wrong", "000000", tmpf)
        print("连接码拒收:", "PASS" if not bad else "FAIL")
        return 0 if ok and not bad else 1
    if args.print_bookmarklet:
        print_bookmarklet()
        return 0
    if args.listen:
        return run_listen(path, args.timeout)
    if args.check:
        return run_check(load_cookies(path), path)
    interactive(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
