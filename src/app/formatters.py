"""
src/app/formatters.py
Pure formatting utilities for InfluencerAI presentation metrics.
Supports numbers, percentages, currency, and counts with robust edge-case handling.
"""
from __future__ import annotations

import math
from typing import Any
import pandas as pd


def format_subscribers(val: Any) -> str:
    """
    Format subscriber count cleanly:
      - >= 1,000,000 -> 3.02M
      - >= 1,000 -> 914K or 11.4K
      - < 1,000 -> raw integer
      - None / NaN / negative -> 'n/a' or '0'
    """
    if val is None or pd.isna(val):
        return "n/a"
    try:
        num = float(val)
    except (ValueError, TypeError):
        return "n/a"

    if math.isnan(num):
        return "n/a"
    if num <= 0:
        return "0"

    if num >= 1_000_000:
        val_m = num / 1_000_000.0
        # If integer million, e.g. 3.0M -> 3M, otherwise 3.02M or 3.1M
        return f"{val_m:.2f}".rstrip("0").rstrip(".") + "M"
    if num >= 1_000:
        val_k = num / 1_000.0
        if val_k >= 100:
            return f"{val_k:.0f}K"
        return f"{val_k:.1f}".rstrip("0").rstrip(".") + "K"
    return str(int(num))


def format_views(val: Any) -> str:
    """
    Format view count with comma thousands separators and zero decimals.
    e.g. 1234567 -> '1,234,567'
    """
    if val is None or pd.isna(val):
        return "n/a"
    try:
        num = float(val)
    except (ValueError, TypeError):
        return "n/a"

    if math.isnan(num):
        return "n/a"
    return f"{int(round(num)):,}"


def format_percentage(val: Any, decimals: int = 2) -> str:
    """
    Format decimal or percentage to string with '%'.
    If val <= 1.0 (e.g. 0.1111), converts to percentage (11.11%).
    If val > 1.0 (e.g. 11.11), formats as (11.11%).
    """
    if val is None or pd.isna(val):
        return "n/a"
    try:
        num = float(val)
    except (ValueError, TypeError):
        return "n/a"

    if math.isnan(num):
        return "n/a"

    # If already a percentage (greater than 1.0, e.g. 11.11), don't multiply by 100
    # unless it's genuinely meant as fraction (e.g. 0.05 -> 5.00%)
    pct = num * 100.0 if abs(num) <= 1.0 and num != 0.0 else num
    return f"{pct:.{decimals}f}%"


def format_promo_lift(val: Any) -> str:
    """
    Format promo lift multiplier, e.g. 1.41 -> '1.41x'.
    Returns 'N/A' when missing, NaN, or non-positive.
    """
    if val is None or pd.isna(val):
        return "N/A"
    try:
        num = float(val)
    except (ValueError, TypeError):
        return "N/A"

    if math.isnan(num) or num <= 0:
        return "N/A"
    return f"{num:.2f}x"


def format_currency(val: Any) -> str:
    """
    Format currency as integer or 2-decimal USD string.
    e.g. 15000 -> '$15,000'
    """
    if val is None or pd.isna(val):
        return "$0"
    try:
        num = float(val)
    except (ValueError, TypeError):
        return "$0"

    if math.isnan(num):
        return "$0"
    if num.is_integer():
        return f"${int(num):,}"
    return f"${num:,.2f}"
