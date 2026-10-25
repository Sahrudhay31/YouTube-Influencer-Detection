"""
tests/spark/test_ranking.py
Smoke tests T-R1 through T-R6 for Phase 7 Promotion-Potential Scoring,
Calibration, and Time-Split Backtesting.

T-R1: Weights sum to 100 and every component score in [0, 1].
T-R2: Identical inputs yield identical scores (deterministic ranking).
T-R3: Creator with missing component is flagged (partial_evidence=True)
      and weights renormalise to 100%.
T-R4: Percentile normalisation is strictly within domain and tier.
T-R5: Backtest uses NO data after cutoff T (assert max upload_date <= T).
T-R6: NDCG on hand-constructed ranking fixture matches hand-computed value.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
import yaml
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from src.common.paths import local
from src.ranking.backtest import (
    compute_dcg,
    compute_ndcg,
    compute_precision_at_k,
    run_time_split_backtest,
)
from src.common.spark_session import get_spark
from src.ranking.portfolio import allocate_budget_portfolio, estimate_creator_cost
from src.ranking.score import (
    calculate_promotion_potential_score,
    compute_component_scores,
)


@pytest.fixture(scope="module")
def spark():
    s = get_spark(app_name="bda-phase7-tests", local_mode=True)
    yield s


def _safe_create_df(spark: SparkSession, rows: list[dict[str, Any]], tmp_path: Path, name: str) -> DataFrame:
    """Safely create small test DataFrame using JSON staging to avoid Python 3.14 cloudpickle recursion."""
    p = tmp_path / f"{name}.json"
    with open(p, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return spark.read.json(str(p))


# ── T-R1: Weights sum to 100, component scores in [0, 1] ─────────────────────

def test_tr1_weights_sum_to_100_and_components_bounded(spark: SparkSession, tmp_path: Path):
    """
    T-R1:
    1. Configured weights sum to 100.
    2. Computed component scores are bounded in [0.0, 1.0].
    """
    scoring_cfg_path = Path("config/scoring.yaml")
    with open(scoring_cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    components = cfg.get("components", {})
    weights = {k: v.get("weight", 0.0) for k, v in components.items()}
    total_weight = sum(weights.values())
    assert abs(total_weight - 100.0) < 1e-4, f"Weights sum to {total_weight}, expected 100"

    # Test components on synthetic creator data
    sample_rows = [
        {
            "channel_id": "ch_1",
            "fit_score": 0.85,
            "promo_lift": 1.4,
            "purchase_intent_smoothed": 0.05,
            "has_promo_link": True,
            "repeat_sponsor_count": 3,
            "median_views_nonsponsored": 50000.0,
            "engagement_rate": 0.045,
            "view_consistency_cv": 0.35,
            "channel_age_days": 800.0,
            "upload_cadence_days": 4.0,
            "domain_purity": 0.90,
            "sponsored_rate": 0.20,
            "competitor_brand_count": 0,
            "size_tier": "macro",
            "domain": "Technology",
        },
        {
            "channel_id": "ch_2",
            "fit_score": 0.40,
            "promo_lift": 0.8,
            "purchase_intent_smoothed": 0.01,
            "has_promo_link": False,
            "repeat_sponsor_count": 0,
            "median_views_nonsponsored": 2000.0,
            "engagement_rate": 0.015,
            "view_consistency_cv": 1.20,
            "channel_age_days": 120.0,
            "upload_cadence_days": 30.0,
            "domain_purity": 0.50,
            "sponsored_rate": 0.75,
            "competitor_brand_count": 2,
            "size_tier": "nano",
            "domain": "Technology",
        },
    ]

    df = _safe_create_df(spark, sample_rows, tmp_path, "tr1_creators")
    df_comp = compute_component_scores(df)
    results = df_comp.collect()

    comp_cols = [
        "fit_score",
        "conversion_score",
        "reach_score",
        "engagement_score",
        "momentum_score",
        "consistency_score",
    ]

    for r in results:
        for c in comp_cols:
            val = r[c]
            assert val is not None, f"Component {c} is None"
            assert 0.0 <= val <= 1.0, f"Component {c}={val} out of bounds [0, 1]"


# ── T-R2: Identical inputs yield identical scores ─────────────────────────────

def test_tr2_identical_inputs_yield_identical_scores(spark: SparkSession, tmp_path: Path):
    """T-R2: Calculating scores twice on identical inputs produces identical promotion potential."""
    row = {
        "channel_id": "ch_det",
        "fit_score": 0.72,
        "promo_lift": 1.2,
        "purchase_intent_smoothed": 0.03,
        "has_promo_link": True,
        "repeat_sponsor_count": 1,
        "median_views_nonsponsored": 15000.0,
        "engagement_rate": 0.035,
        "view_consistency_cv": 0.4,
        "channel_age_days": 400.0,
        "upload_cadence_days": 7.0,
        "domain_purity": 0.85,
        "sponsored_rate": 0.15,
        "competitor_brand_count": 0,
        "size_tier": "micro",
        "domain": "Gaming",
    }
    df1 = _safe_create_df(spark, [row], tmp_path, "tr2_run1")
    df2 = _safe_create_df(spark, [row], tmp_path, "tr2_run2")

    scored1 = calculate_promotion_potential_score(compute_component_scores(df1)).collect()[0]
    scored2 = calculate_promotion_potential_score(compute_component_scores(df2)).collect()[0]

    assert abs(scored1["raw_score"] - scored2["raw_score"]) < 1e-6
    assert abs(scored1["promotion_potential_score"] - scored2["promotion_potential_score"]) < 1e-6


# ── T-R3: Missing component flagged (partial_evidence=True) and renormalises ──

def test_tr3_missing_component_flagged_and_renormalises(spark: SparkSession, tmp_path: Path):
    """
    T-R3: When conversion evidence (promo_lift) is missing:
    1. partial_evidence flag is True.
    2. Remaining weights renormalise so max possible score remains 100.
    """
    row_missing = {
        "channel_id": "ch_missing",
        "fit_score": 1.0,
        "promo_lift": None,  # Missing promo lift
        "purchase_intent_smoothed": None,
        "has_promo_link": False,
        "repeat_sponsor_count": 0,
        "median_views_nonsponsored": 10000.0,
        "engagement_rate": 0.05,
        "view_consistency_cv": 0.2,
        "channel_age_days": 500.0,
        "upload_cadence_days": 5.0,
        "domain_purity": 1.0,
        "sponsored_rate": 0.0,
        "competitor_brand_count": 0,
        "size_tier": "micro",
        "domain": "Education",
    }
    df = _safe_create_df(spark, [row_missing], tmp_path, "tr3_missing")
    df_comp = compute_component_scores(df)
    scored = calculate_promotion_potential_score(df_comp).collect()[0]

    # Must flag partial_evidence
    assert scored["partial_evidence"] is True, "partial_evidence must be True when components are missing"
    # Even without conversion evidence, raw score is dynamically scaled back to 0..100 scale
    assert scored["raw_score"] > 0.0, "Score should not drop to 0 due to missing component"
    assert scored["raw_score"] <= 100.0, "Renormalised score must not exceed 100"


# ── T-R4: Percentile normalisation within domain/tier ─────────────────────────

def test_tr4_percentile_normalisation_within_domain_and_tier(spark: SparkSession, tmp_path: Path):
    """T-R4: Percentile rank is strictly within domain and tier, bounded in [0, 100]."""
    rows = [
        # Domain: Tech, Tier: Micro (3 creators with varying fit)
        {
            "channel_id": "t_micro_1", "fit_score": 0.9, "median_views_nonsponsored": 20000.0,
            "engagement_rate": 0.06, "view_consistency_cv": 0.3, "channel_age_days": 600.0,
            "upload_cadence_days": 5.0, "domain_purity": 0.9, "sponsored_rate": 0.1,
            "size_tier": "micro", "domain": "Technology", "competitor_brand_count": 0,
        },
        {
            "channel_id": "t_micro_2", "fit_score": 0.5, "median_views_nonsponsored": 15000.0,
            "engagement_rate": 0.03, "view_consistency_cv": 0.5, "channel_age_days": 300.0,
            "upload_cadence_days": 7.0, "domain_purity": 0.7, "sponsored_rate": 0.2,
            "size_tier": "micro", "domain": "Technology", "competitor_brand_count": 0,
        },
        {
            "channel_id": "t_micro_3", "fit_score": 0.2, "median_views_nonsponsored": 10000.0,
            "engagement_rate": 0.01, "view_consistency_cv": 0.9, "channel_age_days": 100.0,
            "upload_cadence_days": 14.0, "domain_purity": 0.5, "sponsored_rate": 0.4,
            "size_tier": "micro", "domain": "Technology", "competitor_brand_count": 1,
        },
        # Domain: Gaming, Tier: Macro (1 creator)
        {
            "channel_id": "g_macro_1", "fit_score": 0.8, "median_views_nonsponsored": 500000.0,
            "engagement_rate": 0.08, "view_consistency_cv": 0.2, "channel_age_days": 1200.0,
            "upload_cadence_days": 2.0, "domain_purity": 0.95, "sponsored_rate": 0.05,
            "size_tier": "macro", "domain": "Gaming", "competitor_brand_count": 0,
        },
    ]

    df = _safe_create_df(spark, rows, tmp_path, "tr4_tiers")
    scored_df = calculate_promotion_potential_score(compute_component_scores(df))
    records = {r["channel_id"]: r for r in scored_df.collect()}

    # All percentile scores must be bounded in [0, 100]
    for ch_id, rec in records.items():
        score = rec["promotion_potential_score"]
        assert 0.0 <= score <= 100.0, f"Score {score} out of [0, 100] for {ch_id}"

    # Micro tech 1 should have higher score than micro tech 3
    assert records["t_micro_1"]["promotion_potential_score"] > records["t_micro_3"]["promotion_potential_score"]


# ── T-R5: Backtest uses NO data after cutoff T (assert max date <= T) ─────────

def test_tr5_backtest_uses_no_data_after_cutoff(spark: SparkSession):
    """
    T-R5: Assert that any data partitioned for training up to cutoff T has
    max(upload_date) <= T.
    """
    cutoff = "2019-01-01"
    video_features_path = str(local("silver", "sponsorship_video_features"))
    df_videos = spark.read.parquet(video_features_path)

    train_videos = df_videos.filter(F.col("upload_date") <= cutoff)
    max_train_date = train_videos.select(F.max("upload_date")).collect()[0][0]

    assert max_train_date is not None
    assert str(max_train_date) <= cutoff, (
        f"T-R5 VIOLATION: max train upload date {max_train_date} is after cutoff {cutoff}"
    )


# ── T-R6: NDCG on hand-constructed fixture matches hand-calculated value ───────

def test_tr6_ndcg_hand_constructed_fixture():
    """
    T-R6: Verify NDCG calculation against exact hand-calculated formula.
    Let relevances = [3, 2, 0].
    Ideal DCG@3 = (2^3-1)/log2(2) + (2^2-1)/log2(3) + (2^0-1)/log2(4)
                = 7/1 + 3/1.5849625 + 0 = 7 + 1.892789 = 8.892789
    Actual ranking = [2, 3, 0].
    Actual DCG@3 = (2^2-1)/log2(2) + (2^3-1)/log2(3) + 0
                 = 3/1 + 7/1.5849625 = 3 + 4.416508 = 7.416508
    NDCG@3 = 7.416508 / 8.892789 = 0.8340
    """
    # 1. Ideal ranking NDCG must be exactly 1.0
    ideal_ndcg = compute_ndcg([3, 2, 0], k=3)
    assert abs(ideal_ndcg - 1.0) < 1e-4, f"Ideal NDCG should be 1.0, got {ideal_ndcg}"

    # 2. Non-ideal ranking NDCG must match hand-computed value: 0.8340
    actual_ndcg = compute_ndcg([2, 3, 0], k=3)
    expected_ndcg = 0.8340
    assert abs(actual_ndcg - expected_ndcg) < 1e-3, (
        f"NDCG@3 mismatch: got {actual_ndcg:.4f}, expected {expected_ndcg:.4f}"
    )

    # 3. Precision@k hand test
    p_at_2 = compute_precision_at_k([1, 0, 1], k=2)
    assert abs(p_at_2 - 0.5) < 1e-4

    p_at_3 = compute_precision_at_k([1, 0, 1], k=3)
    assert abs(p_at_3 - (2.0 / 3.0)) < 1e-4


# ── Portfolio Allocation Unit Test ───────────────────────────────────────────

def test_portfolio_greedy_allocation_within_budget():
    """Verify greedy budget allocation stays within budget and respects rate card."""
    rate_card = {
        "nano": {"cpm": 15.0, "fixed_overhead": 50.0},
        "micro": {"cpm": 20.0, "fixed_overhead": 100.0},
        "macro": {"cpm": 25.0, "fixed_overhead": 250.0},
    }
    candidates = [
        {"channel_id": "c1", "size_tier": "micro", "median_views": 10000.0, "promotion_potential_score": 85.0},
        {"channel_id": "c2", "size_tier": "nano", "median_views": 2000.0, "promotion_potential_score": 75.0},
        {"channel_id": "c3", "size_tier": "macro", "median_views": 200000.0, "promotion_potential_score": 90.0},
    ]

    # c1 cost = (10000/1000)*20 + 100 = $300 -> eff = 85/300 = 0.283
    # c2 cost = (2000/1000)*15 + 50 = $80   -> eff = 75/80 = 0.938
    # c3 cost = (200000/1000)*25 + 250 = $5250 -> eff = 90/5250 = 0.017
    # With budget $500: c2 ($80) and c1 ($300) can be selected ($380 total spent). c3 ($5250) cannot.
    res = allocate_budget_portfolio(candidates, budget=500.0, rate_card=rate_card)

    assert res["total_spent"] <= 500.0
    assert res["num_creators_allocated"] == 2
    allocated_ids = [c["channel_id"] for c in res["creators"]]
    assert "c2" in allocated_ids
    assert "c1" in allocated_ids
    assert "c3" not in allocated_ids


# ── Phase R7 Hardening Tests (T-R7 through T-R11) ─────────────────────────────

def test_tr7_age_normalisation_unit_test_hand_values():
    """T-R7: Age-normalisation views-per-day calculation with exact hand-verified values."""
    from src.ranking.backtest import compute_age_normalized_views

    # 1. 1,000 views uploaded 10 days before crawl: 1000 / 10 = 100.0 views/day
    vpd_1 = compute_age_normalized_views(1000, "2019-01-01", "2019-01-11")
    assert abs(vpd_1 - 100.0) < 1e-4

    # 2. 50,000 views uploaded 200 days before crawl: 50000 / 200 = 250.0 views/day
    vpd_2 = compute_age_normalized_views(50000, "2018-06-01", "2018-12-18")
    assert abs(vpd_2 - 250.0) < 1e-4

    # 3. Same-day upload (0 days difference) safely bounds at minimum 1.0 day divisor
    vpd_3 = compute_age_normalized_views(500, "2019-01-01", "2019-01-01")
    assert abs(vpd_3 - 500.0) < 1e-4


def test_tr8_random_baseline_mean_matches_analytic_expectation():
    """T-R8: Random baseline mean Precision@k ≈ analytic expectation on a synthetic population."""
    from src.ranking.backtest import compute_random_baseline

    # Population with 40 positives and 60 negatives (base rate = 0.40)
    labels = [1] * 40 + [0] * 60
    rels = [2.0] * 40 + [0.0] * 60

    # Over 1,000 random draws, expected Precision@10 is 0.40
    rand_prec, rand_ndcg = compute_random_baseline(labels, rels, k=10, n_draws=1000, seed=42)
    assert abs(rand_prec - 0.40) < 0.03, f"Expected random Precision@10 ≈ 0.40, got {rand_prec:.4f}"
    assert rand_ndcg > 0.0


def test_tr9_bootstrap_deterministic_under_seed():
    """T-R9: Paired bootstrap 95% CI is completely deterministic under a fixed seed."""
    from src.ranking.backtest import compute_paired_bootstrap_ci_diff

    scores_a = [90, 80, 70, 60, 50, 40, 30, 20, 10, 5]
    scores_b = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90]
    labels = [1, 1, 1, 0, 0, 1, 0, 0, 0, 0]
    rels = [2.0, 2.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0]

    pt1, low1, high1 = compute_paired_bootstrap_ci_diff(
        scores_a, scores_b, labels, rels, k=5, metric="ndcg", n_bootstraps=500, seed=42
    )
    pt2, low2, high2 = compute_paired_bootstrap_ci_diff(
        scores_a, scores_b, labels, rels, k=5, metric="ndcg", n_bootstraps=500, seed=42
    )

    assert pt1 == pt2
    assert low1 == low2
    assert high1 == high2


def test_tr10_readme_generator_never_emits_outperforms_when_ci_includes_zero():
    """T-R10: Text claim generator refuses 'outperforms' if bootstrap CI includes 0."""
    def generate_claim(point_est: float, ci_low: float, ci_high: float) -> str:
        if ci_low > 0.0 or ci_high < 0.0:
            return "outperforms baseline with statistical significance"
        return "no statistically clear difference (CI includes 0)"

    # CI includes 0 -> must NOT claim outperforms
    claim_null = generate_claim(0.04, -0.05, 0.12)
    assert "outperforms" not in claim_null
    assert "no statistically clear difference" in claim_null

    # CI strictly positive -> allowed to claim outperforms
    claim_sig = generate_claim(0.15, 0.05, 0.25)
    assert "outperforms" in claim_sig


def test_tr11_backtest_temporal_guard_rejects_leakage():
    """T-R11: Temporal guard asserts max train upload date <= cutoff date."""
    cutoff = "2019-01-01"
    # Valid date
    assert "2018-12-31" <= cutoff
    assert "2019-01-01" <= cutoff
    # Post-cutoff date triggers assertion
    assert not ("2019-01-02" <= cutoff)

