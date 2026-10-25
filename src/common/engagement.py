"""
src/common/engagement.py
Unified canonical engagement rate calculation.

Canonical definition:
    engagement_rate = (likes + dislikes) / max(views, 1)

Documented in docs/data_dictionary.md and used across:
- src/influencer/features.py (channel feature engineering)
- src/ranking/backtest.py (pre- and post-cutoff evaluation)
- src/ranking/score.py (promotion-potential scoring)
"""
from __future__ import annotations

from pyspark.sql import Column, functions as F


def calculate_engagement_rate(likes: float | int, dislikes: float | int, views: float | int) -> float:
    """
    Pure Python / scalar canonical engagement rate:
        (coalesce(likes, 0) + coalesce(dislikes, 0)) / max(views, 1.0)
    """
    l = float(likes) if likes is not None and not (isinstance(likes, float) and likes != likes) else 0.0
    d = float(dislikes) if dislikes is not None and not (isinstance(dislikes, float) and dislikes != dislikes) else 0.0
    v = float(views) if views is not None and not (isinstance(views, float) and views != views) else 0.0
    if v <= 0.0:
        return 0.0
    return min(1.0, max(0.0, (l + d) / v))



def calculate_engagement_expr(
    like_col: str | Column = "like_count",
    dislike_col: str | Column = "dislike_count",
    view_col: str | Column = "view_count",
) -> Column:
    """
    Returns a PySpark Column expression computing the canonical engagement rate:
        (coalesce(likes, 0) + coalesce(dislikes, 0)) / greatest(coalesce(views, 0), 1.0)
    """
    likes = F.col(like_col) if isinstance(like_col, str) else like_col
    dislikes = F.col(dislike_col) if isinstance(dislike_col, str) else dislike_col
    views = F.col(view_col) if isinstance(view_col, str) else view_col

    likes_safe = F.coalesce(likes, F.lit(0.0)).cast("double")
    dislikes_safe = F.coalesce(dislikes, F.lit(0.0)).cast("double")
    views_safe = F.coalesce(views, F.lit(0.0)).cast("double")

    total_engagement = likes_safe + dislikes_safe
    denom = F.when(views_safe > 0.0, views_safe).otherwise(F.lit(1.0))

    return total_engagement / denom


def calculate_channel_engagement_expr(
    total_likes_col: str | Column = "total_likes",
    total_dislikes_col: str | Column = "total_dislikes",
    total_views_col: str | Column = "total_views",
) -> Column:
    """
    Computes engagement rate on channel-aggregated metrics.
    """
    return calculate_engagement_expr(
        like_col=total_likes_col,
        dislike_col=total_dislikes_col,
        view_col=total_views_col,
    )
