#!/usr/bin/env python3
"""
R1-R6 Testcase 运行器 — test_runner.py
======================================
在隔离副本中运行 testcase，并执行 6 条约束检查。

用法:
  python scripts/harness/test_runner.py --case scripts/tests/demo
  python scripts/harness/test_runner.py --case scripts/tests/demo --tamper   # 演示 R1 失败
  python scripts/harness/test_runner.py --case <dir> [--keep-tmp]

testcase 目录结构:
  <case>/run.py                  必选，模拟/驱动被测流程（cwd=隔离副本根目录）
  <case>/fixtures/cookies.txt    可选，mock cookie → 隔离副本 credentials/
  <case>/fixtures/user/*         可选，mock 用户输入 → 隔离副本 user/

退出码: 0 = 全部通过; 1 = 任一规则失败
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable

READONLY_DIRS = ["skills", "database", "templates", "user", "scripts"]
READONLY_FILES = ["opencode.json"]
PHASES = ["phase1-input", "phase2-profile", "phase3-course-analysis",
          "phase4-report", "phase4.5-must-take"]
TIMESTAMP_KEYS = {"updated_at", "generated_at"}

REAL_CREDENTIALS = ROOT / "credentials"


def _copy_skeleton(dst: Path):
    """复制只读集 + 配置到隔离目录（R6）"""
    for d in READONLY_DIRS:
        src = ROOT / d
        if src.exists():
            shutil.copytree(src, dst / d, dirs_exist_ok=True)
    for f in READONLY_FILES:
        src = ROOT / f
        if src.exists():
            shutil.copy2(src, dst / f)


def _apply_fixtures(case_dir: Path, dst: Path):
    fx = case_dir / "fixtures"
    if not fx.exists():
        return
    if (fx / "cookies.txt").exists():
        (dst / "credentials").mkdir(parents=True, exist_ok=True)
        shutil.copy2(fx / "cookies.txt", dst / "credentials" / "cookies.txt")
    if (fx / "user").exists():
        shutil.copytree(fx / "user", dst / "user", dirs_exist_ok=True)


def _run(args: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([PY, *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _normalize(obj):
    """递归去掉时间戳字段，供 R5 比对"""
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items() if k not in TIMESTAMP_KEYS}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    return obj


def _collect_products(src: Path, dst: Path):
    for d in ("data", "output"):
        s = src / d
        if s.exists():
            shutil.copytree(s, dst / d, dirs_exist_ok=True)


def _dir_stat(path: Path) -> tuple:
    """目录（或其下 cookies.txt）的 mtime/size，用于 R3 未触碰校验"""
    target = path / "cookies.txt" if (path / "cookies.txt").exists() else path
    if not target.exists():
        return None
    st = target.stat()
    return (st.st_mtime_ns, st.st_size)


def main():
    parser = argparse.ArgumentParser(description="R1-R6 testcase 运行器")
    parser.add_argument("--case", required=True, help="testcase 目录（相对项目根或绝对路径）")
    parser.add_argument("--keep-tmp", action="store_true", help="保留临时副本便于排查")
    parser.add_argument("--tamper", action="store_true",
                        help="以 --tamper 参数运行用例（演示 R1 失败）")
    args = parser.parse_args()

    case_dir = Path(args.case)
    if not case_dir.is_absolute():
        case_dir = ROOT / case_dir
    run_py = case_dir / "run.py"
    if not run_py.exists():
        sys.exit(f"错误: 缺少 {run_py}")

    # ── 真实项目侧基线 ──
    real_snap_dir = Path(tempfile.mkdtemp(prefix="ust_snap_"))
    real_snap = real_snap_dir / "real_before.json"
    r = _run(["scripts/harness/hash_check.py", "snapshot", "-o", str(real_snap)], ROOT)
    if r.returncode != 0:
        sys.exit("错误: 真实项目只读集快照失败\n" + r.stdout)
    real_cred_before = _dir_stat(REAL_CREDENTIALS)

    results = {}

    # ── R6: 隔离副本 ──
    tmp = Path(tempfile.mkdtemp(prefix="ust_case_"))
    _copy_skeleton(tmp)
    _apply_fixtures(case_dir, tmp)
    if not (tmp / "credentials" / "cookies.txt").exists():
        (tmp / "credentials").mkdir(parents=True, exist_ok=True)
        (tmp / "credentials" / "cookies.txt").write_text(
            "JSESSIONID=mock-jsessionid!123\nPS_TOKEN=mock-ps-token-000\n", encoding="utf-8")

    # ── R1: 副本侧快照 ──
    snap_before = tmp / "snap_before.json"
    r = _run(["scripts/harness/hash_check.py", "snapshot", "-o", str(snap_before)], tmp)
    if r.returncode != 0:
        sys.exit("错误: 副本只读集快照失败\n" + r.stdout)

    # ── 运行两次（R5 需要） ──
    extra = ["--tamper"] if args.tamper else []
    runs = []
    for i in (1, 2):
        r = _run([str(run_py), *extra], tmp)
        if r.returncode != 0:
            sys.exit(f"错误: 第 {i} 次运行失败\n{r.stdout}\n{r.stderr}")
        prod_dir = tmp / f"products_run{i}"
        _collect_products(tmp, prod_dir)
        runs.append(prod_dir)

    # ── R1: 副本侧验证 ──
    r = _run(["scripts/harness/hash_check.py", "verify", "-s", str(snap_before)], tmp)
    results["R1 只读完整性"] = r.returncode == 0

    # ── R2: 产物 schema 校验 ──
    r = _run(["scripts/harness/schema_validate.py", "--dir", "data", "--dir", "output",
              "--dir", "database/curriculum", "--dir", "database/course_catalog"], tmp)
    results["R2 产物合规"] = r.returncode == 0

    # ── R4: checkpoint 链 + 负向用例 ──
    cp_path = tmp / "data" / "checkpoint.json"
    if not cp_path.exists():
        sys.exit("错误: testcase 未产出 data/checkpoint.json，R4 无法校验")
    cp = json.loads(cp_path.read_text(encoding="utf-8"))
    chain_ok = cp.get("completed") == PHASES and cp.get("current") is None
    tmp2 = Path(tempfile.mkdtemp(prefix="ust_neg_"))
    _copy_skeleton(tmp2)
    _apply_fixtures(case_dir, tmp2)
    rn = _run(["scripts/harness/checkpoint.py", "begin", "phase4-report"], tmp2)
    negative_ok = rn.returncode != 0
    results["R4 阶段顺序"] = chain_ok and negative_ok

    # ── R5: 幂等（两次产物去时间戳后一致） ──
    def load_dir(d: Path):
        merged = {}
        for f in sorted((d / "data").rglob("*.json")) + sorted((d / "output").rglob("*.json")):
            try:
                merged[str(f.relative_to(d))] = _normalize(
                    json.loads(f.read_text(encoding="utf-8")))
            except json.JSONDecodeError as e:
                sys.exit(f"错误: 产物 {f.relative_to(d)} 不是合法 JSON（{e}）")
        return merged
    results["R5 幂等可续"] = load_dir(runs[0]) == load_dir(runs[1])

    # ── R3: 真实凭据未触碰 + mock 值未泄漏到产物 ──
    real_cred_after = _dir_stat(REAL_CREDENTIALS)
    leak_checked = True
    mock_values = set()
    mock_file = tmp / "credentials" / "cookies.txt"
    if mock_file.exists():
        for line in mock_file.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                mock_values.add(line.split("=", 1)[1].strip())
    for d in runs:
        leak_paths = list((d / "data").rglob("*")) + list((d / "output").rglob("*"))
        for f in leak_paths:
            if f.is_file() and f.suffix in (".json", ".md", ".txt"):
                content = f.read_text(encoding="utf-8", errors="ignore")
                for v in mock_values:
                    if v and v in content:
                        leak_checked = False
    results["R3 凭据隔离"] = (real_cred_before == real_cred_after) and leak_checked

    # ── R6: 真实项目只读集未受影响 ──
    r = _run(["scripts/harness/hash_check.py", "verify", "-s", str(real_snap)], ROOT)
    results["R6 环境隔离"] = r.returncode == 0

    # ── 汇总 ──
    print("\n===== R1-R6 汇总 =====")
    all_pass = True
    for name, ok in results.items():
        print(f"  [{('PASS' if ok else 'FAIL'):4}] {name}")
        all_pass = all_pass and ok
    print(f"隔离副本: {tmp}")
    if not args.keep_tmp:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmp2, ignore_errors=True)
        shutil.rmtree(real_snap_dir, ignore_errors=True)
    print("结果:", "全部通过" if all_pass else "存在失败")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
