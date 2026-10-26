"""
src/app/evidence.py
Evidence level badges and dynamic weight renormalisation explanation generator.
Adheres strictly to ADR-008 and config/scoring.yaml hypothesis weights.
"""
from __future__ import annotations

import math
from typing import Any, Mapping
import pandas as pd

# Base hypothesis weights from config/scoring.yaml
COMPONENT_WEIGHTS: dict[str, float] = {
    "comp_fit": 25.0,
    "comp_conversion_evidence": 25.0,
    "comp_real_reach": 15.0,
    "comp_engagement_quality": 15.0,
    "comp_momentum": 10.0,
    "comp_consistency": 10.0,
}

COMPONENT_DISPLAY_NAMES: dict[str, str] = {
    "comp_fit": "Domain / Product Fit",
    "comp_conversion_evidence": "Conversion Evidence",
    "comp_real_reach": "Real Reach",
    "comp_engagement_quality": "Engagement Quality",
    "comp_momentum": "Cadence Momentum",
    "comp_consistency": "View Consistency",
}


def get_missing_components(row_or_dict: Mapping[str, Any] | pd.Series) -> list[str]:
    """
    Return list of component keys that are missing, null, or NaN.
    """
    missing = []
    for comp_key in COMPONENT_WEIGHTS:
        val = row_or_dict.get(comp_key)
        if val is None or pd.isna(val):
            missing.append(comp_key)
    return missing


def compute_renormalisation(missing_keys: list[str]) -> tuple[float, float, str]:
    """
    Given missing component keys, compute:
      - active_weight: sum of weights for available components
      - rescale_factor: multiplier (100.0 / active_weight)
      - message: human-readable explanation

    Returns (active_weight, rescale_factor, message).
    """
    total_weight = sum(COMPONENT_WEIGHTS.values())  # 100.0
    missing_weight = sum(COMPONENT_WEIGHTS.get(k, 0.0) for k in missing_keys)
    active_weight = max(total_weight - missing_weight, 1e-6)
    rescale_factor = total_weight / active_weight

    if not missing_keys:
        return (
            active_weight,
            1.0,
            "All 6 score components available. Full evidence profile (no renormalisation applied).",
        )

    # Build description of missing components with weights
    missing_desc = [
        f"{COMPONENT_DISPLAY_NAMES.get(k, k)} ({int(COMPONENT_WEIGHTS[k])}% weight)"
        for k in missing_keys
    ]
    items_str = ", ".join(missing_desc)
    msg = f"{items_str} missing; remaining weights rescaled x{rescale_factor:.2f}"
    return active_weight, rescale_factor, msg


def get_evidence_badge(partial_evidence: bool | Any) -> dict[str, str]:
    """
    Returns visual badge specification for leaderboard and creator card.
    High = all 6 components available.
    Partial = dynamically renormalised due to missing components.
    """
    is_partial = bool(partial_evidence) if pd.notnull(partial_evidence) else False
    if is_partial:
        return {
            "tier": "Partial",
            "label": "Partial Evidence",
            "short_label": "Partial",
            "color": "#F59E0B",  # Amber
            "bg_color": "rgba(245, 158, 11, 0.15)",
            "border_color": "rgba(245, 158, 11, 0.4)",
            "tooltip": "Some data streams (e.g. sponsored history or comments) were missing and weights were dynamically rescaled to 100%.",
        }
    return {
        "tier": "High",
        "label": "Full Evidence",
        "short_label": "High",
        "color": "#10B981",  # Emerald / Green
        "bg_color": "rgba(16, 185, 129, 0.15)",
        "border_color": "rgba(16, 185, 129, 0.4)",
        "tooltip": "All 6 components (fit, conversion, reach, engagement, momentum, consistency) measured directly.",
    }
