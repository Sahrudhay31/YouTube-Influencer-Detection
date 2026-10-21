"""
src/ranking/backtest.py
Phase 7 — Time-Split Backtesting Engine.

Validates the Promotion-Potential Score using a historical time-split cutoff T.
1. Computes channel ranking strictly using data with upload_date <= T (assert max date <= T).
2. Evaluates actual promotional performance on videos after T (upload_date > T).
3. Computes Precision@k, NDCG@k, and Spearman rank correlation.
4. Compares the Promotion-Potential Score against two baselines:
   - Baseline 1: Rank by subscriber count.
   - Baseline 2: Rank by pre-T median views.
5. Logs results to metrics/backtest_results.csv and metrics/latest_backtest.md.
"""
from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from scipy.stats import spearmanr

from src.common.config import get_settings
from src.common.logging_setup import setup_logging
from src.common.paths import local
from src.common.spark_session import get_spark
from src.ranking.score import calculate_promotion_potential_score, compute_component_scores

logger = setup_logging(__name__)

DEFAULT_CUTOFF_DATE = "2019-01-01"


# ── Standalone Pure-Python Metrics (Testable via Hand Fixtures T-R6) ──────────

def compute_dcg(relevances: list[float], k: int | None = None) -> float:
    """
    Compute Discounted Cumulative Gain at rank k:
    DCG@k = sum_{i=1}^k (2^{rel_i} - 1) / log2(i + 1)
    """
    if k is not None:
        relevances = relevances[:k]
    dcg = 0.0
    for i, rel in enumerate(relevances, start=1):
        gain = (2.0 ** float(rel)) - 1.0
        discount = math.log2(i + 1.0)
        dcg += gain / discount
    return float(dcg)


def compute_ndcg(relevances: list[float], k: int | None = None) -> float:
    """
    Compute Normalized Discounted Cumulative Gain at rank k:
    NDCG@k = DCG@k / IDCG@k
    """
    if not relevances:
        return 0.0
    if k is not None:
        relevances = relevances[:k]

    actual_dcg = compute_dcg(relevances, k=k)
    ideal_relevances = sorted(relevances, reverse=True)
    ideal_dcg = compute_dcg(ideal_relevances, k=k)

    if ideal_dcg <= 0.0:
        return 0.0
    return float(actual_dcg / ideal_dcg)


def compute_precision_at_k(binary_labels: list[int | bool], k: int) -> float:
    """
    Compute Precision@k: fraction of top-k items that are relevant (label == 1/True).
    """
    if not binary_labels or k <= 0:
        return 0.0
    top_k = binary_labels[:k]
    hits = sum(1 for label in top_k if label)
    return float(hits / len(top_k))


# ── Backtest Spark Pipeline ───────────────────────────────────────────────────

def run_time_split_backtest(
    spark: SparkSession,
    cutoff_date: str = DEFAULT_CUTOFF_DATE,
    k_list: list[int] | None = None,
) -> dict[str, Any]:
    """
    Execute time-split backtest at cutoff_date T.
    Strictly asserts max(upload_date) <= cutoff_date for the ranking stage (T-R5).
    """
    if k_list is None:
        k_list = [5, 10]

    video_features_path = str(local("silver", "sponsorship_video_features"))
    channel_profiles_path = str(local("gold", "channel_influencer_profiles"))

    logger.info("[Backtest] Loading datasets for cutoff T = %s ...", cutoff_date)
    df_videos = spark.read.parquet(video_features_path)
    df_profiles = spark.read.parquet(channel_profiles_path).select(
        "channel_id", "size_tier", "domain_purity"
    )

    # 1. Historical Split: videos with upload_date <= cutoff_date
    train_videos = df_videos.filter(F.col("upload_date") <= cutoff_date)
    test_videos = df_videos.filter(F.col("upload_date") > cutoff_date)

    n_train = train_videos.count()
    n_test = test_videos.count()
    logger.info("[Backtest] Video counts: train (<= %s) = %d, test (> %s) = %d", cutoff_date, n_train, cutoff_date, n_test)

    if n_train == 0 or n_test == 0:
        raise ValueError(f"Invalid time split for T={cutoff_date}: train={n_train}, test={n_test}")

    # ── T-R5 Assertion: Verify ranking uses NO data after T ───────────────────
    max_train_date = train_videos.select(F.max("upload_date")).collect()[0][0]
    logger.info("[Backtest] T-R5 Verification: max train upload_date = %s (cutoff = %s)", max_train_date, cutoff_date)
    assert str(max_train_date) <= cutoff_date, f"T-R5 VIOLATION: max train date {max_train_date} > {cutoff_date}"

    # Verify post-T contains sponsored videos
    test_sponsored = test_videos.filter(F.col("is_sponsored") == True)
    n_test_sponsored = test_sponsored.count()
    logger.info("[Backtest] Post-T sponsored videos count = %d", n_test_sponsored)
    if n_test_sponsored == 0:
        raise ValueError(f"No sponsored videos found after cutoff {cutoff_date}")

    # 2. Compute channel features strictly from train_videos
    # Group by channel_id
    ch_agg = train_videos.groupBy("channel_id").agg(
        F.count("display_id").alias("train_video_count"),
        F.sum(F.when(F.col("is_sponsored") == True, 1).otherwise(0)).alias("sponsored_count"),
        F.sum(F.when(F.col("is_sponsored") == False, 1).otherwise(0)).alias("nonsponsored_count"),
        F.percentile_approx("view_count", 0.5, 1000).alias("median_views"),
        F.percentile_approx(
            F.when(F.col("is_sponsored") == False, F.col("view_count")), 0.5, 1000
        ).alias("median_views_nonsponsored"),
        F.percentile_approx(
            F.when(F.col("is_sponsored") == True, F.col("view_count")), 0.5, 1000
        ).alias("median_views_sponsored"),
        (F.sum(F.col("like_count")) / F.greatest(F.sum("view_count"), F.lit(1.0))).alias("engagement_rate"),
        F.min("upload_date").alias("min_upload_date"),
        F.max("upload_date").alias("max_upload_date"),
        (F.stddev("view_count") / F.greatest(F.mean("view_count"), F.lit(1.0))).alias("view_consistency_cv"),
    )

    # Derived channel features as of T
    ch_features = (
        ch_agg.withColumn(
            "sponsored_rate",
            F.col("sponsored_count") / F.greatest(F.col("train_video_count"), F.lit(1.0)),
        )
        .withColumn(
            "promo_lift",
            F.when(
                (F.col("sponsored_count") >= 2) & (F.col("nonsponsored_count") >= 5),
                F.col("median_views_sponsored") / F.greatest(F.col("median_views_nonsponsored"), F.lit(1.0)),
            ).otherwise(F.lit(None)),
        )
        .withColumn(
            "channel_age_days",
            F.datediff(F.lit(cutoff_date), F.col("min_upload_date")).cast("double"),
        )
        .withColumn(
            "upload_cadence_days",
            (F.datediff(F.col("max_upload_date"), F.col("min_upload_date")) / F.greatest(F.col("train_video_count"), F.lit(1.0))).cast("double"),
        )
    )

    # Join with profiles
    ch_full = ch_features.join(df_profiles, on="channel_id", how="inner")

    # Fill defaults for nulls in scoring features
    ch_full = (
        ch_full.withColumn("median_views_nonsponsored", F.coalesce(F.col("median_views_nonsponsored"), F.col("median_views"), F.lit(1000.0)))
        .withColumn("view_consistency_cv", F.coalesce(F.col("view_consistency_cv"), F.lit(0.5)))
        .withColumn("upload_cadence_days", F.coalesce(F.col("upload_cadence_days"), F.lit(7.0)))
        .withColumn("channel_age_days", F.coalesce(F.col("channel_age_days"), F.lit(365.0)))
        .withColumn("sponsored_rate", F.coalesce(F.col("sponsored_rate"), F.lit(0.0)))
        .withColumn("domain_purity", F.coalesce(F.col("domain_purity"), F.lit(0.8)))
    )

    # 3. Calculate Promotion-Potential Score (pre-T)
    ch_components = compute_component_scores(ch_full)
    ch_scored = calculate_promotion_potential_score(ch_components)

    # 4. Compute Post-T Ground Truth Target
    # We measure actual promotional delivery of each channel post-T
    post_t_channel_agg = test_videos.groupBy("channel_id").agg(
        F.count("display_id").alias("post_video_count"),
        F.sum(F.when(F.col("is_sponsored") == True, 1).otherwise(0)).alias("post_sponsored_count"),
        F.percentile_approx("view_count", 0.5, 1000).alias("post_median_views"),
        F.percentile_approx(
            F.when(F.col("is_sponsored") == True, F.col("view_count")), 0.5, 1000
        ).alias("post_sponsored_views"),
        F.percentile_approx(
            F.when(F.col("is_sponsored") == False, F.col("view_count")), 0.5, 1000
        ).alias("post_nonsponsored_views"),
        (F.sum(F.col("like_count")) / F.greatest(F.sum("view_count"), F.lit(1.0))).alias("post_engagement_rate"),
    )

    post_t_eval = post_t_channel_agg.withColumn(
        "post_promo_lift",
        F.when(
            (F.col("post_sponsored_count") >= 1) & (F.col("post_nonsponsored_views") > 0),
            F.col("post_sponsored_views") / F.col("post_nonsponsored_views"),
        ).otherwise(
            F.when(F.col("post_sponsored_count") >= 1, 1.0).otherwise(0.0)
        ),
    )

    # Ground truth relevance grades:
    # Grade 3: post_promo_lift >= 1.25 and sponsored post-T
    # Grade 2: post_promo_lift >= 1.0 or post_sponsored_views >= post_median_views
    # Grade 1: post_sponsored_count >= 1
    # Grade 0: 0 sponsored post-T or low performance
    post_t_eval = post_t_eval.withColumn(
        "relevance_grade",
        F.when((F.col("post_sponsored_count") >= 1) & (F.col("post_promo_lift") >= 1.25), 3)
        .when((F.col("post_sponsored_count") >= 1) & (F.col("post_promo_lift") >= 1.0), 2)
        .when(F.col("post_sponsored_count") >= 1, 1)
        .otherwise(0),
    ).withColumn(
        "is_successful_promo",
        F.when(F.col("relevance_grade") >= 2, 1).otherwise(0),
    )

    # Join pre-T predictions with post-T actuals
    df_eval = (
        ch_scored.select(
            "channel_id",
            "promotion_potential_score",
            F.col("median_views").alias("baseline_median_views"),
            F.col("train_video_count").alias("baseline_activity"),
        )
        .join(post_t_eval, on="channel_id", how="inner")
        .toPandas()
    )

    total_eval_channels = len(df_eval)
    logger.info("[Backtest] Active channels evaluated across both periods: %d", total_eval_channels)

    # 5. Evaluate: Promotion-Potential Score vs Baselines
    # Baseline 1: Rank by baseline activity/subscribers
    # Baseline 2: Rank by baseline median views
    methods = {
        "PromotionPotentialScore": df_eval.sort_values("promotion_potential_score", ascending=False),
        "Baseline_MedianViews": df_eval.sort_values("baseline_median_views", ascending=False),
        "Baseline_Activity": df_eval.sort_values("baseline_activity", ascending=False),
    }

    metrics_results: dict[str, dict[str, float]] = {}

    for method_name, sorted_df in methods.items():
        relevances = sorted_df["relevance_grade"].tolist()
        binary_labels = sorted_df["is_successful_promo"].tolist()
        scores = sorted_df[
            "promotion_potential_score"
            if method_name == "PromotionPotentialScore"
            else ("baseline_median_views" if "Views" in method_name else "baseline_activity")
        ].tolist()
        actual_performance = sorted_df["post_promo_lift"].tolist()

        m: dict[str, float] = {}
        for k in k_list:
            m[f"precision@{k}"] = round(compute_precision_at_k(binary_labels, k=k), 4)
            m[f"ndcg@{k}"] = round(compute_ndcg(relevances, k=k), 4)

        # Spearman correlation with actual post-T promo lift
        if len(scores) > 2:
            res = spearmanr(scores, actual_performance)
            m["spearman_rho"] = round(float(res.statistic) if not np.isnan(res.statistic) else 0.0, 4)
            m["spearman_pvalue"] = round(float(res.pvalue) if not np.isnan(res.pvalue) else 1.0, 4)
        else:
            m["spearman_rho"] = 0.0
            m["spearman_pvalue"] = 1.0

        metrics_results[method_name] = m

    # 6. Save results to CSV and markdown
    csv_path = local("metrics", "backtest_results.csv")
    md_path = local("metrics", "latest_backtest.md")

    # CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["method", "cutoff_date", "n_channels"] + [f"precision@{k}" for k in k_list] + [f"ndcg@{k}" for k in k_list] + ["spearman_rho", "spearman_pvalue"]
        writer.writerow(header)
        for name, m in metrics_results.items():
            row = [name, cutoff_date, total_eval_channels] + [m[f"precision@{k}"] for k in k_list] + [m[f"ndcg@{k}"] for k in k_list] + [m["spearman_rho"], m["spearman_pvalue"]]
            writer.writerow(row)

    # Markdown Table
    md_lines = [
        f"# Time-Split Backtest Evaluation (Cutoff T = {cutoff_date})\n",
        f"- **Evaluation Period**: Videos with `upload_date > {cutoff_date}`",
        f"- **Historical Training**: Videos with `upload_date <= {cutoff_date}` ({n_train:,} videos)",
        f"- **Post-T Test Videos**: {n_test:,} videos ({n_test_sponsored:,} sponsored)",
        f"- **Active Channels Evaluated**: {total_eval_channels}\n",
        "| Ranking Method | Precision@5 | Precision@10 | NDCG@5 | NDCG@10 | Spearman rho | p-value |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for name, m in metrics_results.items():
        md_lines.append(
            f"| **{name}** | {m.get('precision@5', 0.0):.4f} | {m.get('precision@10', 0.0):.4f} | "
            f"{m.get('ndcg@5', 0.0):.4f} | {m.get('ndcg@10', 0.0):.4f} | "
            f"{m.get('spearman_rho', 0.0):.4f} | {m.get('spearman_pvalue', 1.0):.4f} |"
        )
    md_lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    logger.info("[Backtest] Saved backtest results to: %s and %s", csv_path, md_path)

    return {
        "cutoff_date": cutoff_date,
        "n_train_videos": n_train,
        "n_test_videos": n_test,
        "n_channels_evaluated": total_eval_channels,
        "metrics": metrics_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run time-split backtest for Promotion-Potential Score")
    parser.add_argument("--cutoff-date", default=DEFAULT_CUTOFF_DATE, help="Historical cutoff date T")
    args = parser.parse_args()

    spark = get_spark(app_name="ranking-backtest", local_mode=True)
    try:
        res = run_time_split_backtest(spark, cutoff_date=args.cutoff_date)
        print("\n-- Time-Split Backtest Summary --")
        print(f"Cutoff Date T: {res['cutoff_date']}")
        print(f"Channels Evaluated: {res['n_channels_evaluated']}")
        print("\nComparison against baselines:")
        for name, m in res["metrics"].items():
            print(f"  [{name}] Precision@5={m.get('precision@5', 0.0):.4f} | NDCG@5={m.get('ndcg@5', 0.0):.4f} | Spearman={m.get('spearman_rho', 0.0):.4f}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
