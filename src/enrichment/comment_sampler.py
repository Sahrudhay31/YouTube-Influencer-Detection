"""
src/enrichment/comment_sampler.py
Phase 6 — Comment Sampling, Loyalty Proxy & Purchase-Intent Classification.

Steps performed per channel candidate:
  1. Fetch top-K videos via YouTubeClient.
  2. Iterate comment threads for each video (bounded by QuotaGuard).
  3. Reservoir-sample up to max_comments_per_channel comments.
  4. Hash author IDs with salted SHA-256 → privacy-preserving loyalty analysis.
  5. Rule-based purchase-intent classifier (keyword matching).
  6. Persist raw comment samples to data/silver/comment_samples (Parquet).
  7. Stratified export of labelling split to labels/purchase_intent_labelled.csv.
"""
from __future__ import annotations

import csv
import hashlib
import logging
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    BooleanType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from src.common.logging_setup import setup_logging
from src.common.paths import local
from src.enrichment.youtube_client import YouTubeClient

logger = setup_logging(__name__)

_ENRICHMENT_CFG_PATH = Path(__file__).resolve().parents[2] / "config" / "enrichment.yaml"


def load_enrichment_config() -> dict:
    with open(_ENRICHMENT_CFG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ─────────────────────────────────────────────────────────────────────────────
# Privacy: Salted SHA-256 author hashing
# ─────────────────────────────────────────────────────────────────────────────

def _hash_author_id(raw_author_id: str, salt: str) -> str:
    """
    Return the salted SHA-256 hex digest of a YouTube author channel ID.

    The salt is read from COMMENT_HASH_SALT env var at runtime.
    This replaces the real author ID in all stored data — the original ID
    is NEVER written to disk.

    Algorithm: SHA-256(salt + ":" + raw_author_id)
    """
    payload = f"{salt}:{raw_author_id}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


_OLD_LEAKED_SALT_FINGERPRINT = "9dd0b8f06033de1a27a076c1d4d17e068a48a79b7a669c8aab8ce9b102096721"


def get_hash_salt() -> str:
    """Read salt from environment variable; raise if unset or equals old leaked salt."""
    salt = os.environ.get("COMMENT_HASH_SALT", "").strip()
    if not salt:
        raise EnvironmentError(
            "COMMENT_HASH_SALT env var is not set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    salt_fp = hashlib.sha256(salt.encode("utf-8")).hexdigest()
    if salt_fp == _OLD_LEAKED_SALT_FINGERPRINT:
        raise ValueError(
            "COMMENT_HASH_SALT matches the old compromised salt from git history. "
            "Generate a fresh salt with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return salt


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based purchase-intent classifier
# ─────────────────────────────────────────────────────────────────────────────

def _compile_intent_patterns(ecfg: dict) -> list[re.Pattern]:
    keywords = ecfg["purchase_intent"]["intent_keywords"]
    return [re.compile(kw, re.IGNORECASE) for kw in keywords]


def classify_purchase_intent(text: str, patterns: list[re.Pattern], min_hits: int = 1) -> int:
    """
    Return 1 if the comment text contains at least min_hits keyword matches,
    else 0.  This is the rule-based baseline (label=1 → purchase intent).
    """
    if not text:
        return 0
    hits = sum(1 for p in patterns if p.search(text))
    return int(hits >= min_hits)


# ─────────────────────────────────────────────────────────────────────────────
# Reservoir sampler
# ─────────────────────────────────────────────────────────────────────────────

def reservoir_sample(stream, k: int, seed: int) -> list:
    """
    Algorithm R reservoir sampling — keeps exactly k items from an iterable
    in O(n) time with O(k) memory.
    """
    rng = random.Random(seed)
    reservoir = []
    for i, item in enumerate(stream):
        if i < k:
            reservoir.append(item)
        else:
            j = rng.randint(0, i)
            if j < k:
                reservoir[j] = item
    return reservoir


# ─────────────────────────────────────────────────────────────────────────────
# Comment schema
# ─────────────────────────────────────────────────────────────────────────────

COMMENT_SCHEMA = StructType([
    StructField("channel_id",         StringType(),    False),
    StructField("video_id",           StringType(),    False),
    StructField("comment_id",         StringType(),    False),
    StructField("author_id_hashed",   StringType(),    False),
    StructField("text",               StringType(),    True),
    StructField("like_count",         IntegerType(),   True),
    StructField("reply_count",        IntegerType(),   True),
    StructField("published_at",       StringType(),    True),
    StructField("purchase_intent",    IntegerType(),   False),
    StructField("sampled_ts",         StringType(),    False),
])


# ─────────────────────────────────────────────────────────────────────────────
# Core sampling function
# ─────────────────────────────────────────────────────────────────────────────

def sample_comments_for_channel(
    channel_id: str,
    yt: YouTubeClient,
    ecfg: dict,
    salt: str,
    intent_patterns: list[re.Pattern],
) -> list[dict[str, Any]]:
    """
    Fetch, reservoir-sample, hash, and classify comments for one channel.

    Returns a list of dicts (matching COMMENT_SCHEMA) or empty list on error.
    """
    comment_cfg = ecfg["comments"]
    intent_cfg = ecfg["purchase_intent"]
    max_videos = comment_cfg["videos_per_channel"]
    max_pages = comment_cfg["max_pages_per_video"]
    max_comments = comment_cfg["max_comments_per_channel"]
    seed = comment_cfg["seed"]
    min_hits = intent_cfg["min_keyword_hits"]
    sampled_ts = datetime.now(timezone.utc).isoformat()

    try:
        # 1. Get top videos for channel
        videos = yt.get_top_videos(channel_id, max_results=max_videos)
        if not videos:
            logger.debug("[Comments] No videos found for channel %s", channel_id)
            return []

        video_ids = []
        for v in videos:
            vid = (
                v.get("id", {}).get("videoId")  # from search.list
                if isinstance(v.get("id"), dict)
                else v.get("id")
            )
            if vid:
                video_ids.append(vid)

        if not video_ids:
            return []

        # 2. Stream all comment threads across videos, then reservoir-sample
        def _comment_stream():
            for vid_id in video_ids[:max_videos]:
                for thread in yt.iter_comment_threads(vid_id, max_pages=max_pages):
                    snippet = thread.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                    raw_author = snippet.get("authorChannelId", {})
                    if isinstance(raw_author, dict):
                        raw_author = raw_author.get("value", "")
                    yield {
                        "video_id": vid_id,
                        "comment_id": thread.get("id", ""),
                        "raw_author_id": raw_author or "",
                        "text": snippet.get("textDisplay", "") or "",
                        "like_count": int(snippet.get("likeCount", 0) or 0),
                        "reply_count": int(thread.get("snippet", {}).get("totalReplyCount", 0) or 0),
                        "published_at": snippet.get("publishedAt", ""),
                    }

        sampled = reservoir_sample(_comment_stream(), k=max_comments, seed=seed)

        # 3. Hash author IDs & classify
        records = []
        for c in sampled:
            hashed_author = _hash_author_id(c["raw_author_id"], salt) if c["raw_author_id"] else ""
            intent = classify_purchase_intent(c["text"], intent_patterns, min_hits)
            records.append({
                "channel_id":       channel_id,
                "video_id":         c["video_id"],
                "comment_id":       c["comment_id"],
                "author_id_hashed": hashed_author,
                "text":             c["text"],
                "like_count":       c["like_count"],
                "reply_count":      c["reply_count"],
                "published_at":     c["published_at"],
                "purchase_intent":  intent,
                "sampled_ts":       sampled_ts,
            })

        logger.info(
            "[Comments] Channel %s: sampled %d comments (%d intent=1)",
            channel_id, len(records), sum(r["purchase_intent"] for r in records)
        )
        return records

    except Exception as exc:  # noqa: BLE001
        logger.warning("[Comments] Error processing channel %s: %s", channel_id, exc)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Batch runner
# ─────────────────────────────────────────────────────────────────────────────

def run_comment_sampling(
    spark: SparkSession,
    channel_ids: list[str],
    yt: YouTubeClient,
    ecfg: dict,
) -> DataFrame:
    """
    Run comment sampling for all shortlisted channels.
    Returns a Spark DataFrame conforming to COMMENT_SCHEMA.
    """
    salt = get_hash_salt()
    intent_patterns = _compile_intent_patterns(ecfg)

    all_records: list[dict] = []
    for ch_id in channel_ids:
        records = sample_comments_for_channel(
            channel_id=ch_id,
            yt=yt,
            ecfg=ecfg,
            salt=salt,
            intent_patterns=intent_patterns,
        )
        all_records.extend(records)

    logger.info("[Comments] Total records collected: %d", len(all_records))

    if not all_records:
        logger.warning("[Comments] No comment records collected. Returning empty DataFrame.")
        fields = ", ".join([f"CAST(NULL AS {f.dataType.simpleString()}) AS {f.name}" for f in COMMENT_SCHEMA.fields])
        return spark.sql(f"SELECT {fields} WHERE 1=0")

    # Use JSON-lines staging to avoid PySpark RDD cloudpickle serialization recursion issues on Python 3.14
    import json
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r) + "\n")
        tmp_path = f.name

    import atexit
    def _cleanup():
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass
    atexit.register(_cleanup)
    return spark.read.schema(COMMENT_SCHEMA).json(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# Stratified label export
# ─────────────────────────────────────────────────────────────────────────────

def export_labels_for_annotation(df_comments: DataFrame, ecfg: dict) -> int:
    """
    Stratified export of comments to labels/purchase_intent_labelled.csv.
    Balances intent=0 and intent=1 rows so annotators see both classes.

    Returns the number of rows exported.
    """
    comment_cfg = ecfg["comments"]
    frac = comment_cfg["label_export_fraction"]
    min_rows = comment_cfg["label_export_min_rows"]
    max_rows = comment_cfg["label_export_max_rows"]
    seed = comment_cfg["seed"]

    out_path = Path(ecfg["output"]["label_export"])
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_total = df_comments.count()
    if n_total == 0:
        logger.warning("[Labels] No comments to export.")
        return 0

    target_n = max(min_rows, min(max_rows, int(n_total * frac)))

    # Stratified: half from intent=1 (minority), half from intent=0
    df1 = df_comments.filter(F.col("purchase_intent") == 1)
    df0 = df_comments.filter(F.col("purchase_intent") == 0)
    n1 = df1.count()
    n0 = df0.count()

    take1 = min(n1, target_n // 2)
    take0 = min(n0, target_n - take1)

    sampled = (
        df1.sample(fraction=min(1.0, (take1 + 1) / max(n1, 1)), seed=seed).limit(take1)
        .union(
            df0.sample(fraction=min(1.0, (take0 + 1) / max(n0, 1)), seed=seed).limit(take0)
        )
    )

    # Write CSV (local, small)
    rows = sampled.select(
        "channel_id", "video_id", "comment_id", "text", "purchase_intent", "sampled_ts"
    ).collect()

    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["channel_id", "video_id", "comment_id", "text", "purchase_intent", "sampled_ts"],
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.asDict())

    n_exported = len(rows)
    logger.info(
        "[Labels] Exported %d rows to %s (intent=1: %d, intent=0: %d)",
        n_exported, out_path, take1, take0
    )
    return n_exported
