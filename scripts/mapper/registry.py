#!/usr/bin/env python3
"""
映射覆盖规则注册表 — mapper/registry.py
=======================================
加载 database/mappings/{PROG}.json 中的人工/数据规则，优先级最高。

覆盖规则 schema（见 templates/schemas/mapping_overrides.schema.json）:
{
  "program": "PHYS",
  "intake_year": "2026-27",
  "overrides": [
    {
      "match": {"ar_group_regex": "^PHYS Required Course \\(Part 1\\)$"},
      "map_to": {"section": "required", "block": "major"},
      "note": "SIS 把 Required 拆成 Part 1/2，PDF 是同一块"
    }
  ]
}
"""

import json
import re
from pathlib import Path


def load_overrides(program: str, mappings_dir) -> list:
    p = Path(mappings_dir) / f"{program}.json"
    if not p.exists():
        return []
    try:
        ov = json.loads(p.read_text(encoding="utf-8")).get("overrides") or []
        return ov if isinstance(ov, list) else []
    except (json.JSONDecodeError, KeyError, AttributeError):
        return []


def find_override(program: str, mappings_dir, ar_group_name: str):
    """按 AR 组名正则匹配覆盖规则，命中返回 rule dict，否则 None"""
    for rule in load_overrides(program, mappings_dir):
        rgx = rule.get("match", {}).get("ar_group_regex", "")
        if rgx and re.match(rgx, ar_group_name):
            return rule
    return None


def select_by_override(rule: dict, flattened_entries) -> list:
    """按覆盖规则定位 curriculum 条目：map_to.section / block / note 关键词"""
    mt = rule.get("map_to", {})
    want_sec = mt.get("section")
    want_block = mt.get("block")
    want_note = mt.get("note_regex", "")
    hits = []
    for e in flattened_entries:
        if want_block and e["block"] != want_block:
            continue
        if want_sec and e["section"] != want_sec:
            continue
        if want_note and not re.search(want_note, e.get("note") or ""):
            continue
        hits.append(e)
    return hits
