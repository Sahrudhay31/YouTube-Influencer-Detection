"""
src/app/portfolio_optimizer.py
In-app interactive greedy portfolio budget allocator.
Operates in pure Python using pandas without requiring Spark (T-A1).
Implements configurable CPM + overhead rate cards and typical view calculations.
"""
from __future__ import annotations

from typing import Any, Mapping
import pandas as pd


def get_tier_rates(
    tier: str,
    rate_card: Mapping[str, Any] | None = None,
) -> tuple[float, float]:
    """
    Extract (CPM, fixed_overhead) for a given tier from the rate card.
    Handles nested dict format {'cpm': ..., 'overhead': ...} or flat CPM float.
    """
    tier_cap = tier.capitalize()
    default_card = {
        "Nano": {"cpm": 15.0, "overhead": 50.0},
        "Micro": {"cpm": 20.0, "overhead": 100.0},
        "Mid": {"cpm": 22.5, "overhead": 175.0},
        "Macro": {"cpm": 25.0, "overhead": 250.0},
        "Mega": {"cpm": 35.0, "overhead": 500.0},
    }
    card = rate_card or default_card
    info = card.get(tier_cap, card.get(tier.lower(), default_card.get(tier_cap, {"cpm": 20.0, "overhead": 100.0})))

    if isinstance(info, dict):
        cpm = float(info.get("cpm", 20.0))
        overhead = float(info.get("overhead", info.get("fixed_overhead", 100.0)))
        return cpm, overhead
    elif isinstance(info, (int, float)):
        # Flat CPM without overhead
        return float(info), default_card.get(tier_cap, {}).get("overhead", 100.0)
    return 20.0, 100.0


def optimize_portfolio(
    creators_df: pd.DataFrame,
    budget_usd: float,
    rate_card: Mapping[str, Any] | None = None,
    max_tier_share: float = 0.50,
    max_creators: int | None = None,
) -> dict[str, Any]:
    """
    Greedy knapsack portfolio optimization under budget constraints.

    Cost formula:
        Cost = (median_views / 1,000) * CPM + fixed_overhead
    Efficiency:
        Score / Cost

    Parameters
    ----------
    creators_df : pd.DataFrame
        DataFrame with channel metrics.
    budget_usd : float
        Total marketing budget in USD.
    rate_card : dict | None
        CPM and overhead rates by tier.
    max_tier_share : float
        Max fraction of budget that can go to any single size tier.
    max_creators : int | None
        Optional maximum number of creators to select.

    Returns
    -------
    dict with:
        selected_creators: list of dicts with allocations
        total_spent: float
        remaining_budget: float
        total_typical_views: int
        avg_score: float
        tier_breakdown: dict
        cumulative_costs: list[float]
    """
    if creators_df.empty or budget_usd <= 0:
        return {
            "selected_creators": [],
            "total_spent": 0.0,
            "remaining_budget": budget_usd,
            "total_typical_views": 0,
            "avg_score": 0.0,
            "tier_breakdown": {},
            "cumulative_costs": [],
        }

    df = creators_df.copy()

    # Ensure required columns exist
    if "size_tier" not in df.columns:
        df["size_tier"] = "Micro"
    if "median_views" not in df.columns:
        df["median_views"] = 1000.0
    if "promotion_potential_score" not in df.columns:
        df["promotion_potential_score"] = 50.0

    # Calculate individual creator costs: (median_views / 1000) * cpm + overhead
    def calc_cost(row: pd.Series) -> float:
        tier = str(row.get("size_tier", "Micro"))
        cpm, overhead = get_tier_rates(tier, rate_card)
        views = max(float(row.get("median_views", 100.0)), 100.0)
        return round((views / 1000.0) * cpm + overhead, 2)

    df["est_cost"] = df.apply(calc_cost, axis=1)

    # Score per dollar efficiency metric
    df["efficiency"] = df["promotion_potential_score"] / df["est_cost"].clip(lower=1.0)

    # Sort descending by efficiency, secondary sort on promotion potential score
    sorted_df = df.sort_values(by=["efficiency", "promotion_potential_score"], ascending=False)

    selected: list[dict[str, Any]] = []
    total_spent = 0.0
    tier_spend: dict[str, float] = {}
    cumulative_costs: list[float] = []
    max_spend_per_tier = budget_usd * max_tier_share

    for _, row in sorted_df.iterrows():
        if max_creators is not None and len(selected) >= max_creators:
            break

        cost = float(row["est_cost"])
        tier = str(row.get("size_tier", "Micro")).capitalize()

        # Check total budget constraint
        if total_spent + cost > budget_usd:
            continue

        # Check tier diversification constraint
        current_tier_spend = tier_spend.get(tier, 0.0)
        if (budget_usd > 1500) and (current_tier_spend + cost > max_spend_per_tier):
            continue

        total_spent += cost
        tier_spend[tier] = current_tier_spend + cost
        cumulative_costs.append(round(total_spent, 2))

        selected.append({
            "channel_name": row.get("channel_name", row.get("channel_id", "")),
            "channel_id": row.get("channel_id", ""),
            "subscribers": int(row.get("subscribers", 0)) if pd.notnull(row.get("subscribers")) else 0,
            "size_tier": tier,
            "promotion_potential_score": round(float(row.get("promotion_potential_score", 50.0)), 1),
            "raw_score": round(float(row.get("raw_score", 50.0)), 1) if pd.notnull(row.get("raw_score")) else None,
            "partial_evidence": bool(row.get("partial_evidence", False)),
            "median_views": int(row.get("median_views", 0)),
            "est_cost_usd": round(cost, 2),
            "efficiency": round(float(row["efficiency"]), 4),
            "promo_lift": row.get("promo_lift_display", "N/A"),
        })

    total_typical_views = sum(c["median_views"] for c in selected)
    avg_score = round(sum(c["promotion_potential_score"] for c in selected) / len(selected), 1) if selected else 0.0

    return {
        "selected_creators": selected,
        "total_spent": round(total_spent, 2),
        "remaining_budget": round(budget_usd - total_spent, 2),
        "total_typical_views": total_typical_views,
        "avg_score": avg_score,
        "tier_breakdown": {t: round(s, 2) for t, s in tier_spend.items() if s > 0},
        "cumulative_costs": cumulative_costs,
    }
