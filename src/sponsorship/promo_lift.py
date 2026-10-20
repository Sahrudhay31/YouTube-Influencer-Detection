"""
src/sponsorship/promo_lift.py
Channel-level sponsorship metrics and Promo Lift computation.

Rules (Phase 4):
- promo_lift = median(views on sponsored) / median(views on non-sponsored)
- Requires minimum sponsored and non-sponsored videos (default 3 each); else returns None (null).
- Never returns 0 when evidence is insufficient; strictly null.
- Zero-division protected: returns None if baseline is 0.
"""
from __future__ import annotations

import yaml
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StructType, StructField, StringType, LongType


def compute_channel_promo_lift(
    df: DataFrame,
    config_path: str = "config/sponsorship.yaml",
    min_sponsored: int | None = None,
    min_nonsponsored: int | None = None,
) -> DataFrame:
    """
    Computes per-channel sponsored video counts, sponsored rate, and promo lift.

    Parameters
    ----------
    df : DataFrame
        Must contain: `channel_id`, `is_sponsored`, `view_count`.
    config_path : str
        Path to sponsorship configuration.
    min_sponsored : int | None
        Override min sponsored videos needed for lift calculation.
    min_nonsponsored : int | None
        Override min non-sponsored videos needed for lift calculation.

    Returns
    -------
    DataFrame
        Columns:
        - `channel_id`
        - `total_videos`
        - `sponsored_count`
        - `nonsponsored_count`
        - `sponsored_rate`
        - `median_views_sponsored`
        - `median_views_nonsponsored`
        - `promo_lift` (DoubleType, nullable)
    """
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    thresholds = cfg.get("thresholds", {})
    if min_sponsored is None:
        min_sponsored = thresholds.get("min_sponsored_videos_for_lift", 3)
    if min_nonsponsored is None:
        min_nonsponsored = thresholds.get("min_nonsponsored_videos_for_lift", 3)

    # 1. Channel aggregate counts
    counts_df = df.groupBy("channel_id").agg(
        F.count("*").alias("total_videos"),
        F.sum(F.when(F.col("is_sponsored") == True, 1).otherwise(0)).alias("sponsored_count"),
        F.sum(F.when(F.col("is_sponsored") == False, 1).otherwise(0)).alias("nonsponsored_count"),
    )
    counts_df = counts_df.withColumn("sponsored_rate", F.col("sponsored_count") / F.col("total_videos"))

    # 2. Compute approximate median (50th percentile) views for sponsored and non-sponsored
    # percent_approx with accuracy=0.01 provides reliable median estimation in Spark SQL
    median_spon = (
        df.filter(F.col("is_sponsored") == True)
        .groupBy("channel_id")
        .agg(F.percentile_approx("view_count", 0.5).alias("median_views_sponsored"))
    )

    median_nonspon = (
        df.filter(F.col("is_sponsored") == False)
        .groupBy("channel_id")
        .agg(F.percentile_approx("view_count", 0.5).alias("median_views_nonsponsored"))
    )

    merged = (
        counts_df.join(median_spon, on="channel_id", how="left")
        .join(median_nonspon, on="channel_id", how="left")
    )

    # 3. Calculate promo_lift with strict null guards
    # If sponsored_count < min_sponsored OR nonsponsored_count < min_nonsponsored OR baseline <= 0 -> NULL
    valid_condition = (
        (F.col("sponsored_count") >= min_sponsored)
        & (F.col("nonsponsored_count") >= min_nonsponsored)
        & (F.col("median_views_nonsponsored").isNotNull())
        & (F.col("median_views_nonsponsored") > 0.0)
        & (F.col("median_views_sponsored").isNotNull())
    )

    lift_col = F.when(
        valid_condition,
        F.col("median_views_sponsored") / F.col("median_views_nonsponsored"),
    ).otherwise(F.lit(None).cast(DoubleType()))

    return merged.withColumn("promo_lift", lift_col)
