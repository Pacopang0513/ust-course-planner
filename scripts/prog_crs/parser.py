#!/usr/bin/env python3
"""
prog-crs curriculum 文本解析器 — parser.py
==========================================
把 pdftotext -layout 输出的专业要求文本解析为"候选索引"：

  program → requirements[block{track/option} → section → groups]
  group = { subject, note(原文), credits, courses[], areas[] }

设计原则：
  - 只忠实还原结构（块/节/组/课程），不做语义判断
  - Note（布尔 OR/AND、计数、条件、跨组互斥）一律保留原文，由 phase3 AI 解释
  - 缩进仅作组内判断（alternatives 比组头深），不依赖绝对列宽

用法:
  python3 scripts/prog_crs/parser.py --file <xxx.txt>          # 单文件 → stdout JSON
  python3 scripts/prog_crs/parser.py --dir  cache/prog-crs/raw # 批量 → database/curriculum/
  python3 scripts/prog_crs/parser.py --selftest                # 用 fixtures 自测
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ── 正则 ─────────────────────────────────────────────────────
RE_CODE = r"([A-Z]{3,4}(?:/[A-Z]{3,4})*)"              # 单 subject 或组合
RE_CREDIT = r"(\d+(?:\.\d)?(?:-\d+(?:\.\d)?)?)"          # 3 / 3-4 / 4-6
RE_PAGE_FOOTER = re.compile(
    r"^\s*\d{4}-\d{2}\s+[A-Z0-9]+\s+\(\dY\)\s+\(\d{4}-\d{2}\s+intake\)\s*Page\s+\d+\s*$"
)
RE_INTAKE = re.compile(r"admitted in (\d{4}-\d{2})")
RE_TRACK_NAME = re.compile(r"^.{2,60}?(?:Track|Option)\s*$")
RE_AREA = re.compile(r"^.{2,60}\s*$")

SECTION_NAMES = {
    "Major Pre-requisite course(s)": "pre_major",
    "Engineering Fundamental Course(s)": "fundamental",
    "Required Course(s)": "required",
    "Elective Course(s)": "elective",
    "Elective(s)": "elective",
    "Other(s)": "other",
}
TABLE_HEADERS = {"Credit(s)", "attained", "Minimum", "credit(s)", "required",
                 "Course", "Course Title"}


def _col(line: str) -> int:
    return len(line) - len(line.lstrip())


def _credit(line: str):
    m = re.search(RE_CREDIT + r"\*{0,2}\s*$", line.rstrip())
    return m.group(1) if m else ""


def _subject_at(line: str):
    m = re.match(r"^\s*" + RE_CODE + r"\s", line)
    if m:
        return m.group(1), _col(line) + len(m.group(1)) - len(m.group(1).lstrip())
    return None, None


class CurriculumParser:
    def __init__(self, text: str, program: str = "", source: dict = None):
        self.lines = text.splitlines()
        self.program_code = program
        self.source = source or {}
        self.header = ""          # 页眉（每页重复，跳过用）
        self.school = ""
        self.title = ""
        self.intake_year = ""
        self.notes_program = []
        self.remarks = []
        # 结构
        self.blocks = []
        self.cur_block = None
        self.cur_section = None
        self.cur_group = None     # 当前组（含 note/描述）
        self.group_ref_col = None
        self.cur_area = ""
        self.buf_notes = []       # 待归属的散文行
        self.in_remarks = False
        self.in_track_mode = False

    # ── 辅助 ────────────────────────────────────────────────
    def _flush_notes(self, target):
        text = " ".join(self.buf_notes).strip()
        self.buf_notes = []
        if text and target is not None:
            target.setdefault("notes", []).append(text)

    def _new_block(self, name: str, block_type: str):
        self._close_group()
        b = {"block": block_type, "name": name, "sections": []}
        self._flush_notes(b)          # 待归属散文（如 Track Study 前导语）→ 新块 notes
        self.blocks.append(b)
        self.cur_block = b
        self.cur_section = None
        self.cur_group = None
        self.group_ref_col = None

    def _new_section(self, name: str, stype: str):
        self._close_group()
        if self.cur_block is None:
            self._new_block("Major Requirements", "major")
        self._flush_notes(self.cur_block)
        s = {"type": stype, "name": name, "groups": []}
        self.cur_block["sections"].append(s)
        self.cur_section = s
        self.cur_group = None
        self.group_ref_col = None

    def _close_group(self):
        self.cur_group = None
        self.group_ref_col = None

    def _add_course(self, code, title, credits, col):
        if self.cur_section is None:
            self._new_section("Required Course(s)", "required")
        # 判断是 alternatives 还是新独立课
        is_alt = (self.cur_group is not None
                  and (self.cur_group.get("note") or self.cur_group.get("kind") == "pool")
                  and self.group_ref_col is not None
                  and col > self.group_ref_col)
        if not is_alt:
            self.cur_group = {"subject": "", "note": "", "credits": "",
                              "kind": "single", "courses": [], "areas": []}
            self.cur_section["groups"].append(self.cur_group)
            self.group_ref_col = col
        course = {"code": code, "title": title.strip(), "credits": credits,
                  "area": self.cur_area}
        self.cur_group["courses"].append(course)

    def _add_group_header(self, subject, content, col):
        self._close_group()
        if self.cur_section is None:
            self._new_section("Required Course(s)", "required")
        self.cur_area = ""
        note, credits = content, ""
        m = re.search(r"(\s+|)(\d+(?:\.\d)?(?:-\d+(?:\.\d)?)?)\*{0,2}\s*$", note)
        if m and len(m.group(2)) < 8:
            credits = m.group(2)
            note = note[:m.start(2)].rstrip()
        note = note.strip()
        self.cur_group = {"subject": subject, "note": note, "credits": credits,
                          "kind": "pool" if note else "group", "courses": [], "areas": []}
        self.group_ref_col = col
        self.cur_section["groups"].append(self.cur_group)

    def _note_line(self, line):
        if self.cur_group is not None:
            self.cur_group["note"] = (self.cur_group["note"] + " " + line.strip()).strip()

    # ── 元数据 ──────────────────────────────────────────────
    def _extract_meta(self):
        count = 0
        for ln in self.lines:
            s = ln.strip()
            if not s:
                continue
            count += 1
            if not self.header and " - " in s:
                self.header = s
                self.school, self.title = s.split(" - ", 1)
            m = RE_INTAKE.search(s)
            if m:
                self.intake_year = m.group(1)
            if count >= 6:
                break

    # ── 主循环 ──────────────────────────────────────────────
    def parse(self):
        self._extract_meta()
        for raw in self.lines:
            self._process(raw)
        self._flush_notes(self.cur_block if self.cur_block else None)
        self._close_group()
        return self.build()

    def _process(self, raw):
        line = raw.rstrip("\n")
        s = line.strip()

        # 1) 可忽略行
        if not s or s == self.header or RE_PAGE_FOOTER.match(line) \
           or s in TABLE_HEADERS:
            return

        # 2) 小节头（前缀匹配，因行尾可能粘着 "Minimum"/"Credit(s)" 表头）
        for name in sorted(SECTION_NAMES, key=len, reverse=True):
            if s.startswith(name):
                self.in_remarks = False
                self._new_section(name, SECTION_NAMES[name])
                return
        if s in ("Track Study", "Option(s)", "Track Study "):
            self.in_remarks = False
            self.in_track_mode = True
            return

        # 3) Remarks 收集（遇小节头/课程行/组头即结束，避免吞掉后续内容）
        if s.startswith("**Remarks") or s.startswith("Remarks on course(s)"):
            self.in_remarks = True
            return
        if self.in_remarks:
            if s.startswith("-"):
                self.remarks.append(s.lstrip("- ").strip())
                return
            if re.match(r"^\s*" + RE_CODE + r"\s+\d{4}", line) or _subject_at(line):
                self.in_remarks = False
            else:
                return

        # 4) 课程行（含 honors 后缀；组合 subject 如 ISOM/MATH 是组头，不在此处理）
        m = re.match(r"^\s*" + RE_CODE + r"\s+(\d{4}[A-Z]?)\*{0,2}\s+(?![-()\[\],&])(.+?)\s*$", line)
        if m and "/" not in m.group(1):
            subj = m.group(1)
            code = m.group(2)
            body = m.group(3).strip()
            credits = _credit(body)
            if credits:
                body = body[: -len(credits)].rstrip().rstrip("*").rstrip()
            col = _col(line)
            # 若前一行是 note 且本行无学分 → note 延续（排除误判）
            if self.cur_group is not None and self.cur_group.get("note") and not credits \
               and not self._looks_like_title(body):
                self._note_line(line)
                return
            self._add_course(f"{subj} {code}", body, credits, col)
            return

        # 5) 组头（subject + 描述/Note，无 4 位课号）
        subj, col = _subject_at(line)
        if subj:
            content = line[line.find(subj) + len(subj):].strip()
            # 纯课号续行（OR 列表折行 "MATH 2431"）：只要当前组有 note 就并入，
            # 不要求组内无课程（_credit 会把行尾课号误判为学分）
            pure_code_line = bool(re.match(r"^\d{4}[A-Z]?\s*$", content))
            # 池内描述续行：当前组有 note 且尚无课程、本行也无学分 → 并入 note
            # 例: elective 池的 "Any PHYS courses at 3000-level or above"
            if ((pure_code_line or not _credit(content))
                    and self.cur_group is not None
                    and self.cur_group.get("note")
                    and (pure_code_line or not self.cur_group.get("courses"))):
                self._note_line(line)
                return
            self._add_group_header(subj, content, col)
            return

        # 6) Track / Option 名
        if self.in_track_mode and RE_TRACK_NAME.match(s):
            self._new_block(s, "track" if "Track" in s else "option")
            return

        # 7) 未分类行：组内 note 延续 / 课程标题延续 / Area 标签 / 散文
        if self.cur_group is not None and self.cur_group.get("note") \
           and (not _credit(s) or re.match(r"^" + RE_CODE + r"\s+\d{4}[A-Z]?\s*$", s)):
            # note 延续（含 "MATH 1024)] OR ..." 这类以代码开头的续行，
            # 以及 OR 列表折行的纯课号行 "MATH 2431"）
            self._note_line(line)
            return
        if self.cur_area or (self.cur_group and self.cur_group.get("kind") == "pool"):
            if RE_AREA.match(s) and not _credit(s) and " " not in s[:6]:
                self.cur_area = s
                self.cur_group.setdefault("areas", [])
                if s not in self.cur_group["areas"]:
                    self.cur_group["areas"].append(s)
                return
        # 散文 → 缓冲区
        self.buf_notes.append(s)

    def _looks_like_title(self, body: str) -> bool:
        return bool(body) and not any(t in body for t in ("OR", "AND", ")", "]"))

    # ── 输出 ────────────────────────────────────────────────
    def build(self) -> dict:
        return {
            "program": self.program_code,
            "intake_year": self.intake_year,
            "school": self.school.strip(),
            "title": self.title.strip(),
            "source": self.source,
            "notes": self.notes_program,
            "remarks": self.remarks,
            "requirements": self.blocks,
        }


def parse_file(path: Path, code: str = "") -> dict:
    code = code or path.stem.upper()
    text = path.read_text(encoding="utf-8", errors="ignore")
    src = {"file": str(path), "parsed_at": ""}
    return CurriculumParser(text, program=code, source=src).parse()


def parse_dir(src: Path, dst_base: Path):
    """按源目录名（=入学年份）分目录输出: dst_base/{year}/{code}.json"""
    year = src.name
    dst = dst_base / year
    dst.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    for txt in sorted(src.glob("*.txt")):
        try:
            data = parse_file(txt)
            out = dst / f"{data['program']}.json"
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            print(f"  ✅ {data['program']}: {len(data['requirements'])} blocks -> {out}")
            ok += 1
        except Exception as e:
            print(f"  ❌ {txt.name}: {e}")
            fail += 1
    print(f"\n解析完成（{year}）: 成功 {ok}, 失败 {fail}")


def selftest():
    fx = Path(__file__).resolve().parent / "fixtures"
    if not fx.exists():
        sys.exit("错误: 缺少 fixtures/ 目录")
    checks = {
        "econ.txt": (["ECON 3014", "ECON 3024"], 1),
        "comp_required.txt": (["COMP 2011", "COMP 2611", "COMP 2711H"], 1),
        "comp_elective.txt": (["COMP 3211", "COMP 4211"], 1),
        "chem_options.txt": (["CHEM 4350", "CHEM 4250"], 2),
        "math_tracks.txt": (["MATH 2352", "COMP 2011"], 2),
        "elec_option.txt": (["UROP 1000"], 1),
        "math_other.txt": ([], 1),
    }
    all_ok = True
    for name, (need_codes, min_blocks) in checks.items():
        p = fx / name
        if not p.exists():
            print(f"  [SKIP] {name} 不存在")
            continue
        data = parse_file(p)
        got_blocks = len(data["requirements"])
        flat = [c["code"] for b in data["requirements"]
                for sec in b["sections"] for g in sec["groups"] for c in g["courses"]]
        missing = [c for c in need_codes if c not in flat]
        ok = (not missing) and (got_blocks >= min_blocks)
        print(f"  [{('OK' if ok else 'FAIL'):4}] {name}: blocks={got_blocks} "
              f"missing={missing}")
        if not ok:
            all_ok = False
    sys.exit(0 if all_ok else 1)


def main():
    ap = argparse.ArgumentParser(description="prog-crs curriculum 解析器")
    ap.add_argument("--file", help="单个 txt → stdout JSON")
    ap.add_argument("--dir", help="批量解析目录 → database/curriculum/")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        selftest()
    elif args.file:
        data = parse_file(Path(args.file))
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.dir:
        parse_dir(Path(args.dir), ROOT / "database" / "curriculum")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
