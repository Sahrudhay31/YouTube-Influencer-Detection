"""
src/enrichment/pipeline.py
Phase 6 — Full Enrichment Pipeline Orchestrator.

Ties together all Phase 6 components:
  1. Enrichment funnel (multi-stage candidate filtering)
  2. Live YouTube API enrichment (channel stats snapshot)
  3. Comment sampling, loyalty proxy & purchase-intent classification
  4. Audience quality & authenticity checks
  5. Gold audience-quality table export

Usage (dry-run, default — no API calls, no quota consumed):
    python -m src.enrichment.pipeline

Usage (live — bounded, requires YOUTUBE_API_KEY):
    python -m src.enrichment.pipeline --mode live --max-units 300 --max-candidates 10
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone

from src.common.config import get_settings
from src.common.logging_setup import setup_logging
from src.common.paths import local
from src.common.spark_session import get_spark
from src.enrichment.audience_quality import compute_audience_quality, save_audience_quality
from src.enrichment.comment_sampler import export_labels_for_annotation, run_comment_sampling
from src.enrichment.funnel import load_enrichment_config, run_funnel, save_candidates
from src.enrichment.youtube_client import YouTubeClient

logger = setup_logging(__name__)


def run_enrichment_pipeline(
    mode: str = "dry_run",
    max_units: int | None = None,
    max_candidates: int | None = None,
    local_spark: bool = True,
) -> dict:
    """
    Execute the full Phase 6 enrichment pipeline end-to-end.

    Parameters
    ----------
    mode           : 'dry_run' | 'live'
    max_units      : per-run quota cap override
    max_candidates : funnel candidate cap override
    local_spark    : True for local Spark session

    Returns
    -------
    Summary dict with counts and timings.
    """
    t_start = time.time()
    logger.info("=" * 70)
    logger.info("PHASE 6 ENRICHMENT PIPELINE — mode=%s", mode.upper())
    logger.info("=" * 70)

    ecfg = load_enrichment_config()
    spark = get_spark("EnrichmentPipeline", local_mode=local_spark)

    summary: dict = {
        "mode": mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "funnel_candidates": 0,
        "api_channels_enriched": 0,
        "comments_sampled": 0,
        "labels_exported": 0,
        "audience_quality_channels": 0,
        "quota_units_used": 0,
        "errors": [],
    }

    # -- Step 1: Enrichment funnel ---------------------------------------------
    logger.info("-- Step 1: Enrichment funnel --")
    try:
        df_candidates = run_funnel(
            spark=spark,
            ecfg=ecfg,
            max_candidates=max_candidates,
            mode=mode,
        )
        n_candidates = save_candidates(df_candidates, ecfg["output"]["funnel_candidates"], mode)
        summary["funnel_candidates"] = n_candidates
        logger.info("Step 1 complete: %d candidates shortlisted.", n_candidates)
    except Exception as exc:
        logger.error("Step 1 FAILED: %s", exc, exc_info=True)
        summary["errors"].append(f"funnel: {exc}")
        spark.stop()
        return summary

    # -- Step 2: YouTube API live channel snapshot -----------------------------
    logger.info("-- Step 2: YouTube API channel snapshot --")
    yt = YouTubeClient(mode=mode, per_run_max=max_units)

    channel_ids = [r["channel_id"] for r in df_candidates.select("channel_id").collect()]

    try:
        channel_stats = yt.get_channel_stats(channel_ids)
        summary["api_channels_enriched"] = len(channel_stats)
        summary["quota_units_used"] = yt.quota.units_used
        logger.info(
            "Step 2 complete: %d channel records fetched (%d quota units).",
            len(channel_stats), yt.quota.units_used
        )
    except Exception as exc:
        logger.error("Step 2 FAILED: %s", exc, exc_info=True)
        summary["errors"].append(f"channel_stats: {exc}")
        # Non-fatal: continue to comment sampling

    # -- Step 3: Comment sampling, loyalty, purchase-intent -------------------
    logger.info("-- Step 3: Comment sampling & purchase-intent classification --")
    df_comments: DataFrame | None = None
    try:
        df_comments = run_comment_sampling(
            spark=spark,
            channel_ids=channel_ids,
            yt=yt,
            ecfg=ecfg,
        )
        summary["quota_units_used"] = yt.quota.units_used

        if df_comments is not None and df_comments.count() > 0:
            # Persist comment samples to silver
            comment_out = ecfg["output"]["comment_samples"]
            if mode == "dry_run":
                comment_out = comment_out.rstrip("/") + ".dryrun"
            df_comments.write.mode("overwrite").parquet(comment_out)
            summary["comments_sampled"] = df_comments.count()
            logger.info("Step 3 complete: %d comments sampled.", summary["comments_sampled"])
        else:
            logger.warning("Step 3: No comments collected (expected in dry-run mode).")
    except Exception as exc:
        logger.error("Step 3 FAILED: %s", exc, exc_info=True)
        summary["errors"].append(f"comment_sampling: {exc}")

    # -- Step 4: Label export --------------------------------------------------
    logger.info("-- Step 4: Stratified label export --")
    try:
        if df_comments is not None and df_comments.count() > 0:
            n_labels = export_labels_for_annotation(df_comments, ecfg)
            summary["labels_exported"] = n_labels
            logger.info("Step 4 complete: %d rows exported for annotation.", n_labels)
        else:
            logger.info("Step 4 skipped: no comments to export.")
    except Exception as exc:
        logger.error("Step 4 FAILED: %s", exc, exc_info=True)
        summary["errors"].append(f"label_export: {exc}")

    # -- Step 5: Audience quality & authenticity -------------------------------
    logger.info("-- Step 5: Audience quality & authenticity checks --")
    try:
        if df_comments is not None and df_comments.count() > 0:
            df_quality = compute_audience_quality(df_comments, ecfg)
            save_audience_quality(df_quality, ecfg, mode=mode)
            summary["audience_quality_channels"] = df_quality.count()
            logger.info(
                "Step 5 complete: quality computed for %d channels.",
                summary["audience_quality_channels"]
            )
        else:
            logger.info("Step 5 skipped: no comment data.")
    except Exception as exc:
        logger.error("Step 5 FAILED: %s", exc, exc_info=True)
        summary["errors"].append(f"audience_quality: {exc}")

    elapsed = round(time.time() - t_start, 1)
    summary["elapsed_s"] = elapsed
    summary["quota_units_used"] = yt.quota.units_used

    logger.info("=" * 70)
    logger.info(
        "PHASE 6 COMPLETE in %.1fs | candidates=%d | comments=%d | labels=%d | quota=%d units",
        elapsed,
        summary["funnel_candidates"],
        summary["comments_sampled"],
        summary["labels_exported"],
        summary["quota_units_used"],
    )
    if summary["errors"]:
        logger.warning("Non-fatal errors: %s", summary["errors"])
    logger.info("=" * 70)

    spark.stop()
    return summary


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Phase 6 Full Enrichment Pipeline")
    parser.add_argument(
        "--mode",
        choices=["dry_run", "live"],
        default="dry_run",
        help="dry_run (default) skips API calls; live enables real YouTube API calls.",
    )
    parser.add_argument(
        "--max-units",
        type=int,
        default=None,
        help="Per-run quota unit cap override (default: from quota.yaml).",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=None,
        help="Funnel candidate cap override.",
    )
    args = parser.parse_args(argv)

    result = run_enrichment_pipeline(
        mode=args.mode,
        max_units=args.max_units,
        max_candidates=args.max_candidates,
    )
    print("\n-- Phase 6 Pipeline Summary --")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
