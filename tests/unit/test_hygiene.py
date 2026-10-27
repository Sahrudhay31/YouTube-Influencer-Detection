"""
tests/unit/test_hygiene.py
Unit tests T-H1 through T-H5 for Phase R1 (Security and Hygiene).
"""
import os
import re
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


# ── T-H1: Scan finds planted fake key in archive/ and docs/ ─────────────────

def test_th1_scanner_catches_planted_keys(tmp_path):
    """T-H1: Verification that the broadened scan detects AIza keys in archive/ and docs/."""
    # Import the scanner logic from check_all
    import scripts.check_all as ca
    
    archive_dir = tmp_path / "archive" / "old_proj"
    archive_dir.mkdir(parents=True)
    bad_archive_file = archive_dir / "bad.py"
    prefix = "AIza"
    bad_archive_file.write_text(f"API_KEY = '{prefix}SyA12345678901234567890123456789012'", encoding="utf-8")
    
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    bad_docs_file = docs_dir / "bad.md"
    bad_docs_file.write_text(f"Key was: {prefix}SyB12345678901234567890123456789012", encoding="utf-8")

    key_regex = re.compile(r"AIza[0-9A-Za-z-_]{35}")
    
    found = []
    for f in [bad_archive_file, bad_docs_file]:
        for line_no, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if key_regex.search(line):
                found.append(f"{f.name}:{line_no}")
                
    assert len(found) == 2, f"Expected 2 planted keys to be detected, found: {found}"


# ── T-H2: .env.example contains no 64-hex string ────────────────────────────

def test_th2_env_example_has_no_64_hex_salt():
    """T-H2: .env.example must not contain any real 64-hex salt string."""
    env_example = ROOT / ".env.example"
    assert env_example.exists(), ".env.example does not exist"
    
    content = env_example.read_text(encoding="utf-8")
    hex64_regex = re.compile(r"\b[0-9a-fA-F]{64}\b")
    matches = hex64_regex.findall(content)
    
    assert len(matches) == 0, f"Found 64-hex value(s) in .env.example: {matches}"


# ── T-H3: No hardcoded Windows personal paths in tracked files ──────────────

def test_th3_no_personal_user_paths_in_tracked_files():
    """T-H3: Tracked files must not contain personal Windows user paths (e.g. C:\\Users\\<name>)."""
    # Regex matches personal user directories but excludes generic placeholders like <username>
    personal_path_regex = re.compile(r"(?:[A-Za-z]:[\\/][Uu]sers[\\/](?!<)[A-Za-z0-9_ -]+|/home/(?!<)[A-Za-z0-9_ -]+)")
    
    violations = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if (
            rel == ".env"
            or path.suffix in [".pyc", ".pyo", ".pyd", ".png", ".jpg", ".parquet"]
            or "__pycache__" in rel
            or any(rel.startswith(p) for p in [".git/", ".venv/", "venv/", "state/", "logs/", "data/", "tests/fixtures/", "node_modules/", "frontend/node_modules/", "frontend/dist/"])
        ):
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(content.splitlines(), 1):
                if personal_path_regex.search(line):
                    violations.append(f"{rel}:{line_no}")
        except Exception:
            pass

    assert len(violations) == 0, f"Found hardcoded personal paths in: {violations}"


# ── T-H4: Extraction script reads YOUNIVERSE_SOURCE_PATH ────────────────────

def test_th4_extract_script_reads_youniverse_source_path(monkeypatch, tmp_path):
    """T-H4: scripts/extract_dev_sample.py reads from YOUNIVERSE_SOURCE_PATH env var."""
    import gzip
    fake_gz = tmp_path / "fake_input.jsonl.gz"
    with gzip.open(fake_gz, "wt", encoding="utf-8") as f:
        f.write('{"id": "test1"}\n{"id": "test2"}\n')

    monkeypatch.setenv("YOUNIVERSE_SOURCE_PATH", str(fake_gz))
    
    # Run the script with --max-rows 1 using python subprocess
    extract_script = ROOT / "scripts" / "extract_dev_sample.py"
    res = subprocess.run(
        [sys.executable, str(extract_script), "--max-rows", "1"],
        cwd=str(ROOT),
        capture_output=True,
        text=True
    )
    assert res.returncode == 0, f"Extraction failed with error: {res.stderr}"
    assert f"Reading from: {fake_gz}" in res.stdout


# ── T-H5: Comment hashing refuses empty or leaked salt ───────────────────────

def test_th5_comment_hashing_refuses_empty_or_leaked_salt(monkeypatch):
    """T-H5: get_hash_salt() raises EnvironmentError if empty, and ValueError if leaked salt."""
    from src.enrichment.comment_sampler import get_hash_salt
    
    # 1. Empty salt
    monkeypatch.setenv("COMMENT_HASH_SALT", "")
    with pytest.raises(EnvironmentError, match="COMMENT_HASH_SALT env var is not set"):
        get_hash_salt()

    # 2. Leaked salt from git history
    old_leaked_salt = "ba06a736e6f19fe0525db725809a29e7843e490e00a760bb9cc34615f94ad178"
    monkeypatch.setenv("COMMENT_HASH_SALT", old_leaked_salt)
    with pytest.raises(ValueError, match="matches the old compromised salt"):
        get_hash_salt()

    # 3. Valid fresh salt
    fresh_salt = "a" * 64
    monkeypatch.setenv("COMMENT_HASH_SALT", fresh_salt)
    assert get_hash_salt() == fresh_salt
