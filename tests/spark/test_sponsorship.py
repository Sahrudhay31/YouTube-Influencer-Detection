"""
tests/spark/test_sponsorship.py
Phase 4 Sponsorship Detection and Promo Lift smoke tests:
- T-S1: Rules flag 10 handwritten positive and 10 negative fixture strings correctly.
- T-S2: Promo-lift is null (None) when channel has too few videos.
- T-S3: Promo-lift for a fixture channel equals the exact hand-computed value.
- T-S4: Promo-lift protects against zero-division (returns null if baseline is 0).
"""
from __future__ import annotations

import pytest
from pyspark.sql import functions as F
from src.common.spark_session import get_spark
from src.sponsorship.detector import detect_sponsorship_in_text, load_sponsorship_config, add_sponsorship_features
from src.sponsorship.promo_lift import compute_channel_promo_lift


@pytest.fixture(scope="module")
def spark():
    s = get_spark(app_name="bda-phase4-tests", local_mode=True)
    yield s


def test_ts1_handwritten_fixtures_classification():
    """T-S1: Rules flag 10 positive and 10 negative fixture strings correctly."""
    cfg = load_sponsorship_config()

    positives = [
        "Huge thanks to Sephora for sponsoring today's video! #ad",
        "This video is sponsored by Fenty Beauty. Check out the products below!",
        "Paid partnership with Glossier. Use code GLAM20 for 20% off your order.",
        "Loved receiving this pr package from Morphe! All items linked below.",
        "Shop my favorite outfit details here: https://liketk.it/3xyz",
        "Get 15% off using my discount code SARAH15 at checkout!",
        "Check out the summer sale via my affiliate link: https://amzn.to/3abc",
        "In partnership with Curology. Get your custom formula now!",
        "Visit https://mybrand.com/?utm_source=youtube&utm_campaign=summer_promo",
        "Special coupon code BEAUTY50 gives you free shipping on all orders.",
    ]

    negatives = [
        "My daily morning routine and getting ready for high school.",
        "Easy 10-minute natural makeup tutorial for beginners.",
        "What I eat in a day as a university student in London.",
        "Addressing the rumors and answering your assumptions about me.",
        "Q&A with my boyfriend: how we met and funny memories.",
        "Reacting to my old cringey makeup videos from 2014!",
        "Drugstore vs high-end foundation wear test on oily skin.",
        "Cleaning and decluttering my entire beauty room and vanity.",
        "Vlog: A rainy day in New York City with my sister.",
        "How to curl your hair with a flat iron step by step.",
    ]

    for p in positives:
        res = detect_sponsorship_in_text(p, cfg)
        assert res["is_sponsored"] is True, f"Failed to detect sponsorship in positive fixture: '{p}'"

    for n in negatives:
        res = detect_sponsorship_in_text(n, cfg)
        assert res["is_sponsored"] is False, f"False positive sponsorship detected in negative fixture: '{n}'"


def test_ts2_promo_lift_null_when_too_few_videos(spark):
    """T-S2: promo-lift returns null when a channel has fewer than minimum required videos."""
    # Channel has only 1 sponsored and 1 non-sponsored (threshold requires >= 3 each)
    df = spark.sql(
        "SELECT 'ch_sparse' AS channel_id, true AS is_sponsored, 5000.0 AS view_count "
        "UNION ALL SELECT 'ch_sparse', false, 4000.0"
    )
    lift_df = compute_channel_promo_lift(df, min_sponsored=3, min_nonsponsored=3)

    row = lift_df.filter(F.col("channel_id") == "ch_sparse").first()
    assert row["total_videos"] == 2
    assert row["sponsored_count"] == 1
    assert row["nonsponsored_count"] == 1
    # Must be strictly None (null), NEVER 0.0
    assert row["promo_lift"] is None, f"Expected None for insufficient evidence, got {row['promo_lift']}"


def test_ts3_promo_lift_matches_hand_computed_value(spark):
    """T-S3: promo-lift for a fixture channel equals exact hand-computed value."""
    # Channel with 3 sponsored videos: views [1000, 2000, 3000] -> median = 2000
    # and 3 non-sponsored videos: views [500, 1000, 1500] -> median = 1000
    # Expected promo_lift = 2000 / 1000 = 2.0
    df = spark.sql(
        "SELECT 'ch_ideal' AS channel_id, true AS is_sponsored, 1000.0 AS view_count "
        "UNION ALL SELECT 'ch_ideal', true, 2000.0 "
        "UNION ALL SELECT 'ch_ideal', true, 3000.0 "
        "UNION ALL SELECT 'ch_ideal', false, 500.0 "
        "UNION ALL SELECT 'ch_ideal', false, 1000.0 "
        "UNION ALL SELECT 'ch_ideal', false, 1500.0"
    )
    lift_df = compute_channel_promo_lift(df, min_sponsored=3, min_nonsponsored=3)

    row = lift_df.filter(F.col("channel_id") == "ch_ideal").first()
    assert row["sponsored_count"] == 3
    assert row["nonsponsored_count"] == 3
    assert row["promo_lift"] is not None
    assert abs(row["promo_lift"] - 2.0) < 1e-4, f"Expected 2.0, got {row['promo_lift']}"


def test_ts4_no_division_by_zero(spark):
    """T-S4: No division by zero: returns null if non-sponsored baseline median is 0."""
    df = spark.sql(
        "SELECT 'ch_zero_base' AS channel_id, true AS is_sponsored, 1000.0 AS view_count "
        "UNION ALL SELECT 'ch_zero_base', true, 2000.0 "
        "UNION ALL SELECT 'ch_zero_base', true, 3000.0 "
        "UNION ALL SELECT 'ch_zero_base', false, 0.0 "
        "UNION ALL SELECT 'ch_zero_base', false, 0.0 "
        "UNION ALL SELECT 'ch_zero_base', false, 0.0"
    )
    lift_df = compute_channel_promo_lift(df, min_sponsored=3, min_nonsponsored=3)

    row = lift_df.filter(F.col("channel_id") == "ch_zero_base").first()
    assert row["promo_lift"] is None, f"Expected None on zero baseline, got {row['promo_lift']}"
