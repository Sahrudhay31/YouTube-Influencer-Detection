"""
src/influencer/features.py
Feature engineering for channels from silver video and sponsorship datasets.
Assigns size tiers based on dataset quantiles and Option B ground truth labels.
"""
from __future__ import annotations

import yaml
from pathlib import Path
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, StringType


def load_influencer_config(config_path: str = "config/influencer.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_channel_features(
    video_df: DataFrame,
    domain_df: DataFrame,
    sponsorship_df: DataFrame,
    config_path: str = "config/influencer.yaml",
) -> DataFrame:
    """
    Builds the complete feature set per channel, assigns ground-truth label, and assigns size tier.

    Parameters
    ----------
    video_df : DataFrame
        Silver video metadata (display_id, channel_id, duration, view_count, like_count, dislike_count, upload_date).
    domain_df : DataFrame
        Channel domain profile (channel_id, domain_purity, in_domain_share).
    sponsorship_df : DataFrame
        Channel sponsorship metrics (channel_id, sponsored_count, sponsored_rate, median_views).

    Returns
    -------
    DataFrame
        Complete channel feature dataset with label `label` and `size_tier`.
    """
    cfg = load_influencer_config(config_path)
    label_cfg = cfg["label_definition"]
    tier_cfg = cfg["tiers"]

    # 1. Video-level aggregation per channel
    # Parse upload_date timestamp
    ts_col = F.to_timestamp(F.col("upload_date"))
    video_with_ts = video_df.withColumn("_upload_ts", ts_col)

    channel_stats = video_with_ts.groupBy("channel_id").agg(
        F.count("*").alias("video_count"),
        F.round(F.avg("duration"), 2).alias("mean_duration"),
        F.percentile_approx("view_count", 0.5).alias("median_views"),
        F.sum("view_count").alias("_total_views"),
        F.sum(F.coalesce(F.col("like_count"), F.lit(0)) + F.coalesce(F.col("dislike_count"), F.lit(0))).alias("_total_engagement"),
        F.stddev("view_count").alias("_stddev_views"),
        F.avg("view_count").alias("_mean_views"),
        F.min("_upload_ts").alias("_earliest_upload"),
        F.max("_upload_ts").alias("_latest_upload"),
    )

    # 2. Derived behavioral features
    # Engagement rate = total engagement / max(1, total views)
    eng_rate = F.col("_total_engagement") / F.when(F.col("_total_views") > 0, F.col("_total_views")).otherwise(F.lit(1.0))

    # View consistency CV = stddev_views / max(1, mean_views) (coalesced to 0.0 if null for 1-video channels)
    cv_col = F.coalesce(
        F.col("_stddev_views") / F.when(F.col("_mean_views") > 0, F.col("_mean_views")).otherwise(F.lit(1.0)),
        F.lit(0.0)
    )

    # Channel age in days
    age_days = F.coalesce(
        (F.unix_timestamp("_latest_upload") - F.unix_timestamp("_earliest_upload")) / (24 * 3600.0),
        F.lit(0.0)
    )

    # Upload cadence in days = channel_age_days / max(1, video_count - 1)
    cadence_days = age_days / F.when(F.col("video_count") > 1, F.col("video_count") - 1).otherwise(F.lit(1.0))

    enriched = (
        channel_stats.withColumn("engagement_rate", F.round(eng_rate, 4))
        .withColumn("view_consistency_cv", F.round(cv_col, 4))
        .withColumn("channel_age_days", F.round(age_days, 1))
        .withColumn("upload_cadence_days", F.round(cadence_days, 1))
        .drop("_total_views", "_total_engagement", "_stddev_views", "_mean_views", "_earliest_upload", "_latest_upload")
    )

    # 3. Join with domain purity profile
    domain_sub = domain_df.select("channel_id", "domain_purity", "in_domain_share")
    enriched = enriched.join(domain_sub, on="channel_id", how="left").fillna(
        0.0, subset=["domain_purity", "in_domain_share"]
    )

    # 4. Join with sponsorship metrics to derive Option B label and size tiers
    spon_sub = sponsorship_df.select("channel_id", "sponsored_count", "sponsored_rate")
    enriched = enriched.join(spon_sub, on="channel_id", how="left").fillna(
        0.0, subset=["sponsored_count", "sponsored_rate"]
    )

    # 5. Define Ground Truth Label (Option B: Reach threshold AND Sponsorship count >= 1)
    reach_thresh = label_cfg["reach_threshold"]
    spon_thresh = label_cfg["sponsorship_threshold"]

    is_influencer = (F.col("median_views") >= reach_thresh) & (F.col("sponsored_count") >= spon_thresh)
    enriched = enriched.withColumn("label", F.when(is_influencer, F.lit(1.0)).otherwise(F.lit(0.0)))

    # 6. Assign Exhaustive and Mutually Exclusive Size Tiers
    # nano (< nano_max), micro (nano_max to micro_max), macro (micro_max to macro_max), mega (>= macro_max)
    nano_max = tier_cfg["nano_max"]
    micro_max = tier_cfg["micro_max"]
    macro_max = tier_cfg["macro_max"]

    tier_expr = (
        F.when(F.col("median_views") < nano_max, F.lit("nano"))
        .when((F.col("median_views") >= nano_max) & (F.col("median_views") < micro_max), F.lit("micro"))
        .when((F.col("median_views") >= micro_max) & (F.col("median_views") < macro_max), F.lit("macro"))
        .otherwise(F.lit("mega"))
    )

    return enriched.withColumn("size_tier", tier_expr)
