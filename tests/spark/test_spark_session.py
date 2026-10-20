"""
tests/spark/test_spark_session.py
Smoke test for central Spark session factory and basic DataFrame operations.
Uses local[2] per Section 8 guidelines.
"""
from __future__ import annotations

import pytest
from src.common.spark_session import get_spark


def test_ts1_spark_session_creates_and_computes():
    """Verify that get_spark() initializes a working local session."""
    spark = get_spark(app_name="bda-spark-smoke-test", local_mode=True)
    assert spark is not None

    df = spark.createDataFrame(
        [(1, "channel_1", 1000), (2, "channel_2", 2500)],
        ["id", "channel_id", "view_count"],
    )
    assert df.count() == 2
    assert "channel_id" in df.columns

    collected = [row.channel_id for row in df.collect()]
    assert collected == ["channel_1", "channel_2"]
