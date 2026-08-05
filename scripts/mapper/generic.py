#!/usr/bin/env python3
"""
AR↔curriculum 映射：通用策略链 — mapper/generic.py
===================================================
把 SIS Academic Requirements 的"未满足条目"映射到 curriculum 候选索引，
给出该条目可选的候选课程。语义判断（布尔/计数/条件）不在本层，交 phase3。

策略优先级（置信度由高到低）:
  1. override      — database/mappings/{PROG}.json 显式规则   (explicit)
  2. code_intersection — AR 相关课程 ∩ curriculum 组课程      (high)
  3. text_match    — AR 描述与组 note/节名 词重叠            (medium)
  4. structural    — 按 AR 组序对应同类型节                    (low)
  5. fallback      — 未映射 → unmapped（需人工确认）
"""

import re

STOP = set("""
the a an of in for and or to on with at from by may not must any one two three
course courses students following take taken into major requirements specified
as subject level above list their its it be can only also are is required
""".split())

CC_KEYWORDS = ("common core", "arts (a)", "science (s)", "english", "legal",
               "distribution", "foundation", "general education")


def normalize_code(code: str) -> str:
    # 统一去空格：AR 是 "PHYS1113"，curriculum 是 "PHYS 1113"
    return re.sub(r"\s+", "", code.strip().upper())


def flatten_curriculum(curriculum: dict) -> list:
    """把 curriculum 树拍平为要求组列表（含节/块归属）"""
    entries = []
    for b in curriculum.get("requirements", []):
        for s in b.get("sections", []):
            for g in s.get("groups", []):
                entries.append({
                    "block": b["block"],
                    "block_name": b["name"],
                    "section": s["type"],
                    "section_name": s["name"],
                    "note": g.get("note", ""),
                    "credits": g.get("credits", ""),
                    "courses": [c["code"] for c in g.get("courses", [])],
                    "areas": g.get("areas", []),
                })
    return entries


def _code_set(codes):
    return {normalize_code(c) for c in codes}


def _subject_prefix(code: str) -> str:
    """提取 subject 前缀："PHYS1113"/"PHYS 1113" → "PHYS"；本身无数字则原样返回"""
    return re.sub(r"\d.*$", "", re.sub(r"\s+", "", code.strip().upper()))


def code_intersection(ar_codes, entries) -> list:
    """返回 (entry, matched_codes) 列表"""
    ar = _code_set(ar_codes)
    hits = []
    for e in entries:
        cs = _code_set(e["courses"])
        inter = ar & cs
        # 无课号的 AR 代码（如 "PHYS"）按 subject 前缀匹配
        if not inter:
            ar_prefixes = {c for c in ar if not re.search(r"\d", c)}
            inter = {c for c in cs if _subject_prefix(c) in ar_prefixes}
        if inter:
            hits.append((e, sorted(inter)))
    return hits


def tokens(text: str) -> set:
    return {w for w in re.findall(r"[A-Za-z]{3,}", text.lower()) if w not in STOP}


def text_similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def text_match(ar_text, entries, threshold: float = 0.25) -> list:
    scored = []
    for e in entries:
        hay = f"{e['section_name']} {e['note']} {e['block_name']}"
        s = text_similarity(ar_text, hay)
        if s >= threshold:
            scored.append((e, s))
    scored.sort(key=lambda x: -x[1])
    return scored


def structural(ar_group, entries, ar_index: int, section: str = None) -> list:
    """按节类型与组序做位置对应（低置信度）"""
    same_section = [e for e in entries if not section or e["section"] == section]
    if not same_section:
        return []
    # AR 组名中含的节关键词辅助定位
    key = re.sub(r"\(.*?\)", "", ar_group).lower()
    if "elective" in key or "elect" in key:
        same_section = [e for e in same_section if e["section"] == "elective"]
    elif "required" in key or "fundamental" in key or "pre" in key:
        same_section = [e for e in same_section if e["section"] != "elective"]
    if not same_section:
        return []
    idx = ar_index % len(same_section)
    return [(same_section[idx], 0.0)]


def is_cc_item(ar_text: str, ar_codes) -> bool:
    if ar_codes:
        return False
    low = ar_text.lower()
    return any(k in low for k in CC_KEYWORDS)


def _hint_section(ar_text: str):
    """从 AR 组名推断节类型，缩小文本匹配范围"""
    low = ar_text.lower()
    if "elective" in low or "elect" in low or "option" in low:
        return "elective"
    if "pre" in low and "requisite" in low:
        return "pre_major"
    if "fundamental" in low:
        return "fundamental"
    if "required" in low or "seminar" in low:
        return "required"
    return None


def best_match(ar_text, entries, section: str) -> dict:
    """文本/结构兜底，返回置信度 medium 或 low 的结果"""
    pool = entries
    hint = _hint_section(ar_text) or section
    if hint:
        pool = [e for e in entries if e["section"] == hint]
        if not pool:
            pool = entries
    tm = text_match(ar_text, pool)
    if tm:
        e, s = tm[0]
        return {"entry": e, "confidence": "medium", "method": "text_match",
                "score": round(s, 3)}
    if section:
        st = structural(ar_text, entries, 0, section)
        if st:
            return {"entry": st[0][0], "confidence": "low", "method": "structural"}
    return {"entry": None, "confidence": "unmapped", "method": "fallback"}
