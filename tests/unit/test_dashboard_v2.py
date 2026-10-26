"""
tests/unit/test_dashboard_v2.py
Unit tests for InfluencerAI Dashboard v2 pure logic modules:
1. Formatting helpers (subscribers K/M, views, percentages, promo lift) with edge cases.
2. Evidence level flags & dynamic weight renormalisation factor text builder.
3. Leaderboard pure filtering, deterministic tie-breaking, and pagination.
4. Live discovery API guard & confirmation safety checks.
5. Quota ledger Pacific-midnight rollover calculation with injected clock.
6. Portfolio budget allocator with CPM + fixed overhead and typical view projections.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
import pandas as pd
import pytest

from src.app.formatters import (
    format_subscribers,
    format_views,
    format_percentage,
    format_promo_lift,
    format_currency,
)
from src.app.evidence import (
    get_missing_components,
    compute_renormalisation,
    get_evidence_badge,
    COMPONENT_WEIGHTS,
)
from src.app.leaderboard_logic import (
    filter_and_rank_creators,
    paginate_dataframe,
    build_export_csv,
    DISCLAIMER_COMMENT,
)
from src.app.quota_service import (
    get_pacific_now,
    get_pacific_date_key,
    time_until_pacific_midnight,
    inspect_quota_status,
    validate_api_action,
    get_seven_day_quota_history,
)
from src.app.portfolio_optimizer import (
    optimize_portfolio,
    get_tier_rates,
)


# ── 1. Formatting Tests ───────────────────────────────────────────────────────

def test_format_subscribers_edge_cases():
    assert format_subscribers(None) == "n/a"
    assert format_subscribers(float("nan")) == "n/a"
    assert format_subscribers("not_a_number") == "n/a"
    assert format_subscribers(0) == "0"
    assert format_subscribers(-50) == "0"
    assert format_subscribers(500) == "500"
    assert format_subscribers(11400) == "11.4K"
    assert format_subscribers(914000) == "914K"
    assert format_subscribers(3020000) == "3.02M"
    assert format_subscribers(5000000) == "5M"


def test_format_views_edge_cases():
    assert format_views(None) == "n/a"
    assert format_views(float("nan")) == "n/a"
    assert format_views(0) == "0"
    assert format_views(12345) == "12,345"
    assert format_views(1234567.89) == "1,234,568"


def test_format_percentage_edge_cases():
    assert format_percentage(None) == "n/a"
    assert format_percentage(float("nan")) == "n/a"
    # Decimal fraction input
    assert format_percentage(0.1111) == "11.11%"
    assert format_percentage(0.0) == "0.00%"
    assert format_percentage(0.052) == "5.20%"
    # Whole percentage input (> 1.0)
    assert format_percentage(11.11) == "11.11%"


def test_format_promo_lift_edge_cases():
    assert format_promo_lift(None) == "N/A"
    assert format_promo_lift(float("nan")) == "N/A"
    assert format_promo_lift(0.0) == "N/A"
    assert format_promo_lift(-1.5) == "N/A"
    assert format_promo_lift(1.412) == "1.41x"
    assert format_promo_lift(2.9) == "2.90x"


# ── 2. Evidence & Renormalisation Tests ───────────────────────────────────────

def test_evidence_flags_and_renormalisation():
    # Case A: Full evidence (all 6 components present)
    full_row = {
        "comp_fit": 0.8,
        "comp_conversion_evidence": 0.6,
        "comp_real_reach": 0.7,
        "comp_engagement_quality": 0.5,
        "comp_momentum": 0.9,
        "comp_consistency": 0.85,
    }
    missing = get_missing_components(full_row)
    assert missing == []
    act_weight, factor, msg = compute_renormalisation(missing)
    assert act_weight == 100.0
    assert factor == 1.0
    assert "Full evidence" in msg

    badge_full = get_evidence_badge(partial_evidence=False)
    assert badge_full["tier"] == "High"
    assert badge_full["label"] == "Full Evidence"

    # Case B: Missing conversion evidence (25% weight)
    partial_row = {
        "comp_fit": 0.8,
        "comp_conversion_evidence": None,
        "comp_real_reach": 0.7,
        "comp_engagement_quality": 0.5,
        "comp_momentum": 0.9,
        "comp_consistency": 0.85,
    }
    missing_p = get_missing_components(partial_row)
    assert missing_p == ["comp_conversion_evidence"]
    act_weight_p, factor_p, msg_p = compute_renormalisation(missing_p)
    assert act_weight_p == 75.0
    assert round(factor_p, 2) == 1.33
    assert "Conversion Evidence (25% weight) missing" in msg_p
    assert "rescaled x1.33" in msg_p

    badge_part = get_evidence_badge(partial_evidence=True)
    assert badge_part["tier"] == "Partial"
    assert badge_part["label"] == "Partial Evidence"


# ── 3. Leaderboard Filtering, Tie-breaking & Pagination ────────────────────────

@pytest.fixture
def sample_creators_df() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "channel_id": "UC_A",
            "channel_name": "Kylie Cosmetics",
            "size_tier": "Macro",
            "promotion_potential_score": 100.0,
            "raw_score": 68.5,
            "partial_evidence": True,
            "subscribers": 950000,
            "median_views": 85000,
            "engagement_rate": 0.045,
            "sponsored_count": 0,
        },
        {
            "channel_id": "UC_B",
            "channel_name": "Andrea Russett",
            "size_tier": "Mega",
            "promotion_potential_score": 100.0,
            "raw_score": 88.2,
            "partial_evidence": False,
            "subscribers": 2800000,
            "median_views": 150000,
            "engagement_rate": 0.082,
            "sponsored_count": 8,
        },
        {
            "channel_id": "UC_C",
            "channel_name": "Hardwear Beauty",
            "size_tier": "Nano",
            "promotion_potential_score": 100.0,
            "raw_score": 55.0,
            "partial_evidence": True,
            "subscribers": 5400,
            "median_views": 1200,
            "engagement_rate": 0.120,
            "sponsored_count": 0,
        },
        {
            "channel_id": "UC_D",
            "channel_name": "Glow Recipe Fan",
            "size_tier": "Micro",
            "promotion_potential_score": 85.0,
            "raw_score": 75.0,
            "partial_evidence": False,
            "subscribers": 45000,
            "median_views": 12000,
            "engagement_rate": 0.065,
            "sponsored_count": 3,
        },
    ])


def test_leaderboard_tie_breaking_full_evidence_first(sample_creators_df):
    """
    Test deterministic tie-breaking:
    1. Full evidence first (partial_evidence=False before True).
    2. Ties on score broken by raw_score descending.
    """
    ranked = filter_and_rank_creators(
        sample_creators_df,
        rank_full_evidence_first=True,
    )
    # Among the three creators tied with promotion_potential_score=100.0,
    # UC_B (Andrea Russett) has partial_evidence=False, so she must be #1.
    assert ranked.iloc[0]["channel_id"] == "UC_B"
    # UC_D has score 85.0 but partial_evidence=False, so depending on rank_full_evidence_first,
    # all False partial_evidence creators come first!
    assert ranked.iloc[1]["channel_id"] == "UC_D"
    # Between UC_A (raw 68.5) and UC_C (raw 55.0), UC_A must come before UC_C
    assert ranked.iloc[2]["channel_id"] == "UC_A"
    assert ranked.iloc[3]["channel_id"] == "UC_C"


def test_leaderboard_tie_breaking_without_evidence_grouping(sample_creators_df):
    """
    When rank_full_evidence_first is OFF:
    Primary sort is promotion_potential_score (100 vs 85).
    Ties at 100 broken by raw_score: UC_B (88.2) > UC_A (68.5) > UC_C (55.0).
    """
    ranked = filter_and_rank_creators(
        sample_creators_df,
        rank_full_evidence_first=False,
    )
    assert ranked.iloc[0]["channel_id"] == "UC_B"
    assert ranked.iloc[1]["channel_id"] == "UC_A"
    assert ranked.iloc[2]["channel_id"] == "UC_C"
    assert ranked.iloc[3]["channel_id"] == "UC_D"


def test_leaderboard_filtering(sample_creators_df):
    # Tier filter
    macro_only = filter_and_rank_creators(sample_creators_df, selected_tiers=["Macro"])
    assert len(macro_only) == 1
    assert macro_only.iloc[0]["channel_name"] == "Kylie Cosmetics"

    # Full evidence only
    full_only = filter_and_rank_creators(sample_creators_df, full_evidence_only=True)
    assert len(full_only) == 2
    assert set(full_only["channel_id"]) == {"UC_B", "UC_D"}

    # Only sponsored
    sponsored_only = filter_and_rank_creators(sample_creators_df, only_sponsored=True)
    assert len(sponsored_only) == 2
    assert set(sponsored_only["channel_id"]) == {"UC_B", "UC_D"}


def test_pagination():
    df = pd.DataFrame({"id": range(100)})
    page_1, total, pages = paginate_dataframe(df, page_number=1, page_size=25)
    assert len(page_1) == 25
    assert total == 100
    assert pages == 4
    assert page_1.iloc[0]["id"] == 0
    assert page_1.iloc[-1]["id"] == 24

    page_4, _, _ = paginate_dataframe(df, page_number=4, page_size=25)
    assert len(page_4) == 25
    assert page_4.iloc[0]["id"] == 75
    assert page_4.iloc[-1]["id"] == 99


def test_export_csv_has_disclaimer():
    df = pd.DataFrame([{"channel": "TestChannel", "score": 90.0}])
    csv_str = build_export_csv(df)
    assert csv_str.startswith("# Research & Governance Disclaimer")
    assert "channel,score" in csv_str


# ── 4. Live Discovery Safety Guards ──────────────────────────────────────────

def test_live_tab_guard_logic():
    # Scenario 1: Dry run mode is always allowed without confirmation
    quota_status = {
        "units_used": 100,
        "remaining_units": 7900,
        "remaining_searches": 19,
        "per_run_cap": 1500,
        "is_exhausted": False,
    }
    ok_dry, msg_dry = validate_api_action("Dry Run (0 units)", estimated_units=101, confirmed_live=False, quota_status=quota_status)
    assert ok_dry is True
    assert "Dry Run" in msg_dry

    # Scenario 2: Live mode without confirmation -> BLOCKED
    ok_live_no_conf, msg_live_no_conf = validate_api_action("Live Mode (YouTube API)", estimated_units=101, confirmed_live=False, quota_status=quota_status)
    assert ok_live_no_conf is False
    assert "requires explicit user confirmation" in msg_live_no_conf

    # Scenario 3: Live mode confirmed within budget -> ALLOWED
    ok_live_ok, msg_live_ok = validate_api_action("Live Mode (YouTube API)", estimated_units=101, confirmed_live=True, quota_status=quota_status)
    assert ok_live_ok is True

    # Scenario 4: Live mode exceeding per-run cap (1,500) -> BLOCKED
    ok_run_cap, msg_run_cap = validate_api_action("Live Mode (YouTube API)", estimated_units=1600, confirmed_live=True, quota_status=quota_status)
    assert ok_run_cap is False
    assert "exceeds per-run safety limit" in msg_run_cap

    # Scenario 5: Live mode exceeding remaining daily units -> BLOCKED
    tight_status = {
        "units_used": 7950,
        "remaining_units": 50,
        "remaining_searches": 5,
        "per_run_cap": 1500,
        "is_exhausted": False,
    }
    ok_daily, msg_daily = validate_api_action("Live Mode (YouTube API)", estimated_units=101, confirmed_live=True, quota_status=tight_status)
    assert ok_daily is False
    assert "exceeds remaining daily budget" in msg_daily

    # Scenario 6: Server exhausted -> BLOCKED
    exhausted_status = {
        "units_used": 500,
        "remaining_units": 7500,
        "remaining_searches": 15,
        "per_run_cap": 1500,
        "is_exhausted": True,
    }
    ok_exh, msg_exh = validate_api_action("Live Mode (YouTube API)", estimated_units=101, confirmed_live=True, quota_status=exhausted_status)
    assert ok_exh is False
    assert "exhausted by Google API servers" in msg_exh


# ── 5. Quota Ledger & Pacific Midnight Rollover Clock Tests ──────────────────

def test_quota_ledger_pacific_midnight_rollover():
    # Mock ledger with data for 2026-10-24 and 2026-10-25
    mock_ledger = {
        "2026-10-24": {"units_used": 3400, "search_calls": 8, "exhausted": False},
        "2026-10-25": {"units_used": 150, "search_calls": 1, "exhausted": False},
    }

    # Inject clock: 2026-10-25 23:59:00 UTC = 2026-10-25 16:59:00 PDT
    clock_pdt_day = datetime(2026, 10, 25, 23, 59, 0, tzinfo=timezone.utc)
    status_day = inspect_quota_status(mock_ledger, now_dt=clock_pdt_day)
    assert status_day["today_key"] == "2026-10-25"
    assert status_day["units_used"] == 150
    assert status_day["remaining_units"] == 7850

    # Inject clock: 2026-10-26 07:01:00 UTC = 2026-10-26 00:01:00 PDT (Rollover to 2026-10-26!)
    clock_next_day = datetime(2026, 10, 26, 7, 1, 0, tzinfo=timezone.utc)
    status_next = inspect_quota_status(mock_ledger, now_dt=clock_next_day)
    assert status_next["today_key"] == "2026-10-26"
    # Unseen date resets units_used to 0
    assert status_next["units_used"] == 0
    assert status_next["remaining_units"] == 8000
    assert status_next["remaining_searches"] == 20


# ── 6. Portfolio Optimizer Tests ──────────────────────────────────────────────

def test_portfolio_optimizer_with_overheads(sample_creators_df):
    rate_card = {
        "Nano": {"cpm": 15.0, "overhead": 50.0},
        "Micro": {"cpm": 20.0, "overhead": 100.0},
        "Macro": {"cpm": 25.0, "overhead": 250.0},
        "Mega": {"cpm": 35.0, "overhead": 500.0},
    }
    # Budget $5,000
    res = optimize_portfolio(sample_creators_df, budget_usd=5000.0, rate_card=rate_card)
    assert res["total_spent"] <= 5000.0
    assert res["remaining_budget"] >= 0.0
    assert len(res["selected_creators"]) > 0
    assert res["total_typical_views"] > 0
    # Confirm each selected creator's est_cost_usd reflects (views/1000)*cpm + overhead
    for c in res["selected_creators"]:
        tier = c["size_tier"]
        overhead = rate_card[tier]["overhead"]
        cpm = rate_card[tier]["cpm"]
        expected_cost = round((c["median_views"] / 1000.0) * cpm + overhead, 2)
        assert c["est_cost_usd"] == expected_cost
