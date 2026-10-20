"""
src/classification/channel_rollup.py
Aggregate video-level domain predictions to channel level.
Computes channel domain, mean probability, and domain_purity.
"""
from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def rollup_channel_domain(
    video_preds_df: DataFrame,
    channel_col: str = "channel_id",
    pred_col: str = "prediction",
    prob_col: str = "probability",
) -> DataFrame:
    """
    Rolls up video predictions to channel level.

    Parameters
    ----------
    video_preds_df : DataFrame
        Must contain channel_col, pred_col, and optionally prob_col.

    Returns
    -------
    DataFrame
        Columns:
        - `channel_id`
        - `video_count`
        - `primary_domain` (e.g. 1.0 for in-domain, 0.0 for out-of-domain)
        - `domain_purity` (proportion of channel videos matching primary_domain, in [0, 1])
        - `in_domain_share` (share of videos predicted as in-domain)
    """
    # Total videos per channel
    total_window = Window.partitionBy(channel_col)

    # 1. Total count per channel
    with_counts = video_preds_df.withColumn("_total_videos", F.count("*").over(total_window))

    # 2. Count per (channel, prediction)
    grouped = with_counts.groupBy(channel_col, pred_col, "_total_videos").agg(
        F.count("*").alias("_domain_video_count")
    )

    # 3. Find primary domain (the prediction with maximum count for this channel)
    rank_window = Window.partitionBy(channel_col).orderBy(F.desc("_domain_video_count"), F.desc(pred_col))
    ranked = grouped.withColumn("_rank", F.row_number().over(rank_window))

    primary_df = ranked.filter(F.col("_rank") == 1).select(
        F.col(channel_col),
        F.col("_total_videos").alias("video_count"),
        F.col(pred_col).alias("primary_domain"),
        (F.col("_domain_video_count") / F.col("_total_videos")).alias("domain_purity"),
    )

    # 4. Compute in_domain_share (share where pred == 1.0)
    in_domain_counts = (
        video_preds_df.filter(F.col(pred_col) == 1.0)
        .groupBy(channel_col)
        .agg(F.count("*").alias("_in_domain_count"))
    )

    result = primary_df.join(in_domain_counts, on=channel_col, how="left").fillna(0, subset=["_in_domain_count"])
    result = result.withColumn("in_domain_share", F.col("_in_domain_count") / F.col("video_count")).drop("_in_domain_count")

    return result
