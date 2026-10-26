"""
src/app/leaderboard_logic.py
Pure filtering, tie-breaking, sorting, pagination, and CSV export logic for the Find Influencers leaderboard.
Separated from Streamlit UI to enable complete headless unit testing.
"""
from __future__ import annotations

import math
from typing import Any
import pandas as pd

from src.app.formatters import (
    format_subscribers,
    format_views,
    format_percentage,
    format_promo_lift,
)
from src.app.evidence import get_evidence_badge


DISCLAIMER_COMMENT = (
    "# Research & Governance Disclaimer: Predicted promotion potential is computed from public YouTube "
    "engagement signals; it does NOT represent measured sales, commercial ROI, or confidential platform earnings.\n"
)


def filter_and_rank_creators(
    df: pd.DataFrame,
    search_query: str = "",
    selected_tiers: list[str] | None = None,
    min_score: float = 0.0,
    min_engagement_pct: float = 0.0,
    full_evidence_only: bool = False,
    only_sponsored: bool = False,
    sponsor_range: tuple[int, int] | None = None,
    rank_full_evidence_first: bool = True,
) -> pd.DataFrame:
    """
    Pure filtering and deterministic ranking of creator dataframe.
    Ties in percentile score are broken deterministically by raw_score, then median_views, then channel_name.
    """
    if df.empty:
        return df.copy()

    filtered = df.copy()

    # 1. Size Tier Filter
    if selected_tiers is not None and len(selected_tiers) > 0 and "size_tier" in filtered.columns:
        # Match case-insensitively
        norm_tiers = [t.lower() for t in selected_tiers]
        filtered = filtered[filtered["size_tier"].astype(str).str.lower().isin(norm_tiers)]

    # 2. Minimum Promotion Potential Score
    if "promotion_potential_score" in filtered.columns and min_score > 0.0:
        filtered = filtered[filtered["promotion_potential_score"] >= min_score]

    # 3. Minimum Engagement Rate
    if "engagement_rate" in filtered.columns and min_engagement_pct > 0.0:
        # Engagement rate in df is typically in decimal form (e.g. 0.05 for 5%)
        # but could be in percentage form (> 1.0)
        # We handle decimal vs percent comparison safely
        thresh_dec = min_engagement_pct / 100.0
        filtered = filtered[
            filtered["engagement_rate"].apply(
                lambda val: False if pd.isna(val) else (val >= thresh_dec if val <= 1.0 else val >= min_engagement_pct)
            )
        ]

    # 4. Search Query (channel name or channel id)
    if search_query and search_query.strip():
        q = search_query.strip().lower()
        name_match = filtered["channel_name"].astype(str).str.lower().str.contains(q, na=False)
        id_match = filtered["channel_id"].astype(str).str.lower().str.contains(q, na=False)
        filtered = filtered[name_match | id_match]

    # 5. Full Evidence Only
    if full_evidence_only and "partial_evidence" in filtered.columns:
        filtered = filtered[filtered["partial_evidence"] == False]

    # 6. Only Sponsored History
    if only_sponsored and "sponsored_count" in filtered.columns:
        filtered = filtered[filtered["sponsored_count"] > 0]

    # 7. Sponsored Range Filter (min, max)
    if sponsor_range is not None and "sponsored_count" in filtered.columns:
        min_sp, max_sp = sponsor_range
        filtered = filtered[(filtered["sponsored_count"] >= min_sp) & (filtered["sponsored_count"] <= max_sp)]

    # 8. Deterministic Ranking & Tie-breaking
    # Build sort keys
    sort_cols: list[str] = []
    ascending_flags: list[bool] = []

    if rank_full_evidence_first and "partial_evidence" in filtered.columns:
        # partial_evidence False (0) comes before True (1)
        sort_cols.append("partial_evidence")
        ascending_flags.append(True)

    if "promotion_potential_score" in filtered.columns:
        sort_cols.append("promotion_potential_score")
        ascending_flags.append(False)

    if "raw_score" in filtered.columns:
        sort_cols.append("raw_score")
        ascending_flags.append(False)

    if "median_views" in filtered.columns:
        sort_cols.append("median_views")
        ascending_flags.append(False)

    if "channel_name" in filtered.columns:
        sort_cols.append("channel_name")
        ascending_flags.append(True)

    if sort_cols:
        filtered = filtered.sort_values(by=sort_cols, ascending=ascending_flags).reset_index(drop=True)

    return filtered


def paginate_dataframe(
    df: pd.DataFrame,
    page_number: int = 1,
    page_size: int = 25,
) -> tuple[pd.DataFrame, int, int]:
    """
    Paginate dataframe.
    Returns (sliced_df, total_rows, total_pages).
    """
    total_rows = len(df)
    if total_rows == 0 or page_size <= 0:
        return df.iloc[0:0].copy(), 0, 1

    total_pages = max(1, math.ceil(total_rows / page_size))
    page_number = max(1, min(page_number, total_pages))

    start_idx = (page_number - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)

    sliced = df.iloc[start_idx:end_idx].copy().reset_index(drop=True)
    return sliced, total_rows, total_pages


def build_export_csv(df: pd.DataFrame) -> str:
    """
    Serialize filtered/ranked dataframe to CSV string with compliance header comment.
    """
    csv_text = df.to_csv(index=False)
    return DISCLAIMER_COMMENT + csv_text
