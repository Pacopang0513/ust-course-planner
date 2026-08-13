#!/usr/bin/env python3
"""
单测：凭据统一模块 — 2026-08-13
================================
credentials.py（load/save/filter/meta/TTL）+ cookies_setup 接收协议纯函数
（handle_submit_payload）。全部离线，不依赖浏览器。

运行（在 scripts/ 目录下，保证 harness/rank 可导入）:
  python tests/unit/test_cookies.py
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from credentials import (KNOWN_KEYS, filter_known, load_cookies,  # noqa: E402
                         meta_read, meta_update, meta_write, save_cookies,
                         ttl_info, ttl_warning)
from cookies_setup import handle_submit_payload, make_token  # noqa: E402


class TestLoadSave(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ust_cred_"))
        self.cf = self.tmp / "cookies.txt"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_load_roundtrip(self):
        save_cookies({"PS_TOKEN": "a", "ustspace_session": "b", "junk": "x"}, self.cf)
        got = load_cookies(self.cf)
        self.assertEqual(got, {"PS_TOKEN": "a", "ustspace_session": "b"})

    def test_load_missing_returns_empty(self):
        self.assertEqual(load_cookies(self.tmp / "nope.txt"), {})

    def test_load_bom_tolerant(self):
        self.cf.write_bytes(b"\xef\xbb\xbfPS_TOKEN=a\n")
        self.assertEqual(load_cookies(self.cf), {"PS_TOKEN": "a"})

    def test_filter_known_by_source(self):
        cookies = {"PS_TOKEN": "a", "JSESSIONID": "b", "PS_TOKENEXPIRE": "c",
                   "ustspace_session": "d", "junk": "z"}
        self.assertEqual(filter_known(cookies, "sis"),
                         {"PS_TOKEN": "a", "JSESSIONID": "b", "PS_TOKENEXPIRE": "c"})
        self.assertEqual(filter_known(cookies, "ustspace"),
                         {"ustspace_session": "d"})
        self.assertEqual(filter_known(cookies),
                         {k: v for k, v in cookies.items() if k in KNOWN_KEYS})


class TestMetaTTL(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ust_cred_"))
        self.cf = self.tmp / "cookies.txt"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_meta_follows_cookie_path(self):
        meta_update("sis", self.cf)
        self.assertTrue((self.tmp / "meta.json").exists())
        self.assertEqual(meta_read(self.cf).get("sources"), ["sis"])
        # 同目录 meta 不与默认路径混淆
        self.assertEqual(meta_read(), {})

    def test_meta_update_appends_sources(self):
        meta_update("sis", self.cf)
        meta_update("ustspace", self.cf)
        self.assertEqual(sorted(meta_read(self.cf).get("sources", [])),
                         ["sis", "ustspace"])

    def test_ttl_expired(self):
        meta_write({"fetched_at": (datetime.now(timezone.utc)
                                   - timedelta(hours=13)).isoformat()}, self.cf)
        info = ttl_info(12.0, self.cf)
        self.assertTrue(info["expired"])
        self.assertGreater(info["age_hours"], 12.0)
        self.assertIn("建议刷新", ttl_warning(12.0, self.cf))

    def test_ttl_fresh_no_warning(self):
        meta_write({"fetched_at": datetime.now(timezone.utc).isoformat()}, self.cf)
        self.assertFalse(ttl_info(12.0, self.cf)["expired"])
        self.assertEqual(ttl_warning(12.0, self.cf), "")

    def test_ttl_no_meta(self):
        self.assertFalse(ttl_info(12.0, self.cf)["expired"])
        self.assertEqual(ttl_warning(12.0, self.cf), "")


class TestListenProtocol(unittest.TestCase):
    """cookies_setup --listen 接收协议纯函数（handle_submit_payload）"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ust_cred_"))
        self.cf = self.tmp / "cookies.txt"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wrong_token_rejected(self):
        ok, msg, _ = handle_submit_payload(
            {"source": "sis", "cookies": {"PS_TOKEN": "x"}},
            "000000", "123456", self.cf)
        self.assertFalse(ok)
        self.assertIn("连接码", msg)

    def test_unknown_source_rejected(self):
        ok, msg, _ = handle_submit_payload(
            {"source": "evil", "cookies": {"PS_TOKEN": "x"}},
            "123456", "123456", self.cf)
        self.assertFalse(ok)

    def test_accepts_and_filters(self):
        ok, msg, merged = handle_submit_payload(
            {"source": "sis", "cookies": {"PS_TOKEN": "t1", "JSESSIONID": "t2",
                                          "junk": "z"}},
            "123456", "123456", self.cf)
        self.assertTrue(ok)
        self.assertEqual(merged, {"PS_TOKEN": "t1", "JSESSIONID": "t2"})
        self.assertEqual(load_cookies(self.cf),
                         {"PS_TOKEN": "t1", "JSESSIONID": "t2"})
        # 元数据跟随 cookie 文件
        self.assertTrue((self.tmp / "meta.json").exists())

    def test_merge_preserves_existing(self):
        save_cookies({"ustspace_session": "old"}, self.cf)
        handle_submit_payload({"source": "sis", "cookies": {"PS_TOKEN": "new"}},
                              "123456", "123456", self.cf)
        got = load_cookies(self.cf)
        self.assertEqual(got["ustspace_session"], "old")
        self.assertEqual(got["PS_TOKEN"], "new")

    def test_empty_cookies_rejected(self):
        ok, msg, _ = handle_submit_payload(
            {"source": "sis", "cookies": {"junk": "x"}},
            "123456", "123456", self.cf)
        self.assertFalse(ok)

    def test_make_token_six_digits(self):
        for _ in range(20):
            t = make_token()
            self.assertRegex(t, r"^\d{6}$")


if __name__ == "__main__":
    unittest.main()
