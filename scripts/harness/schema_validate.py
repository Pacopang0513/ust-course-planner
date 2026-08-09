#!/usr/bin/env python3
"""
R2 产物合规检查 — schema_validate.py
====================================
校验 data/ 与 output/ 产物是否符合 templates/schemas/ 中的 JSON Schema。

用法:
  python scripts/harness/schema_validate.py --dir <产物目录> --schema-dir <schema目录>
  python scripts/harness/schema_validate.py --target <文件> [--schema <schema文件>]

匹配规则（批处理模式）:
  <产物目录>/profile.json            <-> <schema目录>/profile.schema.json
  <产物目录>/passed_courses.json     <-> <schema目录>/passed_courses.schema.json
  （按 basename 匹配：xxx.json <-> xxx.schema.json）

任一产物未通过校验 → exit 1。
"""

import argparse
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft7Validator, ValidationError
except ImportError:
    sys.exit("缺少依赖 jsonschema，请先运行: python -m pip install jsonschema")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIRS = ["data", "output"]
DEFAULT_SCHEMA_DIR = ROOT / "templates" / "schemas"

# 文件名或父目录名 → schema 的映射（basename 匹配失败时的回退）
FILE_SCHEMA = {
    "mapping_result.json": "mapping.schema.json",
    "checkpoint.json": "checkpoint.schema.json",
    "pre_enrolled.json": "pre_enroll.schema.json",
}
DIR_SCHEMA = {"curriculum", "course_catalog", "course_notes"}
# 前缀匹配：courses_{session}.json → courses.schema.json（session 动态）
PREFIX_SCHEMA = {"courses_": "courses", "cc_courses_": "cc_courses"}


def _schema_for(target: Path, schema_dir: Path):
    """basename 匹配 → 显式映射 → 前缀匹配 → 父目录链匹配（curriculum/<YEAR>/PHYS.json）"""
    c = schema_dir / f"{target.stem}.schema.json"
    if c.exists():
        return c
    if target.name in FILE_SCHEMA:
        c = schema_dir / FILE_SCHEMA[target.name]
        if c.exists():
            return c
    for prefix, stem in PREFIX_SCHEMA.items():
        if target.name.startswith(prefix):
            c = schema_dir / f"{stem}.schema.json"
            if c.exists():
                return c
    for parent in target.parents:
        if parent.name in DIR_SCHEMA:
            c = schema_dir / f"{parent.name}.schema.json"
            if c.exists():
                return c
    return None


def _load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_file(target: Path, schema: Path) -> list:
    """校验单个文件，返回错误列表"""
    errors = []
    try:
        instance = _load_json(target)
        schema_data = _load_json(schema)
        validator = Draft7Validator(schema_data)
        for e in sorted(validator.iter_errors(instance), key=lambda x: list(x.path)):
            errors.append(f"  {target.name}: {'/'.join(map(str, e.path)) or '<root>'}: {e.message}")
    except json.JSONDecodeError as e:
        errors.append(f"  {target.name}: JSON 解析失败: {e}")
    except OSError as e:
        errors.append(f"  {target.name}: 读取失败: {e}")
    return errors


def _resolve_dir(name: str) -> Path:
    """相对路径：优先按当前 cwd 解析（test_runner 隔离副本场景），
    不存在时回退项目根（外部 cwd 场景），避免空校验假阳性"""
    p = Path(name)
    if p.is_absolute():
        return p
    if p.exists():
        return p
    alt = ROOT / p
    return alt if alt.exists() else p


def main():
    parser = argparse.ArgumentParser(description="R2 产物 schema 校验")
    parser.add_argument("--dir", action="append", default=[],
                        help="产物目录（可多次指定，默认 data output；相对路径锚定项目根）")
    parser.add_argument("--schema-dir", default=str(DEFAULT_SCHEMA_DIR),
                        help="schema 目录（默认 templates/schemas）")
    parser.add_argument("--target", help="单文件模式：目标 JSON")
    parser.add_argument("--schema", help="单文件模式：schema 文件")
    args = parser.parse_args()

    schema_dir = Path(args.schema_dir)

    if args.target:
        target = _resolve_dir(args.target)
        schema = Path(args.schema) if args.schema else \
            schema_dir / f"{target.stem}.schema.json"
        if not schema.exists():
            print(f"[R2] SKIP: 无对应 schema {schema}")
            sys.exit(0)
        errors = validate_file(target, schema)
        if errors:
            print("[R2] FAIL:")
            for e in errors:
                print(e)
            sys.exit(1)
        print(f"[R2] OK: {target} 通过 {schema.name}")
        sys.exit(0)

    dirs = [_resolve_dir(d) for d in (args.dir or DEFAULT_DIRS)]
    total_errors = 0
    total_checked = 0
    total_skipped = 0

    for d in dirs:
        if not d.exists():
            print(f"[R2] 提示: 产物目录不存在，跳过 {d}")
            continue
        for target in sorted(d.rglob("*.json")):
            schema = _schema_for(target, schema_dir)
            if schema is None:
                total_skipped += 1
                continue
            total_checked += 1
            errors = validate_file(target, schema)
            if errors:
                total_errors += len(errors)
                print("[R2] FAIL:")
                for e in errors:
                    print(e)
            else:
                print(f"[R2] OK: {target}")

    print(f"[R2] 汇总: 校验 {total_checked} 个产物, 跳过 {total_skipped} 个(无 schema), 错误 {total_errors} 个")
    sys.exit(1 if total_errors else 0)


if __name__ == "__main__":
    main()
