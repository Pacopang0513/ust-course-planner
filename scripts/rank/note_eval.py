#!/usr/bin/env python3
"""
curriculum Note 表达式解析与求值 — scripts/rank/note_eval.py
=============================================================
Step 1 配套工具：把 curriculum Note 的 OR/AND/括号/方括号/"any N of" 语义
固化为脚本解析（禁止 AI 手写求值器），供 buckets.py 做整桶满足性判定。

支持语法（对应 UST 真实 Note 格式，如 COMP.json FYP 组）：
  - 顶层 OR 优先级最低，其次 AND：'A AND B OR C' → (A AND B) OR C
  - 圆括号 () / 方括号 [] 均为分组：'[A AND (B OR C)] OR [D]'
  - 计数：'any 2 of A, B, C' → 满足 2 门即满足
  - 叶子：课程代码（'COMP 1991'）；含多个代码的叶子按 AND（全部满足）

求值语义（保守）：
  - met=True  明确满足；met=False 明确未满足；met=None 无法判定（无代码段）
  - OR 任一分支 True → True；AND 任一分支 False → False
  - 计数分支：满足数 ≥ N → True；满足数+未知数 < N → False；否则 None

用法:
  from rank import note_eval
  met, tree = note_eval.eval_note(
      "Note: [COMP 1991 AND (COMP 4981 OR COMP 4981H)] OR [COMP 4910]",
      {"COMP1991", "COMP4981"})
  if note_eval.complex_note(note):
      ...      # 含 AND/方括号/any N of，需表达式求值而非计数规则
"""

import re

RE_CODE = re.compile(r"([A-Z]{3,4})\s*(\d{4}[A-Z]?)")
RE_ANY_N = re.compile(r"any\s+(\d+)\s+of", re.I)


def norm_code(s: str) -> str:
    """课号规范化：大写、去空格/点（'COMP 1991' → 'COMP1991'）"""
    return re.sub(r"[\s.]+", "", str(s)).upper()


def complex_note(note: str) -> bool:
    """Note 是否含复杂语义（AND / 方括号分组 / any N of）→ 需表达式求值。
    纯 OR 列表（'A OR B OR C'）与无连接词列表走原计数规则即可。"""
    s = note or ""
    return ("[" in s or "]" in s
            or re.search(r"\bAND\b", s, re.I) is not None
            or RE_ANY_N.search(s) is not None)


def _split_top(text: str, sep: str) -> list:
    """按顶层连接词切分（忽略 ()/[] 内），返回去空白片段列表"""
    pat = re.compile(r"\s+" + re.escape(sep) + r"\s+", re.I)
    parts, depth, cur = [], 0, ""
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if depth == 0:
            m = pat.match(text, i)
            if m:
                parts.append(cur)
                cur = ""
                i = m.end()
                continue
        cur += ch
        i += 1
    parts.append(cur)
    return [p for p in (s.strip() for s in parts) if p]


def _wrapped(text: str) -> bool:
    """整个文本是否被一对最外层 () 或 [] 包裹"""
    depth = 0
    pairs = {"(": ")", "[": "]"}
    open_ch = None
    for i, ch in enumerate(text):
        if ch in pairs:
            depth += 1
            if open_ch is None:
                open_ch = ch
        elif ch in ")]":
            depth -= 1
            if depth == 0:
                return open_ch is not None and ch == pairs[open_ch] \
                    and i == len(text) - 1
    return False


def parse(text: str):
    """Note 文本 → 表达式树 node。
    node = ("or", [children]) | ("and", [children]) | ("count", n, [codes])
         | ("leaf", [codes]) | ("text",)"""
    text = (text or "").strip()
    if not text:
        return ("text",)
    text = re.sub(r"^\s*Note\s*[:\-]\s*", "", text, flags=re.I)

    or_parts = _split_top(text, "OR")
    if len(or_parts) > 1:
        return ("or", [parse(p) for p in or_parts])
    and_parts = _split_top(text, "AND")
    if len(and_parts) > 1:
        return ("and", [parse(p) for p in and_parts])
    if _wrapped(text):
        return parse(text[1:-1])

    m = RE_ANY_N.search(text)
    if m:
        codes = [f"{a} {b}" for a, b in RE_CODE.findall(text)]
        return ("count", int(m.group(1)), codes)

    codes = [f"{a} {b}" for a, b in RE_CODE.findall(text)]
    if codes:
        return ("leaf", codes)
    return ("text",)


def evaluate(node, done: set):
    """表达式树 → (met: bool|None, detail)"""
    kind = node[0]
    if kind == "or":
        met_list = [evaluate(c, done) for c in node[1]]
        any_true = any(m is True for m, _ in met_list)
        if any_true:
            return True, {"kind": "or", "branches": [d for _, d in met_list]}
        if any(m is None for m, _ in met_list):
            return None, {"kind": "or", "branches": [d for _, d in met_list]}
        return False, {"kind": "or", "branches": [d for _, d in met_list]}
    if kind == "and":
        met_list = [evaluate(c, done) for c in node[1]]
        if any(m is False for m, _ in met_list):
            return False, {"kind": "and", "branches": [d for _, d in met_list]}
        if all(m is True for m, _ in met_list):
            return True, {"kind": "and", "branches": [d for _, d in met_list]}
        return None, {"kind": "and", "branches": [d for _, d in met_list]}
    if kind == "count":
        n = node[1]
        codes = [norm_code(c) for c in node[2]]
        n_true = sum(c in done for c in codes)
        return (n_true >= n), {"kind": "count", "n": n, "codes": codes,
                               "satisfied": n_true}
    if kind == "leaf":
        codes = [norm_code(c) for c in node[1]]
        met = all(c in done for c in codes)
        return met, {"kind": "leaf", "codes": codes, "met": met}
    return None, {"kind": "text"}


def eval_note(note: str, done: set):
    """Note 原文 + 已满足课程码集合 → (met: bool|None, tree)。
    done 元素为规范化课号（如 'COMP1991'）。"""
    return evaluate(parse(note), done)


def shape(node) -> str:
    """表达式树 → 紧凑形状串（写入 buckets[].note_semantics，供复核）"""
    kind = node[0]
    if kind in ("or", "and"):
        return f"{kind}[{'|'.join(shape(c) for c in node[1])}]"
    if kind == "count":
        return f"count({node[1]} of {len(node[2])})"
    if kind == "leaf":
        return f"leaf({len(node[1])})"
    return "text"


if __name__ == "__main__":
    import sys
    tests = [
        ("Note: [COMP 1991 AND (COMP 4981 OR COMP 4981H)] OR [COMP 4910]",
         {"COMP1991", "COMP4981"}, True),
        ("Note: [COMP 1991 AND (COMP 4981 OR COMP 4981H)] OR [COMP 4910]",
         {"COMP1991"}, False),
        ("Note: [COMP 1991 AND (COMP 4981 OR COMP 4981H)] OR [COMP 4910]",
         {"COMP4910"}, True),
        ("Note: (COMP 2011 AND COMP 2012) OR COMP 2012H", {"COMP2011"}, False),
        ("Note: (COMP 2011 AND COMP 2012) OR COMP 2012H",
         {"COMP2011", "COMP2012H"}, True),
        ("any 2 of MATH 1013, MATH 1023, MATH 2011", {"MATH1013", "MATH1023"},
         True),
        ("any 2 of MATH 1013, MATH 1023, MATH 2011", {"MATH1013"}, False),
        ("Students with credit in COMP 2011 may reuse it", {"COMP2011"}, True),
    ]
    fail = 0
    for note, done, want in tests:
        met, tree = eval_note(note, done)
        ok = met is want
        fail += 0 if ok else 1
        print(f"  [{'OK' if ok else 'FAIL'}] {shape(parse(note)):18} "
              f"met={met} want={want}  {note[:60]!r}")
    print("selftest:", "PASS" if fail == 0 else f"FAIL ({fail})")
    sys.exit(1 if fail else 0)
