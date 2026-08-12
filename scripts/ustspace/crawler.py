#!/usr/bin/env python3
"""
USTspace 课程评论爬虫 — scripts/ustspace/crawler.py
===================================================
抓取 ust.space 课程评论（需 ustspace_session cookie，仅 scripts 经
--cookie-file 读取，AI 不接触 cookie），产出：
  - cache/ustspace/raw/{code}.json      原始 API JSON（完整评论列表）
  - data/ustspace_reviews.json          解析汇总（热度 top5 + 每导师 top5）

流程（固化，见 skills/web-crawl-guide/SKILL.md）:
  1. GET https://ust.space/review/{CODE} → 提取 meta csrf_token
  2. GET https://ust.space/review/{CODE}/get?single=false&composer=false
     &preferences[sort]=0&preferences[filterInstructor]=0
     &preferences[filterSemester]=0&preferences[filterRating]=0
     头 X-CSRF-Token: <csrf>，cookie ustspace_session
  3. 响应 JSON: {course, reviews[], composer}

用法:
  python3 scripts/ustspace/crawler.py --codes "COMP 2011" "MATH 1013"
  python3 scripts/ustspace/crawler.py --codes-file data/filter_report.json
  python3 scripts/ustspace/crawler.py --codes "COMP 2011" --cookie-file credentials/cookies.txt
  python3 scripts/ustspace/crawler.py --codes "COMP 2011" --force
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "cache" / "ustspace" / "raw"
HEADERS = {"User-Agent": "Mozilla/5.0 (course-arranger build script)"}
GET_PARAMS = {
    "single": "false", "composer": "false",
    "preferences[sort]": "0", "preferences[filterInstructor]": "0",
    "preferences[filterSemester]": "0", "preferences[filterRating]": "0",
}


def load_cookies(path: Path) -> dict:
    cookies = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cookies[k.strip()] = v.strip()
    return cookies


def fetch_csrf(sess: requests.Session, code: str) -> str:
    """GET 课程页提取 meta csrf_token；失败返回 ''"""
    r = sess.get(f"https://ust.space/review/{code}", timeout=30)
    m = re.search(r'<meta name=["\']csrf_token["\'] content=["\']([^"\']*)["\']', r.text)
    return m.group(1) if m else ""


def fetch_course(sess: requests.Session, code: str, csrf: str) -> dict:
    """GET /review/{code}/get → 原始响应 dict；error 时抛 RuntimeError（含重试）"""
    url = f"https://ust.space/review/{code}/get"
    last = None
    for _ in range(3):
        try:
            r = sess.get(url, params=GET_PARAMS,
                         headers={"X-CSRF-Token": csrf}, timeout=30)
            d = r.json()
            if d.get("error"):
                raise RuntimeError(f"API 返回 error: {d}")
            return d
        except (requests.RequestException, ValueError) as e:
            last = e
    raise RuntimeError(f"请求失败（重试 3 次）: {last}")


def heat_key(rv: dict) -> int:
    return int(rv.get("vote_count") or 0)


def summarize(course: dict, reviews: list) -> dict:
    """原始 API JSON → 紧凑汇总（热度 top5 + 每导师 top5）"""
    rv_sorted = sorted(reviews, key=heat_key, reverse=True)
    def slim(r):
        return {
            "hash": r.get("hash"), "semester": r.get("semester"),
            "instructors": [i.get("name") for i in (r.get("instructors") or [])],
            "author": r.get("author"), "date": r.get("date"),
            "title": r.get("title"), "comment": r.get("comment_content"),
            "rating_content": r.get("rating_content"), "rating_teaching": r.get("rating_teaching"),
            "rating_grading": r.get("rating_grading"), "rating_workload": r.get("rating_workload"),
            "upvote_count": r.get("upvote_count"), "vote_count": r.get("vote_count"),
            "comment_count": r.get("comment_count"),
            "has_midterm": r.get("has_midterm"), "has_final": r.get("has_final"),
            "has_assignment": r.get("has_assignment"), "has_project": r.get("has_project"),
            "has_attendance": r.get("has_attendance"),
        }
    heat_top5 = [slim(r) for r in rv_sorted[:5]]
    by_instructor = {}
    for r in reviews:
        for i in (r.get("instructors") or []):
            by_instructor.setdefault(i.get("name"), []).append(r)
    inst_top = [
        {"instructor": name, "top5": [slim(r) for r in sorted(rs, key=heat_key, reverse=True)[:5]]}
        for name, rs in sorted(by_instructor.items())
    ]
    return {
        "subject": course.get("subject"), "number": course.get("code"),
        "name": course.get("name"), "credits": course.get("credits"),
        "review_count": course.get("review_count"),
        "ratings": {
            "content": course.get("rating_content"), "teaching": course.get("rating_teaching"),
            "grading": course.get("rating_grading"), "workload": course.get("rating_workload"),
        },
        "instructors": [i.get("name") for i in (course.get("instructors") or [])],
        "heat_top5": heat_top5,
        "instructor_top5": inst_top,
    }


def normalize_code(code: str) -> str:
    return "".join(code.upper().split())


def main():
    ap = argparse.ArgumentParser(description="USTspace 课程评论爬虫")
    ap.add_argument("--codes", nargs="+", help="课程代码，如 'COMP 2011'")
    ap.add_argument("--codes-file", help="JSON 文件（如 data/filter_report.json）中的课程代码列表")
    ap.add_argument("--cookie-file", default=str(ROOT / "credentials" / "cookies.txt"))
    ap.add_argument("--force", action="store_true", help="强制重新抓取")
    args = ap.parse_args()

    codes = []
    if args.codes:
        codes = [normalize_code(c) for c in args.codes]
    elif args.codes_file:
        data = json.loads(Path(args.codes_file).read_text(encoding="utf-8"))
        # 兼容三种输入：courses[]（candidate_rank / ustspace_reviews）与
        # kept[]（filter_report.json，step4 skill 指定）
        items = data.get("courses") or data.get("kept") or []
        for c in items:
            codes.append(normalize_code(c.get("code", "")))
    if not codes:
        ap.print_help()
        sys.exit(1)
    codes = list(dict.fromkeys(c for c in codes if c))

    cookie_path = Path(args.cookie_file)
    if not cookie_path.exists():
        sys.exit(f"错误: cookie 文件不存在 {cookie_path}（需含 ustspace_session 行）")
    cookies = load_cookies(cookie_path)
    if "ustspace_session" not in cookies:
        sys.exit("错误: cookie 文件中缺少 ustspace_session")

    sess = requests.Session()
    sess.cookies.update(cookies)
    sess.headers.update(HEADERS)

    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    csrf = ""
    results, fails, no_data = [], [], []

    for code in codes:
        raw = RAW_ROOT / f"{code}.json"
        if not args.force and raw.exists():
            try:
                d = json.loads(raw.read_text(encoding="utf-8"))
                results.append(summarize(d["course"], d["reviews"]))
                print(f"  [CACHE] {code}")
                continue
            except (json.JSONDecodeError, KeyError):
                pass
        try:
            if not csrf:
                csrf = fetch_csrf(sess, code)
                if not csrf:
                    sys.exit("错误: 无法获取 csrf_token（登录失效？）")
            d = fetch_course(sess, code, csrf)
            if not isinstance(d.get("course"), dict) or not isinstance(d.get("reviews"), list):
                raise ValueError(f"响应结构异常（缺 course/reviews）: {str(d)[:200]}")
            raw.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            results.append(summarize(d["course"], d["reviews"]))
            print(f"  [OK] {code}: {d['course'].get('review_count')} 条评论")
        except requests.RequestException as e:
            fails.append({"code": code, "reason": f"网络错误 {e}"})
            print(f"  [FAIL] {code}: {e}")
        except RuntimeError as e:
            if "API 返回 error" in str(e):
                # {"error": true} = 该课无评论数据（正常，非失败，不阻塞 job）
                no_data.append({"code": code, "reason": str(e)})
                print(f"  [NODATA] {code}: {e}")
                continue
            if "error" in str(e) and csrf:
                # csrf 过期 → 刷新一次重试
                csrf = fetch_csrf(sess, code)
                try:
                    d = fetch_course(sess, code, csrf)
                    if not isinstance(d.get("course"), dict) or not isinstance(d.get("reviews"), list):
                        raise ValueError(f"响应结构异常: {str(d)[:200]}")
                    raw.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    results.append(summarize(d["course"], d["reviews"]))
                    print(f"  [OK] {code}（csrf 刷新后）: {d['course'].get('review_count')} 条评论")
                    continue
                except Exception as e2:
                    fails.append({"code": code, "reason": f"API error: {e2}"})
                    print(f"  [FAIL] {code}: {e2}")
                    continue
            fails.append({"code": code, "reason": str(e)})
            print(f"  [FAIL] {code}: {e}")
        except (ValueError, KeyError) as e:
            fails.append({"code": code, "reason": str(e)})
            print(f"  [FAIL] {code}: {e}")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "course_count": len(results),
        "courses": results,
        "failed": fails,
        "no_data": no_data,
    }
    dest = ROOT / "data" / "ustspace_reviews.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n汇总 {len(results)} 门课, 无评论 {len(no_data)}, 失败 {len(fails)} -> {dest}")
    # 无评论数据（{"error":true}）属正常，不置非 0 退出码（避免 job 误判 failed）
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
