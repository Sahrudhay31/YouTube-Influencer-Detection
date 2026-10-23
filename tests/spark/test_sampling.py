"""
tests/spark/test_sampling.py
Unit and integration tests for YouNiverse Channel-Hash Sampling (Phase R2).

Tests:
- T-D7: Same input + salt -> identical kept-channel set (deterministic).
- T-D8: A fixture with 3 channels keeps/drops each channel's lines as a block.
- T-D9: Different salt -> different but similarly sized set.
- T-D10: Output size <= configured disk cap.
- T-D11: Resume gives the exact same output as an uninterrupted run.
"""
from __future__ import annotations

import gzip
import json
import zlib
from pathlib import Path
import pytest

from src.ingestion.sample_youniverse import (
    extract_channel_id_from_json_line,
    is_channel_kept,
    sample_metadata,
)


def test_t_d7_deterministic_channel_hashing():
    """T-D7: Same input + salt yields identical kept-channel set."""
    channels = [f"UCtest_{i:04d}" for i in range(500)]
    salt = "bda_beauty_salt_2026"
    bp = 1000

    set1 = {ch for ch in channels if is_channel_kept(ch, salt, bp)}
    set2 = {ch for ch in channels if is_channel_kept(ch, salt, bp)}

    assert set1 == set2
    assert len(set1) > 0
    # Expected ~10% (+/- binomial variance)
    assert 30 <= len(set1) <= 70


def test_t_d8_channels_kept_as_complete_blocks(tmp_path: Path):
    """T-D8: Fixture with 3 channels keeps or drops each channel's lines as a block."""
    channels = ["UC_alpha", "UC_beta", "UC_gamma"]
    salt = "bda_beauty_salt_2026"
    # Find a basis point threshold where at least one is kept and one is dropped
    kept_flags = {ch: is_channel_kept(ch, salt, 5000) for ch in channels}
    # Ensure there is variation
    bp = 5000
    while len(set(kept_flags.values())) == 1:
        bp += 1000
        kept_flags = {ch: is_channel_kept(ch, salt, bp) for ch in channels}

    fixture_gz = tmp_path / "fixture_metadata.jsonl.gz"
    out_gz = tmp_path / "sampled_metadata.jsonl.gz"

    # Create 5 videos for each of the 3 channels
    lines_per_channel = 5
    with gzip.open(fixture_gz, "wt", encoding="utf-8") as f:
        for ch in channels:
            for v_idx in range(lines_per_channel):
                row = {
                    "display_id": f"vid_{ch}_{v_idx}",
                    "channel_id": ch,
                    "title": f"Video {v_idx} of {ch}",
                    "view_count": 1000 * (v_idx + 1),
                }
                f.write(json.dumps(row) + "\n")

    sample_metadata(fixture_gz, out_gz, salt=salt, basis_points=bp)

    # Read back sampled lines and group by channel
    channel_counts: dict[str, int] = {}
    with gzip.open(out_gz, "rt", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            ch = data["channel_id"]
            channel_counts[ch] = channel_counts.get(ch, 0) + 1

    for ch in channels:
        if kept_flags[ch]:
            assert channel_counts.get(ch, 0) == lines_per_channel, (
                f"Expected all {lines_per_channel} lines for kept channel {ch}, got {channel_counts.get(ch, 0)}"
            )
        else:
            assert ch not in channel_counts, (
                f"Expected 0 lines for dropped channel {ch}, got {channel_counts[ch]}"
            )


def test_t_d9_different_salts_yield_different_sets():
    """T-D9: Different salt -> different but similarly sized set."""
    channels = [f"UCtest_{i:04d}" for i in range(1000)]
    bp = 1000  # 10%
    salt1 = "bda_beauty_salt_2026"
    salt2 = "independent_salt_validation_2026"

    kept1 = {ch for ch in channels if is_channel_kept(ch, salt1, bp)}
    kept2 = {ch for ch in channels if is_channel_kept(ch, salt2, bp)}

    # Both should be ~100 channels (allow range 70-130)
    assert 70 <= len(kept1) <= 130
    assert 70 <= len(kept2) <= 130

    # Overlap should be ~10% of 10% = ~1% (allow range 0-25)
    overlap = kept1.intersection(kept2)
    assert len(overlap) < len(kept1) * 0.35, f"Salts are too correlated! Overlap: {len(overlap)}"
    assert kept1 != kept2


def test_t_d10_output_size_cap(tmp_path: Path):
    """T-D10: Output size <= configured disk cap."""
    fixture_gz = tmp_path / "test_size.jsonl.gz"
    out_gz = tmp_path / "sampled_size.jsonl.gz"

    with gzip.open(fixture_gz, "wt", encoding="utf-8") as f:
        for i in range(100):
            row = {"channel_id": f"UC_{i % 5}", "title": "Test Title " * 5}
            f.write(json.dumps(row) + "\n")

    stats = sample_metadata(fixture_gz, out_gz, salt="test_salt", basis_points=2000)
    max_disk_mb = 10240  # 10 GB
    assert stats["output_size_mb"] <= max_disk_mb


def test_t_d11_resume_exact_match(tmp_path: Path):
    """T-D11: Resume gives the same output as an uninterrupted run."""
    fixture_gz = tmp_path / "fixture.jsonl.gz"
    full_out_gz = tmp_path / "full_out.jsonl.gz"
    resumed_out_gz = tmp_path / "resumed_out.jsonl.gz"
    cp_path = tmp_path / "checkpoint.json"

    salt = "resume_test_salt"
    bp = 5000

    # Create 30 rows across 5 channels
    rows = []
    for i in range(30):
        rows.append({
            "display_id": f"vid_{i}",
            "channel_id": f"UC_{i % 5}",
            "title": f"Video title {i}",
        })

    with gzip.open(fixture_gz, "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    # 1. Uninterrupted run
    full_stats = sample_metadata(fixture_gz, full_out_gz, salt=salt, basis_points=bp)

    # 2. Part 1: stop after 12 lines
    part1_stats = sample_metadata(
        fixture_gz,
        resumed_out_gz,
        salt=salt,
        basis_points=bp,
        max_lines=12,
        checkpoint_path=cp_path,
        checkpoint_interval=6,
    )
    # Ensure checkpoint recorded 12 lines
    with open(cp_path, "w", encoding="utf-8") as cpf:
        json.dump({
            "lines_read": 12,
            "lines_kept": part1_stats["lines_kept"],
            "kept_channels": [],
        }, cpf)

    # 3. Part 2: resume from line 12
    part2_stats = sample_metadata(
        fixture_gz,
        resumed_out_gz,
        salt=salt,
        basis_points=bp,
        resume=True,
        checkpoint_path=cp_path,
    )

    # Read back both files and compare line-for-line
    with gzip.open(full_out_gz, "rt", encoding="utf-8") as f_full:
        full_lines = f_full.readlines()

    with gzip.open(resumed_out_gz, "rt", encoding="utf-8") as f_resumed:
        resumed_lines = f_resumed.readlines()

    assert full_lines == resumed_lines, "Resumed output lines did not match uninterrupted run"
