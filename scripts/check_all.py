"""
scripts/check_all.py
Phase gate verification script implementing Section 8 requirements:
1. Secrets scan: no AIza API keys outside archive/ or .git/
2. Single-entrypoint check: only src/ingestion/yt_client.py may import googleapiclient
3. Python compilation / syntax check across all source and test files
4. Unit tests via pytest
"""
from __future__ import annotations

import os
import re
import sys
import py_compile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run_secrets_scan() -> bool:
    print("[1/4] Running secrets scan...")
    key_regex = re.compile(r"AIza[0-9A-Za-z-_]{35}")
    violations = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        # Skip archive, git, venv, pycache, state, logs
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel == ".env" or any(rel.startswith(p) for p in ["archive/", ".git/", ".venv/", "venv/", "__pycache__/", "state/", "logs/"]):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(content.splitlines(), 1):
                if key_regex.search(line):
                    violations.append(f"{rel}:{line_no}")
        except Exception:
            pass

    if violations:
        print(f"[-] FAILED: Found potential API keys in:")
        for v in violations:
            print(f"    {v}")
        return False
    print("  [OK] Secrets scan passed: No API keys found outside archive/.")
    return True


def run_single_import_check() -> bool:
    print("[2/4] Running single-entrypoint check for googleapiclient...")
    allowed_file = "src/ingestion/yt_client.py"
    violations = []

    for path in (ROOT / "src").rglob("*.py"):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel == allowed_file:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        if "googleapiclient" in content:
            violations.append(rel)

    if violations:
        print(f"[-] FAILED: googleapiclient imported outside {allowed_file}:")
        for v in violations:
            print(f"    {v}")
        return False
    print(f"  [OK] Single-import check passed: Only {allowed_file} imports googleapiclient.")
    return True


def run_compile_check() -> bool:
    print("[3/4] Running Python compilation / syntax checks...")
    errors = []
    for folder in ["src", "tests", "scripts", "config"]:
        folder_path = ROOT / folder
        if not folder_path.exists():
            continue
        for py_file in folder_path.rglob("*.py"):
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(str(e))

    if errors:
        print("[-] FAILED: Syntax/Compilation errors:")
        for err in errors:
            print(f"    {err}")
        return False
    print("  [OK] All Python files compiled cleanly.")
    return True


def run_unit_tests() -> bool:
    print("[4/4] Running unit tests via pytest...")
    res = subprocess.run([sys.executable, "-m", "pytest", "tests/unit", "tests/spark", "-v"], cwd=str(ROOT))
    if res.returncode != 0:
        print(f"[-] FAILED: pytest returned exit code {res.returncode}")
        return False
    print("  [OK] All unit tests passed.")
    return True


def main():
    print("=" * 60)
    print(" BDA Project Phase Gate Verification (check_all)")
    print("=" * 60)
    
    checks = [
        ("Secrets Scan", run_secrets_scan),
        ("Single Import Check", run_single_import_check),
        ("Compilation Pass", run_compile_check),
        ("Unit Tests", run_unit_tests),
    ]

    all_passed = True
    for name, fn in checks:
        if not fn():
            all_passed = False
            break

    print("=" * 60)
    if all_passed:
        print("[SUCCESS] ALL CHECKS PASSED!")
        sys.exit(0)
    else:
        print("[FAIL] SOME CHECKS FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
