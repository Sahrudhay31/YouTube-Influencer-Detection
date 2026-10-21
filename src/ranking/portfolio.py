"""
src/ranking/portfolio.py
Phase 7 — Budget Portfolio Allocation.

Given a budget and a rate card (CPM + fixed overhead by size tier),
allocates sponsorships across creators to maximize expected promotional impact
per currency unit using a documented greedy selection strategy with tier diversification.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml
from pyspark.sql import DataFrame, SparkSession

from src.common.config import get_settings
from src.common.logging_setup import setup_logging
from src.common.paths import local

logger = setup_logging(__name__)


def load_rate_card(rate_card_path: str | Path | None = None) -> dict[str, dict[str, float]]:
    """
    Load CPM and overhead rate card from YAML file.
    Default rate card from config/rate_card.yaml.
    """
    if rate_card_path is None:
        rate_card_path = local("config", "rate_card.yaml")

    p = Path(rate_card_path)
    if not p.exists():
        logger.warning("Rate card %s not found. Using default benchmark rates.", p)
        return {
            "nano": {"cpm": 15.0, "fixed_overhead": 50.0},
            "micro": {"cpm": 20.0, "fixed_overhead": 100.0},
            "macro": {"cpm": 25.0, "fixed_overhead": 250.0},
            "mega": {"cpm": 35.0, "fixed_overhead": 500.0},
        }

    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    tiers_data = data.get("tiers", {})
    rate_card: dict[str, dict[str, float]] = {}
    for tier, info in tiers_data.items():
        rate_card[tier.lower()] = {
            "cpm": float(info.get("cpm", 20.0)),
            "fixed_overhead": float(info.get("fixed_overhead", 100.0)),
        }
    return rate_card


def estimate_creator_cost(
    median_views: float,
    size_tier: str,
    rate_card: dict[str, dict[str, float]],
) -> float:
    """
    Estimate sponsorship cost based on tier CPM and fixed overhead.
    Cost = (median_views / 1,000) * CPM + fixed_overhead
    """
    tier_info = rate_card.get(size_tier.lower(), {"cpm": 20.0, "fixed_overhead": 100.0})
    views = max(float(median_views), 100.0)
    cpm = tier_info.get("cpm", 20.0)
    overhead = tier_info.get("fixed_overhead", 100.0)
    cost = (views / 1000.0) * cpm + overhead
    return round(cost, 2)


def allocate_budget_portfolio(
    candidates: list[dict[str, Any]],
    budget: float,
    rate_card: dict[str, dict[str, float]] | None = None,
    max_creators_per_tier: int | None = None,
    min_score: float = 0.0,
) -> dict[str, Any]:
    """
    Documented Greedy Budget Allocation Algorithm:
    1. Filter candidates having promotion_potential_score >= min_score.
    2. Compute estimated cost for each creator from rate card.
    3. Compute efficiency ratio = promotion_potential_score / estimated_cost.
    4. Sort candidates descending by efficiency.
    5. Iteratively select creators that fit within remaining budget,
       optionally constraining tier concentration (max_creators_per_tier).
    6. Return selected creator list and summary statistics.
    """
    if rate_card is None:
        rate_card = load_rate_card()

    # Step 1 & 2: Score candidates and compute costs
    annotated: list[dict[str, Any]] = []
    for c in candidates:
        score = float(c.get("promotion_potential_score", 0.0))
        if score < min_score:
            continue

        views = float(c.get("median_views", 1000.0))
        tier = str(c.get("size_tier", "micro")).lower()
        cost = estimate_creator_cost(views, tier, rate_card)

        if cost <= 0:
            continue

        # Efficiency: points of promotion potential per currency unit spent
        efficiency = score / cost

        item = dict(c)
        item["estimated_cost"] = cost
        item["efficiency"] = efficiency
        annotated.append(item)

    # Step 4: Sort descending by efficiency
    annotated.sort(key=lambda x: x["efficiency"], reverse=True)

    # Step 5: Greedy allocation
    allocated: list[dict[str, Any]] = []
    tier_counts: dict[str, int] = {}
    remaining_budget = float(budget)

    for item in annotated:
        cost = item["estimated_cost"]
        tier = str(item.get("size_tier", "micro")).lower()

        # Check budget availability
        if cost > remaining_budget:
            continue

        # Check tier concentration constraint
        current_tier_count = tier_counts.get(tier, 0)
        if max_creators_per_tier is not None and current_tier_count >= max_creators_per_tier:
            continue

        # Select creator
        allocated.append(item)
        remaining_budget -= cost
        tier_counts[tier] = current_tier_count + 1

    total_spent = budget - remaining_budget
    total_views = sum(float(c.get("median_views", 0.0)) for c in allocated)
    avg_score = (
        sum(float(c.get("promotion_potential_score", 0.0)) for c in allocated) / len(allocated)
        if allocated
        else 0.0
    )

    return {
        "budget": round(budget, 2),
        "total_spent": round(total_spent, 2),
        "remaining_budget": round(remaining_budget, 2),
        "num_creators_allocated": len(allocated),
        "tier_distribution": tier_counts,
        "total_expected_views": int(total_views),
        "average_promotion_potential_score": round(avg_score, 2),
        "creators": allocated,
    }
