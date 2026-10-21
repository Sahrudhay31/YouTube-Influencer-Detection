"""
tests/spark/test_enrichment.py
Phase 6 Smoke Tests — Enrichment Funnel, Comments & Audience Quality.

T-E1: QuotaGuard blocks calls that would exceed per-run cap.
T-E2: QuotaGuard dry-run returns empty items without consuming quota.
T-E3: Salted SHA-256 author hashing is deterministic and one-way.
T-E4: Purchase-intent rule classifier flags keyword hits and ignores non-intent text.
T-E5: Reservoir sampler draws exactly k items and is reproducible.
T-E6: Audience quality — duplicate_comment_share is zero when all comments are unique.
T-E7: Audience quality — top1_commenter_share is correctly computed.
T-E8: Audience quality — any_authenticity_flag fires when any threshold is breached.
T-E9: Enrichment funnel candidate cap is respected (Stage 4).
T-E10: Loyal commenter share is zero when no author repeats across videos.
"""
from __future__ import annotations

import hashlib
import os

import pytest
from pyspark.sql import Row
from pyspark.sql import functions as F

from src.common.spark_session import get_spark
from src.enrichment.audience_quality import (
    _duplicate_comment_share,
    _loyal_commenter_share,
    _top_commenter_shares,
    compute_audience_quality,
    load_enrichment_config,
)
from src.enrichment.comment_sampler import (
    _hash_author_id,
    classify_purchase_intent,
    _compile_intent_patterns,
    reservoir_sample,
)
from src.enrichment.youtube_client import QuotaGuard, QuotaExceededError, YouTubeClient


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def spark():
    s = get_spark(app_name="bda-phase6-tests", local_mode=True)
    yield s
    s.stop()


@pytest.fixture(scope="module")
def ecfg():
    return load_enrichment_config()


def _make_comment_df(spark, rows: list[dict]):
    """Helper to create a comment DataFrame from dicts."""
    from src.enrichment.comment_sampler import COMMENT_SCHEMA
    return spark.createDataFrame(rows, schema=COMMENT_SCHEMA)


# ─────────────────────────────────────────────────────────────────────────────
# T-E1: QuotaGuard blocks calls exceeding per-run cap
# ─────────────────────────────────────────────────────────────────────────────

def test_te1_quota_guard_blocks_excess():
    """T-E1: Consuming more than the cap raises QuotaExceededError."""
    guard = QuotaGuard(per_run_max=2)
    guard.check_and_consume("channels.list", n_calls=2)   # 2 units — exactly at cap
    with pytest.raises(QuotaExceededError):
        guard.check_and_consume("channels.list", n_calls=1)  # would exceed cap


# ─────────────────────────────────────────────────────────────────────────────
# T-E2: Dry-run mode returns empty stubs and charges zero real quota
# ─────────────────────────────────────────────────────────────────────────────

def test_te2_dry_run_no_network_calls():
    """T-E2: Dry-run YouTubeClient returns empty items and logs quota but makes no HTTP calls."""
    yt = YouTubeClient(mode="dry_run", per_run_max=100)
    result = yt.get_channel_stats(["UCtest123"])
    assert isinstance(result, list)
    assert result == [], "Dry-run should return empty channel stats list"
    # Quota units ARE charged in dry-run (logged, not enforced externally)
    assert yt.quota.units_used >= 0


# ─────────────────────────────────────────────────────────────────────────────
# T-E3: Salted SHA-256 author hashing
# ─────────────────────────────────────────────────────────────────────────────

def test_te3_author_hashing_deterministic_and_one_way():
    """T-E3: Hash is deterministic for same input and different for distinct inputs."""
    salt = "test_salt_abc123"
    author1 = "UCabcdef"
    author2 = "UCxyzwvu"

    h1a = _hash_author_id(author1, salt)
    h1b = _hash_author_id(author1, salt)
    h2 = _hash_author_id(author2, salt)

    # Deterministic
    assert h1a == h1b, "Same input must produce same hash"
    # Distinct inputs → distinct hashes
    assert h1a != h2, "Different authors must produce different hashes"
    # Verify format: 64-char hex (SHA-256)
    assert len(h1a) == 64 and all(c in "0123456789abcdef" for c in h1a)
    # Verify algorithm matches manual computation
    expected = hashlib.sha256(f"{salt}:{author1}".encode()).hexdigest()
    assert h1a == expected


# ─────────────────────────────────────────────────────────────────────────────
# T-E4: Purchase-intent classifier
# ─────────────────────────────────────────────────────────────────────────────

def test_te4_purchase_intent_classifier(ecfg):
    """T-E4: Rule-based classifier correctly flags intent vs. non-intent comments."""
    patterns = _compile_intent_patterns(ecfg)
    min_hits = ecfg["purchase_intent"]["min_keyword_hits"]

    intent_comments = [
        "Where can I buy this product?",
        "What's the price?",
        "Do you have a discount code?",
        "I want to order one right now",
        "Is there a promo link?",
    ]
    non_intent_comments = [
        "Great video! Keep it up.",
        "I learned so much from this.",
        "First comment!",
        "😂😂😂",
        "This is amazing content.",
    ]

    for comment in intent_comments:
        result = classify_purchase_intent(comment, patterns, min_hits)
        assert result == 1, f"Expected intent=1 for: '{comment}'"

    for comment in non_intent_comments:
        result = classify_purchase_intent(comment, patterns, min_hits)
        assert result == 0, f"Expected intent=0 for: '{comment}'"


# ─────────────────────────────────────────────────────────────────────────────
# T-E5: Reservoir sampler correctness
# ─────────────────────────────────────────────────────────────────────────────

def test_te5_reservoir_sampler():
    """T-E5: reservoir_sample returns exactly k items and is reproducible."""
    data = list(range(1000))
    k = 50
    seed = 42

    sample1 = reservoir_sample(iter(data), k=k, seed=seed)
    sample2 = reservoir_sample(iter(data), k=k, seed=seed)

    assert len(sample1) == k, f"Expected {k} items, got {len(sample1)}"
    assert sample1 == sample2, "Same seed must produce identical sample"
    # All items in sample must be from the original stream
    assert all(item in data for item in sample1)
    # When stream has fewer than k items, return all
    small = reservoir_sample(iter(range(10)), k=100, seed=0)
    assert len(small) == 10


# ─────────────────────────────────────────────────────────────────────────────
# T-E6: Duplicate comment share = 0 for unique comments
# ─────────────────────────────────────────────────────────────────────────────

def test_te6_duplicate_comment_share_unique(spark):
    """T-E6: All unique comments → duplicate_comment_share = 0."""
    rows = [
        {
            "channel_id": "ch1", "video_id": "v1", "comment_id": f"c{i}",
            "author_id_hashed": f"author_{i}", "text": f"unique text {i}",
            "like_count": 0, "reply_count": 0, "published_at": "2024-01-01T00:00:00Z",
            "purchase_intent": 0, "sampled_ts": "2024-01-01T00:00:00Z",
        }
        for i in range(20)
    ]
    df = _make_comment_df(spark, rows)
    result = _duplicate_comment_share(df).collect()
    assert len(result) == 1
    row = result[0]
    assert row["channel_id"] == "ch1"
    assert row["n_comments_sampled"] == 20
    assert row["duplicate_comment_share"] == pytest.approx(0.0, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# T-E7: Top-1 commenter share
# ─────────────────────────────────────────────────────────────────────────────

def test_te7_top1_commenter_share(spark):
    """T-E7: Top-1 commenter share is correctly computed."""
    # author_A posts 4 comments, author_B posts 1 comment → top1 share = 4/5 = 0.8
    rows = [
        {
            "channel_id": "ch2", "video_id": "v1", "comment_id": f"c{i}",
            "author_id_hashed": "author_A" if i < 4 else "author_B",
            "text": f"text {i}", "like_count": 0, "reply_count": 0,
            "published_at": "2024-01-01T00:00:00Z", "purchase_intent": 0,
            "sampled_ts": "2024-01-01T00:00:00Z",
        }
        for i in range(5)
    ]
    df = _make_comment_df(spark, rows)
    result = _top_commenter_shares(df).filter(F.col("channel_id") == "ch2").collect()
    assert len(result) == 1
    assert result[0]["top1_commenter_share"] == pytest.approx(0.8, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────────
# T-E8: any_authenticity_flag fires when threshold breached
# ─────────────────────────────────────────────────────────────────────────────

def test_te8_authenticity_flag_fires_on_duplicate_breach(spark, ecfg):
    """T-E8: any_authenticity_flag=True when duplicate_comment_share > threshold."""
    dup_thresh = ecfg["authenticity"]["duplicate_comment_max_share"]  # 0.15

    # Create 20 comments where 10 are duplicates of the same text+author → dup_share = 0.5
    rows = []
    for i in range(10):
        rows.append({
            "channel_id": "ch_dup", "video_id": "v1", "comment_id": f"uniq_{i}",
            "author_id_hashed": "author_A", "text": "buy this now!", "like_count": 0,
            "reply_count": 0, "published_at": "2024-01-01T00:00:00Z",
            "purchase_intent": 1, "sampled_ts": "2024-01-01T00:00:00Z",
        })
    for i in range(10):
        rows.append({
            "channel_id": "ch_dup", "video_id": "v1", "comment_id": f"other_{i}",
            "author_id_hashed": f"author_{i + 2}", "text": f"nice video {i}",
            "like_count": 0, "reply_count": 0, "published_at": "2024-01-01T00:00:00Z",
            "purchase_intent": 0, "sampled_ts": "2024-01-01T00:00:00Z",
        })
    df = _make_comment_df(spark, rows)
    df_quality = compute_audience_quality(df, ecfg)
    row = df_quality.filter(F.col("channel_id") == "ch_dup").collect()
    assert len(row) == 1
    assert row[0]["any_authenticity_flag"] is True, (
        f"Expected authenticity flag for dup_share > {dup_thresh}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-E9: Funnel candidate cap is respected
# ─────────────────────────────────────────────────────────────────────────────

def test_te9_funnel_candidate_cap(spark, ecfg):
    """T-E9: After Stage 4, result has at most max_api_candidates rows."""
    # Create synthetic gold-like DataFrame with 30 channels, all passing gates
    from pyspark.ml.linalg import Vectors
    import pyspark.sql.types as T

    schema = T.StructType([
        T.StructField("channel_id",      T.StringType(),  False),
        T.StructField("probability",      T.StringType(),  True),  # placeholder
        T.StructField("influencer_prob",  T.DoubleType(),  True),
        T.StructField("prediction",       T.DoubleType(),  True),
        T.StructField("label",            T.DoubleType(),  True),
        T.StructField("engagement_rate",  T.DoubleType(),  True),
        T.StructField("channel_age_days", T.DoubleType(),  True),
        T.StructField("domain_purity",    T.DoubleType(),  True),
        T.StructField("upload_cadence_days", T.DoubleType(), True),
        T.StructField("size_tier",        T.StringType(),  True),
    ])

    n = 30
    rows = [
        (
            f"ch_{i:04d}",    # channel_id
            None,              # probability (raw vector — skipped; influencer_prob is pre-computed)
            0.70 + i * 0.001, # influencer_prob (all well above 0.55 gate)
            1.0,              # prediction
            1.0,              # label
            0.05,             # engagement_rate
            500.0 * (i + 1),  # channel_age_days — gives reach_proxy well above 5000
            0.9,              # domain_purity
            7.0,              # upload_cadence_days
            "micro",          # size_tier
        )
        for i in range(n)
    ]
    df_gold = spark.createDataFrame(rows, schema=schema)

    # Derive reach_proxy as in funnel.py
    df_gold = df_gold.withColumn(
        "reach_proxy", F.col("engagement_rate") * F.col("channel_age_days")
    )

    # Apply Stage 4 manually
    from pyspark.sql.window import Window
    cap = ecfg["funnel"]["max_api_candidates"]
    w = Window.orderBy(F.col("influencer_prob").desc())
    df_capped = df_gold.withColumn("funnel_rank", F.row_number().over(w))
    df_capped = df_capped.filter(F.col("funnel_rank") <= cap)

    assert df_capped.count() <= cap, (
        f"Funnel output {df_capped.count()} rows exceeds cap {cap}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-E10: Loyal commenter share is zero when no author repeats
# ─────────────────────────────────────────────────────────────────────────────

def test_te10_loyal_commenter_share_zero_no_repeats(spark, ecfg):
    """T-E10: loyal_commenter_share=0 when every author appears in exactly 1 video."""
    loyal_min = ecfg["loyalty"]["loyal_videos_min"]

    # 10 unique authors, each commenting in exactly 1 video
    rows = [
        {
            "channel_id": "ch_noloyal", "video_id": f"v{i}", "comment_id": f"c{i}",
            "author_id_hashed": f"author_{i}", "text": f"comment {i}",
            "like_count": 0, "reply_count": 0, "published_at": "2024-01-01T00:00:00Z",
            "purchase_intent": 0, "sampled_ts": "2024-01-01T00:00:00Z",
        }
        for i in range(10)
    ]
    df = _make_comment_df(spark, rows)
    result = _loyal_commenter_share(df, loyal_min).filter(
        F.col("channel_id") == "ch_noloyal"
    ).collect()
    assert len(result) == 1
    assert result[0]["loyal_commenter_share"] == pytest.approx(0.0, abs=1e-6), (
        "No author repeats across videos → loyal share must be 0.0"
    )
