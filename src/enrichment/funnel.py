"""
src/enrichment/funnel.py
Phase 6 — Multi-Stage Enrichment Funnel.

Applies four sequential filters to gold channel profiles to produce a
shortlist of candidates ready for live YouTube API enrichment:

  Stage 1 – Domain gate:        channel must belong to a labelled domain.
  Stage 2 – Influencer score:   model probability >= threshold.
  Stage 3 – Reach gate:         estimated reach (median_views proxy) >= threshold.
  Stage 4 – Candidate cap:      top-N by probability, capped at max_api_candidates.

The shortlist is written to data/gold/enrichment_candidates as Parquet.

Usage (dry-run, default):
    python -m src.enrichment.funnel

Usage (live, bounded):
    python -m src.enrichment.funnel --mode live --max-candidates 20
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from src.common.config import get_settings
from src.common.logging_setup import setup_logging
from src.common.paths import local
from src.common.spark_session import get_spark

logger = setup_logging(__name__)

_ENRICHMENT_CFG_PATH = Path(__file__).resolve().parents[2] / "config" / "enrichment.yaml"


def load_enrichment_config() -> dict:
    """Load enrichment.yaml and return as a dict."""
    with open(_ENRICHMENT_CFG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_domain_labelled_channels(spark: SparkSession) -> set[str]:
    """
    Return the set of channel_ids that appear in the silver domain profiles
    table (i.e. they belong to at least one labelled domain).
    """
    domain_path = str(local("silver", "channel_domain_profiles"))
    try:
        df = spark.read.parquet(domain_path)
        rows = df.select("channel_id").dropna().distinct().collect()
        return {r["channel_id"] for r in rows}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load domain profiles (%s). Domain gate disabled.", exc)
        return set()


def run_funnel(
    spark: SparkSession,
    ecfg: dict,
    max_candidates: int | None = None,
    mode: str = "dry_run",
) -> DataFrame:
    """
    Execute the four-stage enrichment funnel.

    Parameters
    ----------
    spark          : active SparkSession
    ecfg           : parsed enrichment.yaml config dict
    max_candidates : override for ecfg.funnel.max_api_candidates
    mode           : 'dry_run' (default) or 'live'

    Returns
    -------
    Spark DataFrame of shortlisted candidates with funnel metadata columns.
    """
    funnel_cfg = ecfg["funnel"]
    cap = max_candidates if max_candidates is not None else funnel_cfg["max_api_candidates"]

    # ── Load gold channel profiles (written by Phase 5 classifier) ────────────
    gold_path = str(local("gold", "channel_influencer_profiles"))
    logger.info("[Funnel] Loading gold profiles from: %s", gold_path)
    df = spark.read.parquet(gold_path)

    # Ensure probability column exists (GBT writes 'probability' as Vector)
    if "probability" not in df.columns:
        raise ValueError("Gold profiles missing 'probability' column. Re-run Phase 5 classifier.")

    # Extract P(influencer=1) from the probability DenseVector using native vector_to_array
    from pyspark.ml.functions import vector_to_array
    df = df.withColumn("influencer_prob", vector_to_array(F.col("probability"))[1].cast("double"))

    total_before = df.count()
    logger.info("[Funnel] Stage 0: total gold channels = %d", total_before)

    # ── Stage 1: Domain gate ──────────────────────────────────────────────────
    if funnel_cfg.get("require_labelled_domain", True):
        labelled_ids = load_domain_labelled_channels(spark)
        if labelled_ids:
            df = df.filter(F.col("channel_id").isin(labelled_ids))
            logger.info("[Funnel] Stage 1 (Domain gate): %d channels remaining", df.count())
        else:
            logger.warning("[Funnel] Stage 1 skipped — no domain labels loaded.")
    else:
        logger.info("[Funnel] Stage 1 (Domain gate): DISABLED in config.")

    # ── Stage 2: Influencer probability gate ──────────────────────────────────
    prob_min = funnel_cfg["influencer_score_min"]
    df = df.filter(F.col("influencer_prob") >= prob_min)
    logger.info(
        "[Funnel] Stage 2 (Influencer prob >= %.2f): %d channels remaining",
        prob_min, df.count()
    )

    # ── Stage 3: Reach gate ───────────────────────────────────────────────────
    # median_views is a label-defining column and is NOT in gold features.
    # We use engagement_rate × channel_age_days as a lightweight reach proxy.
    # Alternatively, if median_views exists in the gold table we use it.
    if "median_views" in df.columns:
        reach_col = "median_views"
    elif "engagement_rate" in df.columns:
        # synthetic proxy: engagement_rate * channel_age_days (monotone with size)
        df = df.withColumn("reach_proxy", F.col("engagement_rate") * F.col("channel_age_days"))
        reach_col = "reach_proxy"
    else:
        logger.warning("[Funnel] Stage 3 skipped — no reach column available.")
        reach_col = None

    reach_min = funnel_cfg["reach_min_views"]
    if reach_col is not None:
        df = df.filter(F.col(reach_col) >= reach_min)
        logger.info(
            "[Funnel] Stage 3 (Reach '%s' >= %d): %d channels remaining",
            reach_col, reach_min, df.count()
        )

    # ── Stage 4: Candidate cap (top-N by influencer_prob) ────────────────────
    w = Window.orderBy(F.col("influencer_prob").desc())
    df = df.withColumn("funnel_rank", F.row_number().over(w))
    df = df.filter(F.col("funnel_rank") <= cap)
    n_final = df.count()
    logger.info("[Funnel] Stage 4 (cap=%d): %d candidates shortlisted", cap, n_final)

    # ── Annotate with funnel metadata ─────────────────────────────────────────
    df = df.withColumn("enrichment_mode", F.lit(mode))
    df = df.withColumn("funnel_version", F.lit("v6.0"))
    df = df.withColumn(
        "funnel_pass_rate",
        F.lit(round(n_final / max(total_before, 1), 4))
    )

    # Keep only configured gold columns + funnel annotations
    keep_cols = funnel_cfg.get("gold_columns", []) + [
        "influencer_prob", "funnel_rank", "enrichment_mode", "funnel_version",
        "funnel_pass_rate", "prediction", "label",
    ]
    # Only keep columns that actually exist in the DataFrame
    present = set(df.columns)
    keep_cols = [c for c in keep_cols if c in present]
    df = df.select(*keep_cols)

    return df


def save_candidates(df: DataFrame, out_path: str, mode: str) -> int:
    """Write shortlist to Parquet. In dry-run mode, writes to a .dryrun sub-folder."""
    if mode == "dry_run":
        out_path = out_path.rstrip("/") + ".dryrun"
        logger.info("[Funnel] DRY-RUN: writing to %s (not live path)", out_path)
    df.write.mode("overwrite").parquet(out_path)
    count = df.count()
    logger.info("[Funnel] Wrote %d candidates to %s", count, out_path)
    return count


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description="Phase 6 Enrichment Funnel")
    parser.add_argument(
        "--mode",
        choices=["dry_run", "live"],
        default="dry_run",
        help="dry_run (default) skips actual API calls; live enables them.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=None,
        help="Override max_api_candidates from enrichment.yaml.",
    )
    parser.add_argument("--local", action="store_true", default=True)
    args = parser.parse_args(argv)

    ecfg = load_enrichment_config()
    spark = get_spark("EnrichmentFunnel", local_mode=args.local)

    candidates = run_funnel(
        spark=spark,
        ecfg=ecfg,
        max_candidates=args.max_candidates,
        mode=args.mode,
    )

    out_path = ecfg["output"]["funnel_candidates"]
    n = save_candidates(candidates, out_path, args.mode)

    spark.stop()
    return {"candidates_written": n, "mode": args.mode}


if __name__ == "__main__":
    main()
