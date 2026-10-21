"""
src/app/portfolio_optimizer.py
Phase 8 — In-app interactive greedy portfolio budget allocator.
Operates in pure Python using pandas without requiring Spark (T-A1).
"""
from __future__ import annotations

from typing import Any
import pandas as pd


def optimize_portfolio(
    creators_df: pd.DataFrame,
    budget_usd: float,
    rate_card: dict[str, float] | None = None,
    max_tier_share: float = 0.50,
) -> dict[str, Any]:
    """
    Greedy knapsack portfolio optimization under budget constraints.

    Parameters
    ----------
    creators_df : pd.DataFrame
        DataFrame with columns: channel_id, size_tier, median_views, promotion_potential_score
    budget_usd : float
        Total marketing budget in USD.
    rate_card : dict[str, float] | None
        CPM rate per tier (e.g. {'Nano': 15.0, 'Micro': 20.0, 'Macro': 25.0, 'Mega': 35.0}).
    max_tier_share : float
        Max fraction of budget that can go to a single tier (tier diversification).

    Returns
    -------
    dict with:
        selected_creators: list of dicts with allocations
        total_spent: float
        remaining_budget: float
        total_estimated_reach: int
        avg_score: float
        tier_breakdown: dict
    """
    if creators_df.empty or budget_usd <= 0:
        return {
            "selected_creators": [],
            "total_spent": 0.0,
            "remaining_budget": budget_usd,
            "total_estimated_reach": 0,
            "avg_score": 0.0,
            "tier_breakdown": {},
        }

    rates = rate_card or {"Nano": 15.0, "Micro": 20.0, "Macro": 25.0, "Mega": 35.0}

    df = creators_df.copy()

    # Ensure required columns
    if "size_tier" not in df.columns:
        df["size_tier"] = "Micro"
    if "median_views" not in df.columns:
        df["median_views"] = 1000.0
    if "promotion_potential_score" not in df.columns:
        df["promotion_potential_score"] = 50.0

    # Calculate cost per sponsored video: (median_views / 1000) * cpm
    df["cpm"] = df["size_tier"].map(lambda t: rates.get(t, 20.0))
    df["est_cost"] = (df["median_views"].clip(lower=100) / 1000.0) * df["cpm"]
    # Ensure reasonable cost floors
    tier_min_cost = {"Nano": 50.0, "Micro": 150.0, "Macro": 500.0, "Mega": 2000.0}
    df["est_cost"] = df.apply(lambda r: max(r["est_cost"], tier_min_cost.get(r["size_tier"], 100.0)), axis=1)

    # Score per dollar efficiency metric
    df["efficiency"] = df["promotion_potential_score"] / df["est_cost"]

    # Sort descending by efficiency
    sorted_df = df.sort_values(by=["efficiency", "promotion_potential_score"], ascending=False)

    selected: list[dict[str, Any]] = []
    total_spent = 0.0
    tier_spend: dict[str, float] = {t: 0.0 for t in rates}
    max_spend_per_tier = budget_usd * max_tier_share

    for _, row in sorted_df.iterrows():
        cost = float(row["est_cost"])
        tier = str(row["size_tier"])

        # Check budget constraint
        if total_spent + cost > budget_usd:
            continue

        # Check tier diversification constraint (if budget > 2 * cost)
        if budget_usd > 1000 and (tier_spend.get(tier, 0.0) + cost > max_spend_per_tier):
            continue

        selected.append({
            "channel_id": row.get("channel_id", ""),
            "size_tier": tier,
            "promotion_potential_score": round(float(row["promotion_potential_score"]), 1),
            "median_views": int(row.get("median_views", 0)),
            "est_cost_usd": round(cost, 2),
            "efficiency": round(float(row["efficiency"]), 4),
            "promo_lift": row.get("promo_lift_display", "N/A"),
        })
        total_spent += cost
        tier_spend[tier] = tier_spend.get(tier, 0.0) + cost

    total_reach = sum(c["median_views"] for c in selected)
    avg_score = round(sum(c["promotion_potential_score"] for c in selected) / len(selected), 1) if selected else 0.0

    return {
        "selected_creators": selected,
        "total_spent": round(total_spent, 2),
        "remaining_budget": round(budget_usd - total_spent, 2),
        "total_estimated_reach": total_reach,
        "avg_score": avg_score,
        "tier_breakdown": {t: round(s, 2) for t, s in tier_spend.items() if s > 0},
    }
