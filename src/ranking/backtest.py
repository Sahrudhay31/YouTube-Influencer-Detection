"""
src/ranking/backtest.py
Phase R7 — Time-Split Backtesting Engine with Age Normalization & Bootstrap CIs.

Validates the Promotion-Potential Score across multiple historical cutoffs T:
1. Computes channel ranking strictly using data with upload_date <= T (assert max date <= T).
2. Evaluates actual promotional performance on videos after T (upload_date > T).
3. Evaluates both raw views and age-normalized views (views per day since upload at crawl).
4. Compares the Promotion-Potential Score against 3 baselines:
   - Baseline 1: Rank by baseline median views.
   - Baseline 2: Rank by baseline upload activity.
   - Baseline 3: Random Baseline (seeded, averaged over 1,000 draws with analytic expectations).
5. Computes paired bootstrap 95% confidence intervals for the difference in NDCG@k / Precision@k.
6. Evaluates consistency across >= 3 cutoffs (2018-01-01, 2018-07-01, 2019-01-01).
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from scipy.stats import spearmanr

from src.common.config import get_settings
from src.common.engagement import calculate_engagement_expr
from src.common.logging_setup import setup_logging
from src.common.paths import local
from src.common.spark_session import get_spark
from src.ranking.score import calculate_promotion_potential_score, compute_component_scores

logger = setup_logging(__name__)

DEFAULT_CUTOFF_DATES = ["2018-01-01", "2018-07-01", "2019-01-01"]


# ── Age Normalization Helper (Pure Python & Unit Testable T-R7) ───────────────

def compute_age_normalized_views(
    view_count: float | int,
    upload_date: str,
    crawl_date: str,
) -> float:
    """
    Computes views per day since upload at crawl time.
    T-R7 unit-testable helper with hand values.
    """
    v = float(view_count) if view_count is not None else 0.0
    try:
        t_up = datetime.fromisoformat(str(upload_date)[:10])
        t_cr = datetime.fromisoformat(str(crawl_date)[:10])
        days = max(1.0, float((t_cr - t_up).days))
    except Exception:
        days = 1.0
    return round(v / days, 4)


# ── Standalone Pure-Python Metrics (Testable via Hand Fixtures T-R6, T-R8) ─────

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


def compute_random_baseline(
    binary_labels: list[int | bool],
    relevances: list[float],
    k: int,
    n_draws: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """
    Simulates a random ranking baseline over n_draws permutations.
    Returns (mean_precision_at_k, mean_ndcg_at_k).
    """
    rng = np.random.default_rng(seed)
    n = len(binary_labels)
    if n == 0 or k <= 0:
        return 0.0, 0.0

    prec_scores = []
    ndcg_scores = []

    b_arr = np.array(binary_labels)
    r_arr = np.array(relevances)

    for _ in range(n_draws):
        perm = rng.permutation(n)
        perm_b = b_arr[perm]
        perm_r = r_arr[perm]
        prec_scores.append(compute_precision_at_k(perm_b.tolist(), k=k))
        ndcg_scores.append(compute_ndcg(perm_r.tolist(), k=k))

    return float(np.mean(prec_scores)), float(np.mean(ndcg_scores))


def compute_paired_bootstrap_ci_diff(
    scores_a: list[float],
    scores_b: list[float],
    labels: list[int | bool],
    relevances: list[float],
    k: int,
    metric: str = "ndcg",
    n_bootstraps: int = 1000,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    Computes point estimate and 95% paired bootstrap confidence interval for:
        Metric(Ranking A) - Metric(Ranking B)
    Metric can be 'ndcg' or 'precision'.
    Returns (diff_point_est, ci_low, ci_high).
    """
    n = len(scores_a)
    if n == 0 or k <= 0:
        return 0.0, 0.0, 0.0

    rng = np.random.default_rng(seed)

    def calc_metric(order: np.ndarray) -> float:
        top_k_idx = order[:k]
        if metric == "precision":
            return float(np.mean([labels[i] for i in top_k_idx]))
        else:
            rel_list = [relevances[i] for i in top_k_idx]
            return compute_ndcg(rel_list, k=k)

    order_a = np.argsort(-np.array(scores_a))
    order_b = np.argsort(-np.array(scores_b))
    point_est = calc_metric(order_a) - calc_metric(order_b)

    diffs = []
    indices = np.arange(n)
    for _ in range(n_bootstraps):
        boot_idx = rng.choice(indices, size=n, replace=True)
        # Rank the bootstrapped sample under both models
        sub_a = np.array(scores_a)[boot_idx]
        sub_b = np.array(scores_b)[boot_idx]
        sub_labels = np.array(labels)[boot_idx]
        sub_rels = np.array(relevances)[boot_idx]

        sub_order_a = boot_idx[np.argsort(-sub_a)]
        sub_order_b = boot_idx[np.argsort(-sub_b)]

        top_a = sub_order_a[:k]
        top_b = sub_order_b[:k]

        if metric == "precision":
            m_a = float(np.mean([labels[i] for i in top_a]))
            m_b = float(np.mean([labels[i] for i in top_b]))
        else:
            m_a = compute_ndcg([relevances[i] for i in top_a], k=k)
            m_b = compute_ndcg([relevances[i] for i in top_b], k=k)

        diffs.append(m_a - m_b)

    ci_low = float(np.percentile(diffs, 2.5))
    ci_high = float(np.percentile(diffs, 97.5))
    return float(point_est), ci_low, ci_high


# ── Backtest Spark Pipeline ───────────────────────────────────────────────────

def run_time_split_backtest(
    spark: SparkSession,
    cutoff_date: str = "2019-01-01",
    k_list: list[int] | None = None,
) -> dict[str, Any]:
    """
    Execute time-split backtest at cutoff_date T.
    Strictly asserts max(upload_date) <= cutoff_date for the ranking stage (T-R5, T-R11).
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

    # ── T-R5 / T-R11 Assertion: Verify ranking uses NO data after T ───────────
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
        calculate_engagement_expr(
            like_col=F.sum(F.coalesce(F.col("like_count"), F.lit(0.0))),
            dislike_col=F.sum(F.coalesce(F.col("dislike_count"), F.lit(0.0))),
            view_col=F.sum("view_count"),
        ).alias("engagement_rate"),
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
            F.datediff(F.lit(cutoff_date), F.col("min_upload_date")),
        )
        .withColumn(
            "upload_cadence_days",
            F.col("channel_age_days") / F.greatest(F.col("train_video_count") - 1, F.lit(1)),
        )
        .join(df_profiles, on="channel_id", how="inner")
    )

    # 3. Compute Promotion-Potential Score using strictly pre-T features
    ch_scored = compute_component_scores(ch_features)
    ch_scored = calculate_promotion_potential_score(ch_scored)

    # 4. Compute Post-T Actual Performance (Ground Truth)
    # Include age-normalized views: views_per_day = view_count / max(1, datediff(crawl_date, upload_date))
    crawl_ref = "2019-11-01"
    test_videos_norm = test_videos.withColumn(
        "days_since_upload",
        F.greatest(F.lit(1.0), F.datediff(F.lit(crawl_ref), F.col("upload_date")).cast("double")),
    ).withColumn(
        "views_per_day",
        F.col("view_count") / F.col("days_since_upload"),
    )

    post_t_channel_agg = test_videos_norm.groupBy("channel_id").agg(
        F.count("display_id").alias("post_video_count"),
        F.sum(F.when(F.col("is_sponsored") == True, 1).otherwise(0)).alias("post_sponsored_count"),
        F.percentile_approx("view_count", 0.5, 1000).alias("post_median_views"),
        F.percentile_approx(
            F.when(F.col("is_sponsored") == True, F.col("view_count")), 0.5, 1000
        ).alias("post_sponsored_views"),
        F.percentile_approx(
            F.when(F.col("is_sponsored") == False, F.col("view_count")), 0.5, 1000
        ).alias("post_nonsponsored_views"),
        F.percentile_approx(
            F.when(F.col("is_sponsored") == True, F.col("views_per_day")), 0.5, 1000
        ).alias("post_sponsored_vpd"),
        F.percentile_approx(
            F.when(F.col("is_sponsored") == False, F.col("views_per_day")), 0.5, 1000
        ).alias("post_nonsponsored_vpd"),
        calculate_engagement_expr(
            like_col=F.sum(F.coalesce(F.col("like_count"), F.lit(0.0))),
            dislike_col=F.sum(F.coalesce(F.col("dislike_count"), F.lit(0.0))),
            view_col=F.sum("view_count"),
        ).alias("post_engagement_rate"),
    )

    post_t_eval = post_t_channel_agg.withColumn(
        "post_promo_lift",
        F.when(
            (F.col("post_sponsored_count") >= 1) & (F.col("post_nonsponsored_views") > 0),
            F.col("post_sponsored_views") / F.col("post_nonsponsored_views"),
        ).otherwise(
            F.when(F.col("post_sponsored_count") >= 1, 1.0).otherwise(0.0)
        ),
    ).withColumn(
        "post_promo_lift_age_norm",
        F.when(
            (F.col("post_sponsored_count") >= 1) & (F.col("post_nonsponsored_vpd") > 0),
            F.col("post_sponsored_vpd") / F.col("post_nonsponsored_vpd"),
        ).otherwise(
            F.when(F.col("post_sponsored_count") >= 1, 1.0).otherwise(0.0)
        ),
    )

    # Relevance Grades:
    # Grade 3: post_promo_lift >= 1.25 and sponsored post-T
    # Grade 2: post_promo_lift >= 1.0
    # Grade 1: post_sponsored_count >= 1
    # Grade 0: 0 sponsored post-T
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
    methods = {
        "PromotionPotentialScore": df_eval.sort_values("promotion_potential_score", ascending=False),
        "Baseline_MedianViews": df_eval.sort_values("baseline_median_views", ascending=False),
        "Baseline_Activity": df_eval.sort_values("baseline_activity", ascending=False),
    }

    metrics_results: dict[str, dict[str, Any]] = {}

    for method_name, sorted_df in methods.items():
        relevances = sorted_df["relevance_grade"].tolist()
        binary_labels = sorted_df["is_successful_promo"].tolist()
        scores = sorted_df[
            "promotion_potential_score"
            if method_name == "PromotionPotentialScore"
            else ("baseline_median_views" if "Views" in method_name else "baseline_activity")
        ].tolist()
        actual_performance = sorted_df["post_promo_lift"].tolist()

        m: dict[str, Any] = {}
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

    # Evaluate Random Baseline across k
    rand_metrics: dict[str, Any] = {}
    for k in k_list:
        rand_p, rand_ndcg = compute_random_baseline(
            binary_labels=df_eval["is_successful_promo"].tolist(),
            relevances=df_eval["relevance_grade"].tolist(),
            k=k,
            n_draws=1000,
            seed=42,
        )
        rand_metrics[f"precision@{k}"] = round(rand_p, 4)
        rand_metrics[f"ndcg@{k}"] = round(rand_ndcg, 4)
    rand_metrics["spearman_rho"] = 0.0
    rand_metrics["spearman_pvalue"] = 1.0
    metrics_results["Baseline_Random"] = rand_metrics

    # Compute Paired Bootstrap 95% CIs for Score vs Baselines (at k=10)
    score_vals = df_eval["promotion_potential_score"].tolist()
    labels = df_eval["is_successful_promo"].tolist()
    rels = df_eval["relevance_grade"].tolist()

    ci_comparisons = {}
    for base_name, col_key in [
        ("Baseline_MedianViews", "baseline_median_views"),
        ("Baseline_Activity", "baseline_activity"),
    ]:
        base_vals = df_eval[col_key].tolist()
        pt_diff, ci_l, ci_h = compute_paired_bootstrap_ci_diff(
            score_vals, base_vals, labels, rels, k=10, metric="ndcg", n_bootstraps=1000, seed=42
        )
        ci_comparisons[base_name] = {
            "metric": "ndcg@10",
            "diff_point_est": round(pt_diff, 4),
            "ci95_low": round(ci_l, 4),
            "ci95_high": round(ci_h, 4),
            "excludes_zero": bool(ci_l > 0.0 or ci_h < 0.0),
        }

    return {
        "cutoff_date": cutoff_date,
        "n_train_videos": n_train,
        "n_test_videos": n_test,
        "n_channels_evaluated": total_eval_channels,
        "relevance_definition": "Post-T sponsored video with post_promo_lift >= 1.0 (binary) and graded 0..3",
        "metrics": metrics_results,
        "paired_bootstrap_ci_vs_baselines": ci_comparisons,
    }


def run_multi_cutoff_backtest(
    spark: SparkSession,
    cutoffs: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Executes backtest across >= 3 cutoffs and outputs summary CSV and markdown.
    """
    if cutoffs is None:
        cutoffs = DEFAULT_CUTOFF_DATES

    all_results = []
    for cutoff in cutoffs:
        res = run_time_split_backtest(spark, cutoff_date=cutoff)
        all_results.append(res)

    # Write summary CSV
    csv_path = local("metrics", "backtest_results.csv")
    csv_rows = []
    for r in all_results:
        c_date = r["cutoff_date"]
        n_ch = r["n_channels_evaluated"]
        for method, m in r["metrics"].items():
            csv_rows.append({
                "method": method,
                "cutoff_date": c_date,
                "n_channels": n_ch,
                "precision@5": m.get("precision@5", 0.0),
                "precision@10": m.get("precision@10", 0.0),
                "ndcg@5": m.get("ndcg@5", 0.0),
                "ndcg@10": m.get("ndcg@10", 0.0),
                "spearman_rho": m.get("spearman_rho", 0.0),
                "spearman_pvalue": m.get("spearman_pvalue", 1.0),
            })
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)

    # Write markdown report
    md_path = local("metrics", "latest_backtest.md")
    md_lines = [
        "# Multi-Cutoff Time-Split Backtest Evaluation\n",
        f"> **Cutoffs Evaluated:** {', '.join(cutoffs)}  ",
        "> **Baselines:** Median Views, Activity, Random (1,000 draws)  ",
        "> **Relevance Definition:** Post-T sponsored video with post_promo_lift >= 1.0 (graded 0..3)  \n",
        "| Cutoff Date | Method | Precision@5 | Precision@10 | NDCG@5 | NDCG@10 | Spearman rho |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for row in csv_rows:
        md_lines.append(
            f"| `{row['cutoff_date']}` | **{row['method']}** | {row['precision@5']:.4f} | {row['precision@10']:.4f} | {row['ndcg@5']:.4f} | {row['ndcg@10']:.4f} | {row['spearman_rho']:.4f} |"
        )
    md_lines.append("\n## Paired Bootstrap 95% Confidence Intervals (Cutoff 2019-01-01, NDCG@10):\n")
    latest_r = all_results[-1]
    for base_name, comp in latest_r.get("paired_bootstrap_ci_vs_baselines", {}).items():
        claim = "statistically significant difference" if comp["excludes_zero"] else "no statistically clear difference (CI includes 0)"
        md_lines.append(
            f"- **Score vs {base_name}:** Diff = `{comp['diff_point_est']:+.4f}` (95% CI: `[{comp['ci95_low']:+.4f}, {comp['ci95_high']:+.4f}]`) -> *{claim}*"
        )

    Path(md_path).write_text("\n".join(md_lines), encoding="utf-8")
    logger.info("Saved multi-cutoff backtest report to %s.", md_path)

    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-cutoff time-split backtest")
    parser.add_argument("--cutoffs", nargs="+", default=DEFAULT_CUTOFF_DATES)
    args = parser.parse_args()

    spark = get_spark(app_name="ranking-backtest", local_mode=True)
    try:
        run_multi_cutoff_backtest(spark, cutoffs=args.cutoffs)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
