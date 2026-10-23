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
    print("[1/4] Running broadened secrets & hygiene scan (F1, F2, F3)...")
    key_regex = re.compile(r"AIza[0-9A-Za-z-_]{35}")
    hex64_regex = re.compile(r"\b[0-9a-fA-F]{64}\b")
    # Flag personal paths like C:\Users\<name> or /home/<name>, ignoring generic placeholders like <username>
    personal_path_regex = re.compile(r"(?:[A-Za-z]:[\\/][Uu]sers[\\/](?!<)[A-Za-z0-9_ -]+|/home/(?!<)[A-Za-z0-9_ -]+)")
    
    key_violations = []
    salt_violations = []
    path_violations = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        # Never scan git, venvs, pycache, binaries, runtime state/logs, or private .env
        if (
            rel == ".env"
            or path.suffix in [".pyc", ".pyo", ".pyd", ".png", ".jpg", ".parquet"]
            or "__pycache__" in rel
            or any(rel.startswith(p) for p in [".git/", ".venv/", "venv/", "state/", "logs/"])
        ):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(content.splitlines(), 1):
                # 1. API Keys (scans everywhere including archive/, docs/, config/)
                if key_regex.search(line):
                    key_violations.append(f"{rel}:{line_no}")
                # 2. Salt in .env.example
                if rel == ".env.example" and hex64_regex.search(line):
                    salt_violations.append(f"{rel}:{line_no}")
                # 3. Personal paths in tracked files (excluding binary/cache/raw data/fixtures)
                if not any(rel.startswith(p) for p in ["data/", "tests/fixtures/"]):
                    if personal_path_regex.search(line):
                        path_violations.append(f"{rel}:{line_no}")
        except Exception:
            pass

    failed = False
    if key_violations:
        print("[-] FAILED: Found plaintext API keys in:")
        for v in key_violations:
            print(f"    {v}")
        failed = True
    else:
        print("  [OK] No plaintext API keys found (including in archive/, docs/, config/).")

    if salt_violations:
        print("[-] FAILED: Found real 64-hex salt in .env.example:")
        for v in salt_violations:
            print(f"    {v}")
        failed = True
    else:
        print("  [OK] .env.example contains no 64-hex values.")

    if path_violations:
        print("[-] FAILED: Found hardcoded personal paths in:")
        for v in path_violations:
            print(f"    {v}")
        failed = True
    else:
        print("  [OK] No hardcoded personal paths found in tracked files.")

    return not failed


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
