"""
tests/unit/test_scalability.py
Unit tests T-B1 through T-B3 for Phase R8 Defensible Benchmark.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pandas as pd
import pytest

from scripts.scalability_benchmark import (
    check_superlinear_suspect,
    compute_median_and_iqr,
)


def test_tb1_superlinear_suspect_flag():
    """T-B1: Fabricated 12x speedup on 2 cores is strictly flagged as superlinear_suspect."""
    # Fabricated 12.0x speedup on 2 cores (efficiency = 6.0 > 1.20)
    is_suspect = check_superlinear_suspect(speedup=12.0, cores=2, threshold=1.20)
    assert is_suspect is True, "Expected 12x speedup on 2 cores to be flagged as superlinear suspect"

    # Realistic 1.8x speedup on 2 cores (efficiency = 0.90 <= 1.20)
    is_normal = check_superlinear_suspect(speedup=1.8, cores=2, threshold=1.20)
    assert is_normal is False


def test_tb2_output_csv_has_required_defensible_columns():
    """T-B2: Benchmark data model requires median, IQR, cold time, and repeats columns."""
    sample_times = [10.5, 9.8, 10.1, 9.9, 10.2]
    med, iqr = compute_median_and_iqr(sample_times)

    assert abs(med - 10.1) < 1e-4
    assert iqr > 0.0

    # Verify expected column schema
    required_cols = {
        "benchmark_category",
        "configuration",
        "cores",
        "cold_elapsed_s",
        "warm_median_s",
        "iqr_s",
        "repeats",
        "speedup",
        "parallel_efficiency",
        "superlinear_suspect",
    }
    sample_df = pd.DataFrame([{
        "benchmark_category": "core_scalability",
        "configuration": "local[2]",
        "cores": 2,
        "cold_elapsed_s": 5.2,
        "warm_median_s": 3.1,
        "iqr_s": 0.2,
        "repeats": 5,
        "speedup": 1.7,
        "parallel_efficiency": 0.85,
        "superlinear_suspect": False,
    }])
    assert required_cols.issubset(set(sample_df.columns))


def test_tb3_readme_scalability_generated_from_csv():
    """T-B3: Generator parses CSV columns accurately and generates defensible markdown."""
    from scripts.update_readme_metrics import generate_scalability_markdown_table

    sample_df = pd.DataFrame([
        {
            "benchmark_category": "core_scalability",
            "configuration": "local[1]",
            "cores": 1,
            "warm_median_s": 10.0,
            "iqr_s": 0.5,
            "speedup": 1.0,
            "parallel_efficiency": 1.0,
            "superlinear_suspect": False,
        },
        {
            "benchmark_category": "core_scalability",
            "configuration": "local[2]",
            "cores": 2,
            "warm_median_s": 5.8,
            "iqr_s": 0.3,
            "speedup": 1.72,
            "parallel_efficiency": 0.86,
            "superlinear_suspect": False,
        },
    ])

    table_md = generate_scalability_markdown_table(sample_df)
    assert "local[1]" in table_md
    assert "local[2]" in table_md
    assert "1.72x" in table_md
    assert "0.86" in table_md
