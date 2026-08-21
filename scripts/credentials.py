#!/usr/bin/env python3
"""
凭据统一模块 — scripts/credentials.py
=====================================
cookie 读取/写入/元数据/有效期提醒的唯一实现（收敛 cookies_setup.py、
ustspace/crawler.py、sis/parser.py 三处重复的 load_cookies）。

存储后端按"可替换"设计（消费方零改动）：
  - 一期：明文 key=value 文件（credentials/cookies.txt，gitignored；
    测试 fixtures 亦为明文，test_runner R3 隔离不受影响）
  - 二期：DPAPI 加密（Windows CryptProtectData，ctypes 零依赖）——
    届时替换 load/save 内部实现即可

元数据（credentials/meta.json）：{fetched_at, sources[]}——
供 --check / doctor / ustplan status 做凭据有效期（TTL）提醒
（SIS 会话通常数小时过期，提前提醒避免流程中途失败）。

用法:
  from credentials import load_cookies, save_cookies, filter_known,
      meta_read, meta_update, ttl_info
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 脚本认识的凭据键（其余键粘贴时丢弃，防无关内容混入）
KNOWN_KEYS = ("PS_TOKEN", "ustspace_session", "JSESSIONID", "PS_TOKENEXPIRE")

# 各数据源允许的键（扩展/引导只收这些；source 越界键丢弃）
SOURCE_KEYS = {
    "sis": ("PS_TOKEN", "JSESSIONID", "PS_TOKENEXPIRE"),
    "ustspace": ("ustspace_session",),
}

DEFAULT_COOKIE_FILE = ROOT / "credentials" / "cookies.txt"


def load_cookies(path: Path = None) -> dict:
    """读取凭据文件（key=value 每行一行；# 注释与空行忽略；
    utf-8-sig 兼容 Windows 记事本 BOM 产物）。
    文件缺失/损坏返回 {}（调用方自行降级提示）。"""
    p = Path(path) if path else DEFAULT_COOKIE_FILE
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k:
            out[k] = v.strip()
    return out


def save_cookies(cookies: dict, path: Path = None):
    """写凭据文件（仅 KNOWN_KEYS；文件权限收窄：本机当前用户可读写）。"""
    p = Path(path) if path else DEFAULT_COOKIE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: v for k, v in (cookies or {}).items() if k in KNOWN_KEYS and v}
    p.write_text("".join(f"{k}={v}\n" for k, v in sorted(keep.items())),
                 encoding="utf-8")
    _restrict_permissions(p)


def filter_known(cookies: dict, source: str = "") -> dict:
    """按数据源过滤已知键（source='' 时按全局 KNOWN_KEYS）。"""
    keys = SOURCE_KEYS.get(source, KNOWN_KEYS) if source else KNOWN_KEYS
    return {k: str(v) for k, v in (cookies or {}).items()
            if k in keys and v}


def _restrict_permissions(path: Path):
    """收窄文件权限（Windows: icacls 仅当前用户；POSIX: chmod 600）。
    失败仅提示不阻断（NTFS 无 ACL 权限时）。"""
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(
                ["icacls", str(path), "/inheritance:r",
                 "/grant:r", f"{Path.home().name}:F"],
                capture_output=True, timeout=20)
        else:
            path.chmod(0o600)
    except Exception:  # noqa: BLE001  权限收窄为尽力而为
        pass


# ── 元数据 / TTL ──────────────────────────────────────────

def meta_path(cookie_path: Path = None) -> Path:
    """元数据文件跟随 cookie 文件所在目录（--cookie-file 自定义时同目录）。"""
    p = Path(cookie_path) if cookie_path else DEFAULT_COOKIE_FILE
    return p.parent / "meta.json"


def meta_read(cookie_path: Path = None) -> dict:
    try:
        return json.loads(meta_path(cookie_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def meta_write(meta: dict, cookie_path: Path = None):
    mp = meta_path(cookie_path)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def meta_update(source: str, cookie_path: Path = None):
    """记录凭据最近获取时间与来源（--check/--listen/粘贴共用）。"""
    meta = meta_read(cookie_path)
    meta["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sources = list(meta.get("sources") or [])
    if source and source not in sources:
        sources.append(source)
    meta["sources"] = sources
    meta_write(meta, cookie_path)


def ttl_info(ttl_hours: float = 12.0, cookie_path: Path = None) -> dict:
    """凭据年龄 vs TTL → {age_hours, ttl_hours, expired, fetched_at}。
    meta 缺失或时间无法解析 → expired=False（无凭据时由调用方按 MISSING 提示）。"""
    meta = meta_read(cookie_path)
    fetched = meta.get("fetched_at") or ""
    info = {"age_hours": None, "ttl_hours": ttl_hours,
            "expired": False, "fetched_at": fetched}
    if not fetched:
        return info
    try:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(fetched)).total_seconds() / 3600
    except ValueError:
        return info
    info["age_hours"] = round(age, 1)
    info["expired"] = age >= float(ttl_hours)
    return info


def ttl_warning(ttl_hours: float = 12.0, cookie_path: Path = None) -> str:
    """TTL 提醒文案（未过期返回 ''）："凭据已 X 小时（阈值 Y 小时），建议刷新" """
    info = ttl_info(ttl_hours, cookie_path)
    if info["age_hours"] is None:
        return ""
    if info["expired"]:
        return (f"凭据已 {info['age_hours']} 小时（超过阈值 {info['ttl_hours']} 小时），"
                f"建议刷新后再继续（运行 cookies_setup.py 交互引导或 --listen 一键获取）")
    if info["age_hours"] >= float(ttl_hours) * 0.7:
        return (f"凭据已 {info['age_hours']} 小时（阈值 {info['ttl_hours']} 小时），"
                f"接近过期，可提前刷新")
    return ""
