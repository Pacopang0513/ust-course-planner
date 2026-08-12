#!/usr/bin/env python3
"""
未修清单生成（bucket 化）— scripts/rank/buckets.py
===================================================
Step 1：专业必修 + 今年可读 CC − 已修 − 预选课 = 未修清单，按"栏位/bucket"分组。

bucket 划分（新工作流核心：不同栏位并列评分，不再混在一起）：
  - major_required：必修/基础/pre-major 每门课一个 bucket（quota=1）；
    必修 pool（如 "PHYS 1111 OR PHYS 1112 OR PHYS 1312"）→ 一个 bucket，
    quota 按 note 中 "any N of" 解析（默认 1）
  - major_elective：选修每个 pool 一个 bucket（quota 同 note 解析，默认 1）
  - cc_required / cc_elective：Common Core 每个区域（A/H/S/T/SA/SUS/HAIC…）一个
    bucket；区域页课程全部入桶
  - free_elective：其他（"other" section 归 major_elective；无独立 free 源）

其它规则（新工作流）：
  - track/option 过滤：curriculum 存在 track/option 块时必须指定 --track
    （不指定即报错并列可选列表）；指定 "NONE" 表示无 track（只保留 major 块）
  - pre-req 引用补录：major_required 课程的 pre-req（对照本学年 schedule 的
    PRE-REQUISITE 属性）若既不在未修清单也不在已修清单 → 补录入清单并标记
    prereq_reference=true（仅参考；不参与评分与排课；选修不考虑此规则）
  - 已修（passed，含 transferred/exempted/audit）与预选课（pre_enrolled，
    confirmed+pending）直接扣除
  - 课程码清洗：跳过非 "[A-Z]{2,4} \\d{4}[A-Z]?" 格式的脏条目（prog-crs
    解析残留，如 COMP.json 的 "MATH 2540" + "OR MATH 2411..."）

用法:
  python3 scripts/rank/buckets.py --profile data/profile.json --session <SESSION> \
      --track "Physics and Mathematics"
  python3 scripts/rank/buckets.py --profile data/profile.json --session <SESSION> --track NONE
  python3 scripts/rank/buckets.py --profile data/profile.json --session <SESSION> \
      --track NONE --passed data/passed_courses.json --pre-enrolled data/pre_enrolled.json
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "rank"))
sys.path.insert(0, str(ROOT / "scripts"))

from filter import RE_CODE, passed_set  # noqa: E402  （复用 pre-req 代码提取与已修集合）

from harness.config import load as load_config  # noqa: E402
from harness.config import semester_of_session  # noqa: E402 （学期语义唯一权威）

import note_eval  # noqa: E402  （Note 表达式解析/求值：AND/方括号/any N of）

RE_VALID_CODE = re.compile(r"^[A-Z]{2,4}\s+\d{4}[A-Z]?$")
# 'Any N of' / 'Any N courses of'（2026-08 修复：'Any 3 courses of' 此前不匹配 → quota=1）
RE_ANY_N = re.compile(r"any\s+(\d+)\s+(?:courses?\s+)?of", re.I)
# 描述性级别池：'MATH 2000-level or above Electives' → subject+最低千位
RE_LEVEL_POOL = re.compile(r"([A-Z]{3,4})\s+(\d)000[- ]level or above", re.I)
CC_REQUIRED_MARKERS = ("(HAIC)", "(HMW)", "(E-Comm)", "(C-Comm)", "(CTDL)")
CC_UXOP_MARKERS = ("UxOP", "UROP", "UTOP", "UPOP", "UCOP")
COURSE_NOTES_DIR = ROOT / "database" / "course_notes"


def load_course_notes() -> dict:
    """database/course_notes/*.json → {norm_code: {tags[], note, rules}}。
    无目录/文件时返回空 dict（规则跳过，不阻塞）。"""
    out = {}
    if not COURSE_NOTES_DIR.exists():
        return out
    for p in sorted(COURSE_NOTES_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            print(f"提示: course_notes {p} 解析失败，跳过")
            continue
        for code, tags in (d.get("tags") or {}).items():
            out.setdefault(norm_code(code), {}).setdefault("tags", []).extend(tags)
        for code, note in (d.get("notes") or {}).items():
            out.setdefault(norm_code(code), {})["note"] = note
    return out


def apply_course_notes_rules(courses: list, buckets: list, first_major: str):
    """消费 database/course_notes/ 的课程语义规则（防 AI/脚本误配，全脚本化）。

    ext_capstone_pairing：EXT AI 顶点二选一（EMIA 4990/4991）——学生 first_major
    必修中含 major_capstone 标记课程（如 PHYS 4291）→ 只允许 EMIA 4990
    （0 学分，与主修 FYP 并行），移除 4991；无主修 FYP 才可选 4991。
    """
    notes = load_course_notes()
    if not notes:
        return
    major_caps = {norm_code(c["code"]) for c in courses
                  if c.get("category") == "major_required"
                  and "major_capstone" in (notes.get(norm_code(c["code"]), {}).get("tags") or [])}
    if not major_caps:
        return
    for b in buckets:
        if b.get("category") != "major_required" or "pool" not in b.get("bucket_id", ""):
            continue
        in_bucket = [c for c in courses if c.get("bucket_id") == b["bucket_id"]]
        pair = [c for c in in_bucket
                if norm_code(c["code"]) in ("EMIA4990", "EMIA4991")]
        if not pair:
            continue
        dropped = [c for c in in_bucket if norm_code(c["code"]) == "EMIA4991"]
        if dropped:
            b["quota"] = 1
            b["note"] = (b.get("note", "") +
                         " | 规则: 主修含顶点课程（如 PHYS 4291）→ 仅 EMIA 4990 可选"
                         f"（{', '.join(sorted(major_caps))}）")
            for c in dropped:
                courses.remove(c)
            print(f"  - ext 顶点池 {b['bucket_id']}: 主修含顶点课程 → 移除 EMIA 4991，"
                  f"仅保留 EMIA 4990（规则来源 database/course_notes/）")


def load_json(p: Path) -> dict:
    if not p.exists():
        sys.exit(f"错误: 找不到 {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def norm_code(s: str) -> str:
    return re.sub(r"[\s.]+", "", str(s)).upper()


def _credits_num(v) -> float:
    """curriculum 的 credits 可能是 '3' / '3-4' / '4-6*' → 取最小值（保守）"""
    if v is None:
        return None
    m = re.match(r"(\d+(?:\.\d+)?)", str(v))
    return float(m.group(1)) if m else None


def estimate_semesters_left(year_of_study, session: str) -> int:
    """估算剩余学期数（4 年制 8 个主学期，含当前学期）。

    - year_of_study 缺失/越界 → 返回 0（无法估算，调用方降级提示）
    - 当前是学年内第几个主学期由 config semesters 映射判定（2026-08 实测
      wcq 编码：Fall=10、Winter=20、Spring=30、Summer=40）：
      Fall/Winter 归第 1 主学期段，Spring/Summer 归第 2 主学期段
      （Winter/Summer 为可选短学期，不增加主学期计数）。
    例：大三上学期（第 5 主学期）→ 剩 4 个主学期。
    """
    try:
        y = int(year_of_study or 0)
    except (TypeError, ValueError):
        return 0
    if y < 1 or y > 4:
        return 0
    sem = semester_of_session(session)
    term_pos = 2 if sem in ("Spring", "Summer") else 1
    current = (y - 1) * 2 + term_pos
    return max(1, 8 - current + 1)


def _group_quota(note: str) -> int:
    """note 中选修/必修池的数量语义：'any N of' / 'N courses out of M' /
    'N courses from the specified list' → N；默认 1（2026-08 加固：
    学院 School Requirement 池常见 '8 courses from ...' 表述，此前被误判为 1）。"""
    m = RE_ANY_N.search(note or "")
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s+(?:courses?|of)\s+out\s+of", note or "", re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s+courses?\s+from\s+(?:the\s+)?", note or "", re.I)
    return int(m.group(1)) if m else 1


RE_NOTE_CODE = re.compile(
    r"\b([A-Z]{3,4})\s+(\d{4}[A-Z]?)(?!\s*(?:-\s*level|or\s+above|or\s+below|"
    r"and\s+above|or\s+equivalent))",
    re.I)
RE_CAN_ONLY_USE = re.compile(
    r"can only use\s+((?:[A-Z]{3,4}\s+\d{4}[A-Z]?(?:\s+OR\s+)?)+)\s+to fulfill",
    re.I)


def _note_courses(note: str) -> list:
    """从 group note 提取课程码（OR 列表中的课程可能不在 courses[] 中，
    如 'MATH 2111 OR MATH 2121 OR MATH 2131' 只列了 2111/2131）。
    负向前瞻排除描述性课号（'COMP 2000-level' / '2000 or above' → 不提取，
    防 COMP 2000 这类假课混入清单——2026-08 实测 COSC 选修池）。"""
    return [f"{a} {b}" for a, b in RE_NOTE_CODE.findall(note or "")]


def track_only_use(note: str, track: str) -> list:
    """note 中针对所选 track 的 'can only use X to fulfill' 限制 → 限定课程码。
    例：'... those taking Honors Physics Option can only use PHYS 4291 to fulfill
    the requirement.' → ['PHYS 4291']。无匹配返回 []（表示不限制）。"""
    if not track or track.upper() in ("NONE", "-"):
        return []
    low = (note or "").lower()
    for m in RE_CAN_ONLY_USE.finditer(note or ""):
        if track.lower() in low[:m.start()]:
            return [f"{a} {b}" for a, b in RE_NOTE_CODE.findall(m.group(1))]
    return []


# ── CC 区域满足性（全脚本化，无 AI 判断）──────────────────────────

RE_PAREN = re.compile(r"\(([^()]+)\)")

# CC 区域码 → AR 组名关键词（区域码 20-32 为 4Y/CC22/CC25/CC26 通用；SUS 等新区域同构）
AR_GROUP_OF_AREA = {
    "20": "Foundations II", "29": "Foundations II", "30": "Foundations II",
    "31": "Foundations II", "32": "Foundations II",
    "21": "Foundations I", "22": "Foundations I", "23": "Foundations I",
    "24": "Broadening", "25": "Broadening", "26": "Broadening",
    "27": "Broadening", "28": "Broadening",
}


def _paren_code(name: str) -> str:
    m = RE_PAREN.search(name or "")
    return m.group(1) if m else ""


def apply_cc_satisfaction(buckets: list, courses: list, done: set,
                          ar: dict, code_area: dict) -> tuple:
    """CC 区域满足性判定（三层，全脚本，无 AI 判断）：
    1) 历史 CC 区域表（database/common-core/areas_{GROUP}.json）：已修课程码 → 区域，
       满足配额 → 整桶移除（解决 AR 页 S/SA 等区域不渲染明细的盲区，如
       SOSC 1969 → SA、PHYS 1007 → S）
    2) AR 条目级：区域条目 taken >= required → 整桶移除；否则标注 AR 数字
    3) AR 组级回退：条目缺失（折叠空壳，如 HMW/E-Comm/C-Comm/SA）→
       组 taken >= required 移除；否则标注组数据（保守保留）
    返回 (buckets, courses)。"""
    drop_ids, notes = set(), []
    quota = {b.get("bucket_id"): b.get("quota", 1) for b in buckets}
    labels = {b.get("bucket_id"): b.get("label", "") for b in buckets}

    if code_area:
        # 已修课程（done 为规范化码集合）→ 按规范化索引反查区域表
        code_area_norm = {norm_code(c): a for c, a in code_area.items()}
        taken_in = {}
        for code in done:
            area = code_area_norm.get(code)
            if area:
                taken_in[area] = taken_in.get(area, 0) + 1
        for b in buckets:
            bid = b.get("bucket_id", "")
            if not bid.startswith("cc-"):
                continue
            area = bid[3:]
            n = taken_in.get(area, 0)
            if n >= quota.get(bid, 1):
                drop_ids.add(bid)
                notes.append(f"{bid}: 历史 CC 池确认已修 {n} 门 → 区域满足")
            elif n:
                notes.append(f"{bid}: 历史 CC 池已修 {n} 门（未达配额 {quota.get(bid, 1)}）")

    if ar:
        ar_items = [(it, g) for g in ar.get("requirement_groups", [])
                    for it in (g.get("items") or [])]
        for b in buckets:
            bid = b.get("bucket_id", "")
            if not bid.startswith("cc-"):
                continue
            area = bid[3:]
            label = labels.get(bid, "")
            item = next((it for it, _ in ar_items
                         if _paren_code(it.get("name", "")) == _paren_code(label)
                         and not it.get("name", "").startswith("Verification on")), None)
            group_name = AR_GROUP_OF_AREA.get(area, "")
            group = next((g for g in ar.get("requirement_groups", [])
                          if group_name and group_name in g.get("name", "")), None)
            if item and item.get("units"):
                u = item["units"]
                if u.get("taken", 0) >= u.get("required", 0):
                    drop_ids.add(bid)
                    notes.append(f"{bid}: AR 条目满足（{u['taken']}/{u['required']}）")
                else:
                    notes.append(f"{bid}: AR 条目未满足（需 {u['required']} 已修 {u['taken']}）")
            elif group and group.get("units"):
                u = group["units"]
                if u.get("taken", 0) >= u.get("required", 0):
                    drop_ids.add(bid)
                    notes.append(f"{bid}: AR 组满足（{u['taken']}/{u['required']}，条目未渲染）")
                else:
                    notes.append(f"{bid}: AR 组未满足（需 {u['required']} 已修 {u['taken']}，条目未渲染）")
            else:
                notes.append(f"{bid}: AR 无区域数据（保守保留）")

    if drop_ids:
        print("CC 区域满足性（脚本判定，无 AI 判断）整桶移除:")
        for bid in sorted(drop_ids):
            print(f"  - {bid}: {labels.get(bid, '')}")
        buckets = [b for b in buckets if b.get("bucket_id") not in drop_ids]
        courses = [c for c in courses if c.get("bucket_id") not in drop_ids]
    for n in notes:
        print(f"  ~ {n}")
    return buckets, courses


def _sanitize_course(c: dict) -> dict | None:
    """清洗 prog-crs 解析残留：code 必须合法；title/credits 泄漏（含 ' OR '）
    视为脏条目丢弃。"""
    code = str(c.get("code", "")).strip()
    if not RE_VALID_CODE.match(code):
        return None
    title = str(c.get("title", "")).strip()
    if not title or " OR " in title or re.match(r"^[A-Z]{2,4}\s+\d{4}[A-Z]?\s+OR", title):
        return None
    return {"code": code, "name": title,
            "credits": _credits_num(c.get("credits")),
            "area": str(c.get("area", "") or "")}


def available_tracks(prog: dict) -> list:
    return [b.get("name", "") for b in prog.get("requirements", [])
            if b.get("block") in ("track", "option")]


def filter_blocks(prog: dict, track: str) -> list:
    """--track 过滤：保留 major 块 + 匹配的 track/option 块。
    track 含 'NONE'/'none'/'-' → 只保留 major 块。无 track/option 块 → 全部保留。"""
    blocks = prog.get("requirements", [])
    alt = [b for b in blocks if b.get("block") in ("track", "option")]
    if not alt:
        return blocks
    if not track:
        sys.exit("错误: 该专业存在 track/option 分支，必须指定 --track"
                 f"（可用: {', '.join(available_tracks(prog))}；无分支用 NONE）")
    if track.upper() in ("NONE", "-"):
        return [b for b in blocks if b.get("block") == "major"]
    matched = [b for b in blocks
               if b.get("block") == "major"
               or (b.get("block") in ("track", "option")
                   and track.lower() in str(b.get("name", "")).lower())]
    if len(matched) == len([b for b in blocks if b.get("block") == "major"]):
        sys.exit(f"错误: --track '{track}' 未匹配任何 track/option 块"
                 f"（可用: {', '.join(available_tracks(prog))}；无分支用 NONE）")
    return matched


def major_buckets(blocks: list, track: str = "", prefix: str = "major",
                  sched_idx: dict = None) -> tuple:
    """curriculum 块/节/组 → 未修 courses（bucket 化）。
    返回 (courses, buckets_meta)。track 用于解析 note 中的 'can only use X' 限制；
    prefix 区分来源（major=主修 / ext=扩展主修 / add{CODE}=第二主修 / school=学院），
    避免 bucket_id 冲突；sched_idx（本学年课表 {code: course}）用于描述性级别池
    （'MATH 2000-level or above'）从真实课表生成候选。"""
    courses, buckets = [], []
    seq = 0
    required_codes = set()  # 必修已占课码（级别池生成时排除，防必修课混入选修池）
    for block in blocks:
        for section in block.get("sections", []):
            stype = section.get("type", "other")
            category = ("major_required" if stype in ("pre_major", "fundamental", "required")
                        else "major_elective")
            # 预扫描：同 section 同 subject 的嵌套级别池（'MATH 2000-level or above' +
            # 'MATH 3000-level ...'）→ 只处理最低 level 池（候选最全），其余跳过
            # （2026-08 修复：多级别池互相抢占候选导致后池被抢空 + 独立配额超算）
            level_groups = {}
            for gi, group in enumerate(section.get("groups", [])):
                lm = RE_LEVEL_POOL.search(str(group.get("note") or ""))
                if lm:
                    key = (lm.group(1).upper(), str(section.get("name", "")))
                    cur = level_groups.get(key)
                    if cur is None or int(lm.group(2)) < cur[0]:
                        level_groups[key] = (int(lm.group(2)), gi)
            keep_gi = {gi for _, gi in level_groups.values()}
            for gi, group in enumerate(section.get("groups", [])):
                group_note = str(group.get("note") or "")
                lm = RE_LEVEL_POOL.search(group_note)
                if lm and gi not in keep_gi:
                    print(f"  ~ 嵌套级别池 {lm.group(1).upper()} {lm.group(2)}000-level "
                          f"or above：已并入同栏位最低级别池，跳过（quota 明细见 note，"
                          f"P3 复核）")
                    continue
                group_courses = [c for c in (_sanitize_course(c)
                                             for c in group.get("courses", []))
                                 if c is not None]
                group_note = str(group.get("note") or "")
                # 描述性级别池（'MATH 2000-level or above'，prog-crs 不列具体课程；
                # note 中的课码多为特例说明如 'COMP 4981 or COMP 4981H'）：
                # 优先从本学年课表生成真实候选（限定 subject + 课号千位 ≥ N，
                # 排除已被必修占用的课——防 subject 混入与必修重复推荐）。
                # 2026-08 修复：此前空池直接跳过，MATH/COSC 专业选修整组静默缺失。
                lm_pool = RE_LEVEL_POOL.search(group_note)
                if lm_pool and group.get("kind") == "pool" and sched_idx:
                    lsubj, lmin = lm_pool.group(1).upper(), int(lm_pool.group(2))
                    group_courses = []
                    for code, sc in sorted(sched_idx.items()):
                        csubj, _, cnum = code.partition(" ")
                        if csubj.upper() != lsubj:
                            continue
                        nm = re.match(r"(\d{4})", str(cnum or ""))
                        if not nm or int(nm.group(1)) // 1000 < lmin:
                            continue
                        if norm_code(code) in required_codes:
                            continue
                        group_courses.append({
                            "code": code, "name": sc.get("title", ""),
                            "credits": sc.get("units"), "area": ""})
                    if group_courses:
                        print(f"  ~ 级别池 {lsubj} {lmin}000-level or above: "
                              f"从本学年课表生成 {len(group_courses)} 门候选")
                # 池 note 中引用但未列出的课程码（如 OR 列表折行）补入
                elif group.get("kind") == "pool" and group.get("note"):
                    for extra in _note_courses(group.get("note")):
                        if extra not in [c["code"] for c in group_courses]:
                            group_courses.append({"code": extra, "name": "",
                                                  "credits": None, "area": ""})
                if not group_courses:
                    # 空组显式警告（防静默漏读整组要求；描述性池如
                    # "COMP 2000-level or above [Any 6 courses]" 无真实课程列表）
                    gsubj = group.get("subject") or ""
                    gsubj_txt = f"/{gsubj}" if gsubj else ""
                    print(f"  ! 跳过空课程组: {block.get('name', '')}/"
                          f"{section.get('name', '')}{gsubj_txt}"
                          f" —— note 无真实课程码（{group_note[:60]}），"
                          f"若为真实要求需人工补全 curriculum 课程列表")
                    continue
                # track 限制（'can only use X'）：只保留限定的课程码
                only_use = track_only_use(group.get("note", ""), track)
                if only_use:
                    group_courses = [c for c in group_courses if c["code"] in only_use]
                    if not group_courses:
                        continue
                    print(f"  ~ track 限制 {block.get('name', '')}/{section.get('name', '')}: "
                          f"仅 {', '.join(only_use)}")
                # 去重（规范化课号）
                seen, uniq = set(), []
                for c in group_courses:
                    if norm_code(c["code"]) in seen:
                        continue
                    seen.add(norm_code(c["code"]))
                    uniq.append(c)
                kind = group.get("kind", "pool")
                note = str(group.get("note", "") or "")
                # 级别池强制走 pool 分支（quota 按 note 的 any N；单门候选也不能
                # 退化为 quota=1 单桶——'Any 6 courses' 语义不变）
                if kind == "single" or (len(uniq) == 1 and not lm_pool):
                    for c in uniq:
                        bid = f"{prefix}-{stype}-{seq}"
                        seq += 1
                        courses.append({
                            "code": c["code"], "name": c["name"],
                            "credits": c["credits"], "category": category,
                            "bucket_id": bid, "bucket_quota": 1,
                            "source_groups": [{
                                "block": block.get("name", ""),
                                "section": section.get("name", ""),
                                "group": group.get("subject", ""),
                                "note": note,
                            }],
                            "note_interpretation": note,
                            "prereq_reference": False,
                        })
                        if category == "major_required":
                            required_codes.add(norm_code(c["code"]))
                        buckets.append({"bucket_id": bid, "label": c["code"],
                                        "category": category, "quota": 1,
                                        "note": note})
                else:
                    bid = f"{prefix}-{stype}-pool-{seq}"
                    seq += 1
                    quota = _group_quota(note)
                    # pool label：单课程池直接用课号；多课程池 subject 需与
                    # 池内课程前缀匹配才用（ext 选修池 subject 可能是 SHSS 等
                    # 旧元数据，与内容不符 → 用 section 名）
                    subj = group.get("subject", "").strip()
                    codes = [c["code"] for c in uniq]
                    subj_matches = any(code.split()[0] == subj for code in codes)
                    if len(uniq) == 1:
                        label = uniq[0]["code"]
                    elif subj and subj_matches:
                        label = subj
                    else:
                        label = (section.get("name") or block.get("name") or bid)
                    for c in uniq:
                        courses.append({
                            "code": c["code"], "name": c["name"],
                            "credits": c["credits"], "category": category,
                            "bucket_id": bid, "bucket_quota": quota,
                            "source_groups": [{
                                "block": block.get("name", ""),
                                "section": section.get("name", ""),
                                "group": group.get("subject", ""),
                                "note": note,
                            }],
                            "note_interpretation": note,
                            "prereq_reference": False,
                        })
                        if category == "major_required":
                            required_codes.add(norm_code(c["code"]))
                    buckets.append({"bucket_id": bid, "label": label,
                                    "category": category, "quota": quota, "note": note})
    return courses, buckets


def cc_buckets(cc_pool: dict) -> tuple:
    """cc_courses_{session}.json 区域 → 未修 courses + buckets（每区一个 bucket）。
    基础层（HAIC/HMW/E-Comm/C-Comm/CTDL）→ cc_required；其余（A/H/S/T/SA/SUS/UxOP）→ cc_elective。
    UxOP 区域（UROP/UTOP/UPOP/UCOP）刻意跳过：该 3 学分由其他 CC 课程替代，
    不生成 bucket、不参与排课（用户规则，2026-08）。"""
    courses, buckets = [], []
    for area in cc_pool.get("areas", []):
        label = str(area.get("area", ""))
        if any(m in label for m in CC_UXOP_MARKERS):
            print(f"  - cc 区域 {label} 跳过（UxOP 由其他 CC 替代，不排课）")
            continue
        category = ("cc_required"
                    if any(m in label for m in CC_REQUIRED_MARKERS) else "cc_elective")
        bid = f"cc-{area.get('area_code', '')}"
        area_courses = []
        for c in area.get("courses", []):
            code = f"{c.get('code', '')} {c.get('number', '')}".strip()
            if not RE_VALID_CODE.match(code):
                continue
            area_courses.append({
                "code": code, "name": c.get("title", ""),
                "credits": c.get("units"), "category": category,
                "bucket_id": bid, "bucket_quota": 1,
                "source_groups": [{"block": "common_core", "section": "cc",
                                   "group": label, "note": label}],
                "note_interpretation": label,
                "prereq_reference": False,
            })
        if not area_courses:
            continue
        courses.extend(area_courses)
        buckets.append({"bucket_id": bid, "label": label, "category": category,
                        "quota": 1, "note": label})
    return courses, buckets


def add_prereq_references(courses: list, passed: set, sched_idx: dict) -> list:
    """必修课 pre-req 引用补录：pre-req 课程既不在未修清单也不在已修清单 → 补入
    （prereq_reference=true，仅参考）。选修（major_elective 及以下）不适用。"""
    existing = {norm_code(c["code"]) for c in courses}
    refs, seen = [], set()
    for c in courses:
        if c["category"] != "major_required" or c.get("prereq_reference"):
            continue
        sc = sched_idx.get(c["code"])
        pre = (sc.get("attributes") or {}).get("PRE-REQUISITE", "") if sc else ""
        for a, b in RE_CODE.findall(pre):
            code = f"{a} {b}"
            key = norm_code(code)
            if key in existing or key in passed or key in seen:
                continue
            seen.add(key)
            sc2 = sched_idx.get(code)
            refs.append({
                "code": code,
                "name": sc2.get("title", "") if sc2 else "",
                "credits": sc2.get("units") if sc2 else None,
                "category": "major_required",
                "bucket_id": f"prereq-ref-{norm_code(c['code'])}",
                "bucket_quota": 1,
                "source_groups": [{
                    "block": "prereq_reference",
                    "section": f"pre-req of {c['code']}",
                    "group": pre,
                    "note": pre,
                }],
                "note_interpretation": "pre-req 参考课程（未在未修/已修清单中）",
                "prereq_reference": True,
            })
    if refs:
        print("pre-req 引用补录（仅参考，不参与评分/排课）:")
        for r in refs:
            print(f"  - {r['code']}  (pre-req of {r['source_groups'][0]['section']})")
    return courses + refs


def main():
    ap = argparse.ArgumentParser(description="未修清单生成（bucket 化，Step 1）")
    ap.add_argument("--profile", default=str(ROOT / "data" / "profile.json"))
    ap.add_argument("--session", default="", help="学期代码，对应 data/courses_{session}.json")
    ap.add_argument("--track", default="",
                    help="所选 track/option 块名（无分支用 NONE；存在分支时必须指定）")
    ap.add_argument("--passed", default=str(ROOT / "data" / "passed_courses.json"))
    ap.add_argument("--pre-enrolled", default=str(ROOT / "data" / "pre_enrolled.json"),
                    help="SIS 预选课（可选，缺省视为无）")
    ap.add_argument("--curriculum-dir", default="",
                    help="curriculum 目录（默认 database/curriculum/{admission_year}）")
    ap.add_argument("--ar", default="",
                    help="SIS AR 产物（默认 cache/sis/sis_academic_req.json，存在即用）")
    ap.add_argument("--cc-areas", default="",
                    help="历史 CC 区域表（默认 database/common-core/areas_{group}.json，存在即用）")
    ap.add_argument("--output", default=str(ROOT / "data" / "unmet_courses.json"))
    args = ap.parse_args()
    if not args.session:
        sys.exit("错误: 缺少 --session（学期代码；运行中的学期可由 ustplan status 查询）")

    profile = load_json(Path(args.profile))
    admission_year = profile.get("admission_year", "").strip()
    # 硬性以入学年份检索（2026-08 开发要求）：缺失/非法即报错，禁止回退到
    # 当前学年——major curriculum / Common Core 组 / 历史 CC 区域表全部按
    # 入学年份决定，用错年份会导致课程要求与 CC 框架错配
    if not re.match(r"^\d{4}-\d{2}$", admission_year):
        sys.exit(f"错误: profile.admission_year 缺失或非法（{admission_year!r}），"
                 f"无法按入学年份定位 curriculum 与 CC 版本（先完成 phase2-profile）")
    first_major = ((profile.get("programs") or {}).get("first_major") or "").strip()
    if not first_major:
        sys.exit("错误: profile.programs.first_major 为空（请先完成 phase2-profile）")
    cur_dir = Path(args.curriculum_dir) if args.curriculum_dir \
        else ROOT / "database" / "curriculum" / admission_year
    cur_file = cur_dir / f"{first_major}.json"
    if not cur_file.exists():
        sys.exit(f"错误: 本地 curriculum 缺失 {cur_file}"
                 f"（先跑 scripts/prog_crs/build.py --year {admission_year} 重建；"
                 f"2022-23 及更早 prog-crs 已下线无法重建，AR 回退仅人工工具）")
    prog = load_json(cur_file)

    # 副修（minor）：P1 显式收集（数组，[]=没有，可多个）。此处仅校验 curriculum
    # 存在并提示（记录用途）；合并 minor 必修桶为二期增强。
    minors = ((profile.get("programs") or {}).get("minor") or [])
    if isinstance(minors, str):
        minors = [minors]
    minors = [m.strip().upper() for m in minors if m and str(m).strip().upper() != "NA"]
    for m in minors:
        mfile = cur_dir / f"{m}.json"
        if not mfile.exists():
            print(f"提示: 副修 {m} 的本地 curriculum 缺失 {mfile}"
                  f"（可跑 scripts/prog_crs/build.py --year {admission_year}；"
                  f"副修暂不参与排课，仅记录）")
        else:
            print(f"副修 {m}: curriculum 已就绪（暂不合并排课，二期增强）")

    # SIS AR 产物（CC 区域判定 + 扩展主修过滤的权威来源）
    ar = None
    ar_path = Path(args.ar) if args.ar else \
        ROOT / "cache" / "sis" / "sis_academic_req.json"
    if ar_path.exists():
        ar = load_json(ar_path)
    else:
        print(f"提示: 未找到 SIS AR 产物 {ar_path}（SIS AR 判定跳过）")

    blocks = filter_blocks(prog, args.track)
    # 本学年课表索引（级别池生成 + pre-req 引用补录共用；缺失仅提示）
    sched_path = ROOT / "data" / f"courses_{args.session}.json"
    sched_idx = {}
    if sched_path.exists():
        sched_idx = {f"{c.get('code', '')} {c.get('number', '')}".strip(): c
                     for c in load_json(sched_path).get("courses", [])}
    else:
        print(f"提示: 未找到 {sched_path}（级别选修池无法从课表生成，pre-req 补录跳过）")
    courses, buckets = major_buckets(blocks, args.track, sched_idx=sched_idx)

    # 学院 School Requirement（SREQ-{SCHOOL}.json，如 SREQ-SENG）：学校级要求
    # （如 SENG 入门课 + TC I）并入清单。若课程已存在于专业课程（如 COMP 的
    # fundamental 已含 SENG 池）→ 去重跳过，防重复推荐；AR 为权威兜底。
    school = ((profile.get("school") or "").strip().upper() or "")
    if school:
        sreq_file = cur_dir / f"SREQ-{school}.json"
        if sreq_file.exists():
            sreq_prog = load_json(sreq_file)
            sc, sb = major_buckets(sreq_prog.get("requirements", []), "",
                                   prefix="school", sched_idx=sched_idx)
            existing = {norm_code(c["code"]) for c in courses}
            dup = [c for c in sc if norm_code(c["code"]) in existing]
            sc = [c for c in sc if norm_code(c["code"]) not in existing]
            if dup:
                print(f"School Requirement ({school}): 跳过与专业课程重复 "
                      f"{len(dup)} 门（{', '.join(sorted({c['code'] for c in dup})[:8])}）")
            keep_bids = {c["bucket_id"] for c in sc}
            sb = [b for b in sb if b["bucket_id"] in keep_bids]
            courses.extend(sc)
            buckets.extend(sb)
            if sc:
                print(f"School Requirement ({school}): 合并 {len(sc)} 门"
                      f"（{len(sb)} 个 bucket）")
            else:
                print(f"School Requirement ({school}): 全部由专业课程覆盖")
        else:
            print(f"提示: 学院 {school} 的 School Requirement 预构建缺失 {sreq_file}"
                  f"（可能该学年无此要求，如 SENG 2025-26 起取消 SENG 入门课；"
                  f"以 SIS AR 判定为准）")

    # 第二主修（additional_major，2026-08 支持多主修：COSC+MATH 等双主修）：
    # 合并其 major 块要求；track/option 分支暂按无分支处理（major 块全保留，
    # 提示说明）；bucket_id 用 add{CODE} 前缀防与第一主修冲突。
    add_majors = [m.strip().upper()
                  for m in ((profile.get("programs") or {}).get("additional_major") or [])
                  if m and str(m).strip().upper() != "NA"]
    for m in add_majors:
        afile = cur_dir / f"{m}.json"
        if not afile.exists():
            print(f"提示: 第二主修 {m} 的本地 curriculum 缺失 {afile}"
                  f"（跳过；可跑 scripts/prog_crs/build.py --year {admission_year}）")
            continue
        aprog = load_json(afile)
        ab = filter_blocks(aprog, "NONE")
        ac, abk = major_buckets(ab, "", prefix=f"add{m}", sched_idx=sched_idx)
        if ac:
            courses.extend(ac)
            buckets.extend(abk)
            print(f"第二主修 {m}: 合并 {len(ac)} 门（{len(abk)} 个 bucket；"
                  f"track 分支暂按无分支处理）")
        else:
            print(f"第二主修 {m}: curriculum 已加载，无未修课程")

    # 扩展主修（EXTM-*）：合并其要求桶；有 AR 时按 AR not_taken 名单过滤
    # （AR 权威：等效课已由 AR 引擎判定满足，未满足课程才进未修清单）
    ext_major = ((profile.get("programs") or {}).get("extended_major") or "").strip()
    if ext_major:
        ext_file = cur_dir / f"EXTM-{ext_major}.json"
        if ext_file.exists():
            ext_prog = load_json(ext_file)
            ext_courses, ext_buckets = major_buckets(ext_prog.get("requirements", []), "",
                                                     prefix="ext", sched_idx=sched_idx)
            ar_not_taken = None
            if ar:
                ar_not_taken = {norm_code(c["code"])
                                for g in ar.get("requirement_groups", [])
                                for c in g.get("courses", [])
                                if c.get("status") == "not_taken"}
            if ar_not_taken is not None:
                before = len(ext_courses)
                ext_courses = [c for c in ext_courses
                               if norm_code(c["code"]) in ar_not_taken]
                print(f"扩展主修 {ext_major}: 按 AR not_taken 过滤 "
                      f"{before} → {len(ext_courses)} 门")
                # 选修配额取自 AR 条目（Option A: 9 学分 / Option B: 6 学分 → 3 门）
                for g in ar.get("requirement_groups", []):
                    want = None
                    for it in (g.get("items") or []):
                        if "Elective" in it.get("name", "") and it.get("units"):
                            want = max(1, round(it["units"]["required"] / 3))
                            break
                    if want is None and "Elective" in g.get("name", ""):
                        cm = [float(x) for x in (g.get("credits_mentioned") or [])
                              if str(x).replace(".", "", 1).isdigit()]
                        if cm:
                            want = max(1, round(max(cm) / 3))
                    if want:
                        for b in ext_buckets:
                            if b.get("category") == "major_elective":
                                b["quota"] = max(b.get("quota", 1), want)
                                b["note"] = (b.get("note", "") +
                                             f" | AR: 选修需 {want * 3} 学分")
            courses.extend(ext_courses)
            buckets.extend(ext_buckets)
            apply_course_notes_rules(courses, buckets, first_major)
        else:
            print(f"提示: 扩展主修 curriculum 缺失 {ext_file}（跳过）")

    cc_pool_path = ROOT / "data" / f"cc_courses_{args.session}.json"
    cc_used = False
    if cc_pool_path.exists():
        cc_courses, cc_meta = cc_buckets(load_json(cc_pool_path))
        courses.extend(cc_courses)
        buckets.extend(cc_meta)
        cc_used = True
    else:
        print(f"提示: 未找到 CC 课程池 {cc_pool_path}"
              f"（先跑 scripts/wcq/crawler.py --admission-year {admission_year} --session {args.session}）")

    # 已修 / 预选课扣除
    passed = load_json(Path(args.passed)) if Path(args.passed).exists() else {"courses": []}
    done = passed_set(passed)
    pre_ar = []
    pre_path = Path(args.pre_enrolled)
    if pre_path.exists():
        pe = load_json(pre_path)
        pre_ar = [c.get("code", "") for c in pe.get("confirmed", []) + pe.get("pending", [])]
        for c in pre_ar:
            done.add(norm_code(c))

    # 预选课记录（Step 5 按 pre_enroll_boost 加权与 drop 建议的数据来源）：带 bucket 归属
    # （课程在校 curriculum/CC 池内 → 记其 bucket_id/category；否则记空桶）。
    # 预选课仍视为已确定（已计入 done，不重复推荐），此处仅登记供评分/报告使用。
    pre_codes_norm = {norm_code(c) for c in pre_ar}
    pre_enrolled_out = []
    seen_pre = set()
    for c in courses:
        cn = norm_code(c.get("code", ""))
        if cn in pre_codes_norm and cn not in seen_pre:
            seen_pre.add(cn)
            pre_enrolled_out.append({
                "code": c.get("code", ""),
                "name": c.get("name", ""),
                "credits": c.get("credits"),
                "category": c.get("category", ""),
                "bucket_id": c.get("bucket_id", ""),
                "bucket_quota": c.get("bucket_quota"),
            })
    for c in pre_ar:
        cn = norm_code(c)
        if cn not in seen_pre:
            seen_pre.add(cn)
            pre_enrolled_out.append({
                "code": c, "name": "", "credits": None,
                "category": "free_elective", "bucket_id": "",
                "bucket_quota": None,
            })
    if pre_enrolled_out:
        print("预选课（Pre-Enroll，视为已确定；评分按 pre_enroll_boost 加权）:")
        for p in pre_enrolled_out:
            print(f"  - {p['code']:12} bucket={p['bucket_id'] or '—'} "
                  f"({p['category'] or '?'})")

    # CC 区域满足性（全脚本判定：历史区域表 + AR 条目/组级；无 AI 判断）
    code_area = None
    try:
        from wcq.crawler import admission_to_group
        cc_group = admission_to_group(admission_year)
    except Exception:
        cc_group = ""
    areas_path = Path(args.cc_areas) if args.cc_areas else \
        ROOT / "database" / "common-core" / f"areas_{cc_group}.json"
    if areas_path.exists():
        code_area = load_json(areas_path).get("code_area", {})
    else:
        print(f"提示: 未找到历史 CC 区域表 {areas_path}"
              f"（先跑 scripts/wcq/cc_areas.py --admission-year {admission_year}）")
    if ar or code_area:
        buckets, courses = apply_cc_satisfaction(buckets, courses, done, ar, code_area)

    # bucket 满足性（OR 语义）：池内已修课程数 ≥ 配额 → 整桶满足，整桶移除。
    # 例：'PHYS 1111 OR PHYS 1112 OR PHYS 1312' 已修 1312 → 整桶满足；
    #     CC 区域内已修任意一门 → 该区域满足（HMW/E-Comm/C-Comm 同理）。
    # 复杂 Note（AND/方括号/any N of，如 FYP 组
    # '[COMP 1991 AND (COMP 4981 OR COMP 4981H)] OR [COMP 4910]'）→
    # 走 note_eval 表达式求值，不再用"任选一门"计数（防止只修 0 学分实习
    # 即误判整桶满足；嵌套括号/方括号不会被 Python 当列表误判）。
    quota_map = {b.get("bucket_id"): b.get("quota", 1) for b in buckets}
    drop_buckets = set()
    note_by_bucket = {b.get("bucket_id"): str(b.get("note", "") or "")
                      for b in buckets}
    for b in buckets:
        bid = b.get("bucket_id", "")
        note = note_by_bucket.get(bid, "")
        if not note_eval.complex_note(note):
            continue
        met, _ = note_eval.eval_note(note, done)
        if met is True:
            drop_buckets.add(bid)
            print(f"  - {bid}: Note 表达式已满足 → 整桶移除（{note[:70]}）")
        else:
            print(f"  ~ {bid}: Note 表达式未满足（met={met}），保守保留")
    done_in = {}
    for c in courses:
        bid = c.get("bucket_id")
        if not bid or c.get("prereq_reference"):
            continue
        if norm_code(c["code"]) in done:
            done_in[bid] = done_in.get(bid, 0) + 1
    for bid, n in done_in.items():
        if bid not in drop_buckets and n >= quota_map.get(bid, 1):
            drop_buckets.add(bid)
    if drop_buckets:
        names = {b.get("bucket_id"): b.get("label", "") for b in buckets}
        print("栏位已满足（已修课程满足配额/Note 表达式）整桶移除:")
        for bid in sorted(drop_buckets):
            print(f"  - {bid}: {names.get(bid, '')}")
        courses = [c for c in courses if c.get("bucket_id") not in drop_buckets]
        buckets = [b for b in buckets if b["bucket_id"] not in drop_buckets]

    before = len(courses)
    courses = [c for c in courses if norm_code(c["code"]) not in done]
    skipped = before - len(courses)
    if skipped:
        print(f"扣除已修/预选课 {skipped} 门（剩 {len(courses)} 门）")

    # 空桶清理：无剩余课程的 bucket 移除（如 AR 判定已满足的扩展主修单门）
    kept_ids = {c.get("bucket_id") for c in courses}
    before_b = len(buckets)
    buckets = [b for b in buckets if b.get("bucket_id") in kept_ids]
    if len(buckets) != before_b:
        print(f"空桶清理: {before_b} → {len(buckets)} 个 bucket")

    # pre-req 引用补录（对照本学年 schedule；schedule 缺失时跳过并提示）
    if sched_idx:
        courses = add_prereq_references(courses, done, sched_idx)

    # Note 语义固化：复杂 Note（AND/方括号/计数）的表达式形状写入 buckets 元数据，
    # AI 无需手写求值器（见 scripts/rank/note_eval.py），仅需复核与 AR 一致
    for b in buckets:
        note = str(b.get("note", "") or "")
        if note_eval.complex_note(note):
            b["note_semantics"] = note_eval.shape(note_eval.parse(note))

    # 未修学分统计（P3 目标学分建议参考）：未修课程学分总和 + 剩余学期估算
    # （4 年制 8 学期；按年级 + 目标学期 Fall/Spring 推算，含当前学期）。
    # 学分缺失的课程（prog-crs 未标学分）单独计数，不参与平均估算。
    def _credit_sum(items):
        total, unknown = 0.0, 0
        for c in items:
            if c.get("prereq_reference"):
                continue
            v = c.get("credits")
            if isinstance(v, (int, float)) and v > 0:
                total += float(v)
            else:
                unknown += 1
        return total, unknown

    unmet_credits, unknown_count = _credit_sum(courses)
    semesters_left = estimate_semesters_left(profile.get("year_of_study"), args.session)
    per_sem = round(unmet_credits / semesters_left, 1) if semesters_left else None
    # 毕业总学分（4 年制默认 120；config → defaults.graduation_credits 可调，
    # 双主修/特殊学制以 SIS AR 学位审计为准）
    graduation_credits = float(load_config()["defaults"].get("graduation_credits", 120))

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "program": first_major,
        "intake_year": admission_year,
        "track": args.track if args.track not in ("NONE", "-") else "",
        "graduation_target_credits": graduation_credits,
        "buckets": buckets,
        "courses": courses,
        "unmet_credits": round(unmet_credits, 1),
        "unmet_credits_unknown_count": unknown_count,
        "estimated_semesters_left": semesters_left,
        "credits_per_semester_estimate": per_sem,
    }
    if pre_enrolled_out:
        out["pre_enrolled"] = pre_enrolled_out
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    cats = {}
    for c in courses:
        if c.get("prereq_reference"):
            cats["prereq_ref"] = cats.get("prereq_ref", 0) + 1
        else:
            cats[c["category"]] = cats.get(c["category"], 0) + 1
    print(f"未修清单: {len(courses)} 门（{len(buckets)} 个 bucket）")
    print(f"  未修学分 ≈ {round(unmet_credits, 1)}"
          + (f"（{unknown_count} 门学分未知）" if unknown_count else "")
          + (f"，剩 {semesters_left} 个学期 → 平均每学期约 {per_sem} 学分"
             if per_sem else ""))
    print("  分类:", ", ".join(f"{k}={v}" for k, v in sorted(cats.items())))
    if not cc_used:
        print("  CC 未纳入（池缺失）")
    print(f"产物 -> {dest}")


if __name__ == "__main__":
    main()
