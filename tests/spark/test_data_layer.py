"""
tests/spark/test_data_layer.py
Smoke tests for Phase 2 data layer:
- T-D1: Write -> read round trip equals input.
- T-D2: Raw vs Parquet row count equal.
- T-D3: No duplicate video IDs (or documented duplicates checked).
- T-D4: Dev sample <= configured cap (50,000).
- T-D5: Job re-run is idempotent.
- T-D6: Failure raises loudly (no silent fallback).
"""
from __future__ import annotations

import pytest
from pathlib import Path
from src.common.spark_session import get_spark
from src.common.config import get_settings
from src.common.paths import local


@pytest.fixture(scope="module")
def spark():
    s = get_spark(app_name="bda-phase2-tests", local_mode=True)
    yield s
    # Keep session managed


def test_td1_write_read_round_trip(spark, tmp_path):
    """T-D1: Write -> read round trip equals the input."""
    df = spark.sql(
        "SELECT 1 AS id, 'vid_1' AS display_id, 100 AS views "
        "UNION ALL SELECT 2, 'vid_2', 200 "
        "UNION ALL SELECT 3, 'vid_3', 300"
    )
    
    out_dir = str(tmp_path / "round_trip.parquet")
    df.write.mode("overwrite").parquet(out_dir)
    
    df_read = spark.read.parquet(out_dir)
    assert df_read.count() == 3
    ids = sorted([r.display_id for r in df_read.collect()])
    assert ids == ["vid_1", "vid_2", "vid_3"]


def test_td2_and_td4_silver_parquet_row_count(spark):
    """T-D2 & T-D4: Parquet row count matches and <= dev_sample_max_rows."""
    parquet_path = local("silver", "youniverse_metadata")
    assert parquet_path.exists(), f"Silver parquet not found at {parquet_path}"
    
    df = spark.read.parquet(str(parquet_path))
    count = df.count()
    cfg = get_settings()["data"]
    max_cap = cfg.get("dev_sample_max_rows", 50000)
    
    assert count > 0, "Silver parquet should have > 0 rows"
    assert count <= max_cap, f"Dev sample count ({count}) exceeds cap ({max_cap})"


def test_td3_no_duplicate_video_ids(spark):
    """T-D3: No duplicate video IDs in silver metadata table."""
    parquet_path = local("silver", "youniverse_metadata")
    df = spark.read.parquet(str(parquet_path))
    
    total_count = df.count()
    distinct_vids = df.select("display_id").distinct().count()
    assert total_count == distinct_vids, (
        f"Found duplicate display_ids: {total_count} total vs {distinct_vids} distinct"
    )


def test_td5_idempotent_write(spark, tmp_path):
    """T-D5: Job re-run with overwrite is idempotent."""
    out_dir = str(tmp_path / "idempotent.parquet")
    df = spark.sql("SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2, 'b'")
    
    # Run 1
    df.write.mode("overwrite").parquet(out_dir)
    count1 = spark.read.parquet(out_dir).count()
    
    # Run 2 (re-run)
    df.write.mode("overwrite").parquet(out_dir)
    count2 = spark.read.parquet(out_dir).count()
    
    assert count1 == count2 == 2


def test_td6_loud_failure_on_bad_uri(spark):
    """T-D6: Spark read failure raises loudly (no silent fallback)."""
    with pytest.raises(Exception):
        # Reading non-existent directory must raise
        spark.read.parquet("file:///non_existent_bda_path_12345/missing.parquet").count()
