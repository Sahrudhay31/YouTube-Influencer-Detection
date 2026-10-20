"""
src/classification/dataset_splitter.py
Split dataset into train, validation, and test sets strictly by CHANNEL.
Prevents video-level data leakage between splits.
"""
from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from src.common.config import get_settings


def split_by_channel(
    df: DataFrame,
    ratios: list[float] | None = None,
    seed: int | None = None,
) -> tuple[DataFrame, DataFrame, DataFrame]:
    """
    Split a DataFrame into train, val, and test partitions strictly by `channel_id`.

    Parameters
    ----------
    df : DataFrame
        Must contain column `channel_id`.
    ratios : list[float] | None
        [train_ratio, val_ratio, test_ratio], default [0.70, 0.15, 0.15].
    seed : int | None
        Random seed for reproducibility.

    Returns
    -------
    tuple[DataFrame, DataFrame, DataFrame]
        (train_df, val_df, test_df)
    """
    cfg = get_settings().get("data", {})
    if ratios is None:
        ratios = cfg.get("split_ratios", [0.70, 0.15, 0.15])
    if seed is None:
        seed = cfg.get("seed", 42)

    assert len(ratios) == 3, f"Expected 3 split ratios, got {len(ratios)}"
    assert abs(sum(ratios) - 1.0) < 1e-4, f"Ratios must sum to 1.0, got {sum(ratios)}"

    # 1. Extract distinct channels
    distinct_channels = df.select("channel_id").distinct()

    # 2. Split channel IDs deterministically
    train_ch, val_ch, test_ch = distinct_channels.randomSplit(ratios, seed=seed)

    # 3. Join back to full dataset
    # Tag each split explicitly
    train_ch = train_ch.withColumn("_split", F.lit("train"))
    val_ch = val_ch.withColumn("_split", F.lit("val"))
    test_ch = test_ch.withColumn("_split", F.lit("test"))

    channel_splits = train_ch.unionByName(val_ch).unionByName(test_ch)

    tagged_df = df.join(channel_splits, on="channel_id", how="inner")

    train_df = tagged_df.filter(F.col("_split") == "train").drop("_split")
    val_df = tagged_df.filter(F.col("_split") == "val").drop("_split")
    test_df = tagged_df.filter(F.col("_split") == "test").drop("_split")

    return train_df, val_df, test_df
