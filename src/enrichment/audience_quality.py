"""
src/enrichment/audience_quality.py
Phase 6 — Audience Quality & Authenticity Checks.

Computes four channel-level audience quality signals from sampled comments:

  1. loyal_commenter_share     — fraction of unique hashed authors who appear
                                 across >= loyal_videos_min distinct videos.
  2. duplicate_comment_share   — fraction of comments that are exact duplicates
                                 (same text, same hashed author).
  3. top1_commenter_share      — fraction of all comments driven by the single
                                 most prolific (hashed) author.
  4. top5_commenter_share      — same but for the top-5 commenters combined.
  5. comment_spike_flag        — True if any video's comment count is
                                 spike_multiplier × channel_mean.

Authenticity flags are derived by comparing each signal against the thresholds
in config/enrichment.yaml → authenticity.

Outputs:
  - data/gold/audience_quality  (Parquet, one row per channel)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)
from pyspark.sql.window import Window

from src.common.logging_setup import setup_logging
from src.common.paths import local

logger = setup_logging(__name__)

_ENRICHMENT_CFG_PATH = Path(__file__).resolve().parents[2] / "config" / "enrichment.yaml"


def load_enrichment_config() -> dict:
    with open(_ENRICHMENT_CFG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ─────────────────────────────────────────────────────────────────────────────
# Audience quality schema
# ─────────────────────────────────────────────────────────────────────────────

AUDIENCE_QUALITY_SCHEMA = StructType([
    StructField("channel_id",              StringType(),  False),
    StructField("n_comments_sampled",      LongType(),    False),
    StructField("n_unique_authors",        LongType(),    False),
    StructField("loyal_commenter_share",   DoubleType(),  True),
    StructField("duplicate_comment_share", DoubleType(),  True),
    StructField("top1_commenter_share",    DoubleType(),  True),
    StructField("top5_commenter_share",    DoubleType(),  True),
    StructField("comment_spike_flag",      BooleanType(), True),
    StructField("duplicate_flag",          BooleanType(), True),
    StructField("top1_flag",               BooleanType(), True),
    StructField("top5_flag",               BooleanType(), True),
    StructField("any_authenticity_flag",   BooleanType(), True),
    StructField("intent_rate",             DoubleType(),  True),
])


# ─────────────────────────────────────────────────────────────────────────────
# Signal computation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _loyal_commenter_share(df: DataFrame, loyal_videos_min: int) -> DataFrame:
    """
    Compute the fraction of unique hashed authors who appear in >= loyal_videos_min
    distinct videos for each channel.

    Returns a DataFrame with columns: channel_id, loyal_commenter_share, n_unique_authors.
    """
    # Count distinct videos per (channel, author)
    author_video_counts = (
        df.groupBy("channel_id", "author_id_hashed")
          .agg(F.countDistinct("video_id").alias("n_videos_commented"))
    )
    # Mark loyal authors
    loyal_authors = author_video_counts.withColumn(
        "is_loyal",
        F.col("n_videos_commented") >= loyal_videos_min,
    )
    # Aggregate per channel
    channel_loyalty = loyal_authors.groupBy("channel_id").agg(
        F.count("*").alias("n_unique_authors"),
        F.sum(F.col("is_loyal").cast("int")).alias("n_loyal_authors"),
    )
    channel_loyalty = channel_loyalty.withColumn(
        "loyal_commenter_share",
        (F.col("n_loyal_authors") / F.col("n_unique_authors")).cast(DoubleType()),
    )
    return channel_loyalty.select("channel_id", "n_unique_authors", "loyal_commenter_share")


def _duplicate_comment_share(df: DataFrame) -> DataFrame:
    """
    Fraction of comments that are exact duplicates (same channel, author, text).
    Returns DataFrame with: channel_id, n_comments_sampled, duplicate_comment_share.
    """
    # Canonical: first occurrence per (channel, author, text) is NOT a duplicate
    w = Window.partitionBy("channel_id", "author_id_hashed", "text").orderBy("comment_id")
    df_ranked = df.withColumn("dup_rank", F.row_number().over(w))
    df_dup = df_ranked.withColumn("is_dup", (F.col("dup_rank") > 1).cast("int"))

    result = df_dup.groupBy("channel_id").agg(
        F.count("*").alias("n_comments_sampled"),
        F.avg("is_dup").cast(DoubleType()).alias("duplicate_comment_share"),
    )
    return result


def _top_commenter_shares(df: DataFrame) -> DataFrame:
    """
    Compute top-1 and top-5 commenter share per channel.
    Returns DataFrame with: channel_id, top1_commenter_share, top5_commenter_share.
    """
    # Comment counts per (channel, author)
    author_counts = df.groupBy("channel_id", "author_id_hashed").agg(
        F.count("*").alias("author_comment_count")
    )
    # Total comments per channel
    channel_totals = df.groupBy("channel_id").agg(
        F.count("*").alias("total_comments")
    )
    # Rank authors by count within each channel
    w_rank = Window.partitionBy("channel_id").orderBy(F.col("author_comment_count").desc())
    author_ranks = author_counts.withColumn("author_rank", F.row_number().over(w_rank))

    # Join with channel totals
    author_ranked = author_ranks.join(channel_totals, on="channel_id", how="left")
    author_ranked = author_ranked.withColumn(
        "author_share",
        (F.col("author_comment_count") / F.col("total_comments")).cast(DoubleType()),
    )

    # Top-1 share
    top1 = (
        author_ranked.filter(F.col("author_rank") == 1)
        .select("channel_id", F.col("author_share").alias("top1_commenter_share"))
    )
    # Top-5 share (sum of shares for top 5 authors)
    top5 = (
        author_ranked.filter(F.col("author_rank") <= 5)
        .groupBy("channel_id")
        .agg(F.sum("author_share").cast(DoubleType()).alias("top5_commenter_share"))
    )
    result = top1.join(top5, on="channel_id", how="outer")
    return result


def _comment_spike_flag(df: DataFrame, spike_multiplier: float) -> DataFrame:
    """
    Flag channels where any single video has > spike_multiplier × channel_mean
    comment count.

    Returns DataFrame with: channel_id, comment_spike_flag.
    """
    video_counts = df.groupBy("channel_id", "video_id").agg(
        F.count("*").alias("video_comment_count")
    )
    channel_means = video_counts.groupBy("channel_id").agg(
        F.mean("video_comment_count").alias("channel_mean_comments"),
        F.max("video_comment_count").alias("channel_max_comments"),
    )
    result = channel_means.withColumn(
        "comment_spike_flag",
        (F.col("channel_max_comments") > spike_multiplier * F.col("channel_mean_comments")).cast(BooleanType()),
    )
    return result.select("channel_id", "comment_spike_flag")


def _intent_rate(df: DataFrame) -> DataFrame:
    """Average purchase_intent per channel."""
    return df.groupBy("channel_id").agg(
        F.avg("purchase_intent").cast(DoubleType()).alias("intent_rate")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_audience_quality(
    df_comments: DataFrame,
    ecfg: dict,
) -> DataFrame:
    """
    Compute all audience quality signals and authenticity flags from the
    comment sample DataFrame.

    Parameters
    ----------
    df_comments : Spark DataFrame conforming to comment_sampler.COMMENT_SCHEMA
    ecfg        : parsed enrichment.yaml

    Returns
    -------
    Spark DataFrame conforming to AUDIENCE_QUALITY_SCHEMA (one row per channel).
    """
    loyalty_cfg = ecfg["loyalty"]
    auth_cfg = ecfg["authenticity"]

    loyal_min = loyalty_cfg["loyal_videos_min"]
    dup_max = auth_cfg["duplicate_comment_max_share"]
    top1_max = auth_cfg["top1_commenter_max_share"]
    top5_max = auth_cfg["top5_commenters_max_share"]
    spike_mult = auth_cfg["spike_multiplier"]

    # Compute individual signals
    df_loyal = _loyal_commenter_share(df_comments, loyal_min)
    df_dup = _duplicate_comment_share(df_comments)
    df_top = _top_commenter_shares(df_comments)
    df_spike = _comment_spike_flag(df_comments, spike_mult)
    df_intent = _intent_rate(df_comments)

    # Join all signals on channel_id
    df_quality = (
        df_dup
        .join(df_loyal, on="channel_id", how="left")
        .join(df_top, on="channel_id", how="left")
        .join(df_spike, on="channel_id", how="left")
        .join(df_intent, on="channel_id", how="left")
    )

    # Derive authenticity flags
    df_quality = (
        df_quality
        .withColumn("duplicate_flag",
            (F.col("duplicate_comment_share") > dup_max).cast(BooleanType()))
        .withColumn("top1_flag",
            (F.col("top1_commenter_share") > top1_max).cast(BooleanType()))
        .withColumn("top5_flag",
            (F.col("top5_commenter_share") > top5_max).cast(BooleanType()))
        .withColumn("comment_spike_flag",
            F.coalesce(F.col("comment_spike_flag"), F.lit(False)))
        .withColumn("any_authenticity_flag",
            (
                F.col("duplicate_flag") |
                F.col("top1_flag") |
                F.col("top5_flag") |
                F.col("comment_spike_flag")
            ).cast(BooleanType()))
    )

    # Enforce schema (select in order, fill nulls)
    df_quality = df_quality.select(
        F.col("channel_id"),
        F.coalesce(F.col("n_comments_sampled"), F.lit(0)).cast(LongType()).alias("n_comments_sampled"),
        F.coalesce(F.col("n_unique_authors"), F.lit(0)).cast(LongType()).alias("n_unique_authors"),
        F.col("loyal_commenter_share").cast(DoubleType()),
        F.col("duplicate_comment_share").cast(DoubleType()),
        F.col("top1_commenter_share").cast(DoubleType()),
        F.col("top5_commenter_share").cast(DoubleType()),
        F.col("comment_spike_flag").cast(BooleanType()),
        F.col("duplicate_flag").cast(BooleanType()),
        F.col("top1_flag").cast(BooleanType()),
        F.col("top5_flag").cast(BooleanType()),
        F.col("any_authenticity_flag").cast(BooleanType()),
        F.col("intent_rate").cast(DoubleType()),
    )

    n = df_quality.count()
    flagged = df_quality.filter(F.col("any_authenticity_flag") == True).count()
    logger.info(
        "[AudienceQuality] Computed quality for %d channels; %d flagged for authenticity issues.",
        n, flagged
    )
    return df_quality


def save_audience_quality(df_quality: DataFrame, ecfg: dict, mode: str = "dry_run") -> str:
    """Write audience quality Parquet. In dry-run, appends '.dryrun' to path."""
    out_path = ecfg["output"]["audience_quality"]
    if mode == "dry_run":
        out_path = out_path.rstrip("/") + ".dryrun"
    df_quality.write.mode("overwrite").parquet(out_path)
    logger.info("[AudienceQuality] Saved to %s", out_path)
    return out_path
