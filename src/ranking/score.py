"""
src/ranking/score.py
Phase 7 — Domain-Aware Promotion-Potential Score Engine.

Calculates the Promotion-Potential Score (0–100) per creator with:
  1. Component breakdown (fit, conversion_evidence, real_reach, engagement_quality, momentum, consistency)
  2. Dynamic weight renormalisation when components are missing + partial_evidence flag
  3. Deductions for sponsor saturation and competitor exposure
  4. Percentile rank normalisation within domain and size tier
  5. Full explainability per creator
"""
from __future__ import annotations

import logging
from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from src.common.config import get_scoring_config
from src.common.logging_setup import setup_logging
from src.common.paths import local

logger = setup_logging(__name__)


def compute_component_scores(
    df: DataFrame,
    fit_scores_df: DataFrame | None = None,
    competitor_brands: list[str] | None = None,
) -> DataFrame:
    """
    Compute raw normalized sub-components in [0, 1] for all channels.

    Columns expected/computed in `df`:
      - fit: in [0, 1] from fit_scores_df or domain_purity fallback
      - conversion_evidence: promo_lift, sponsored presence, intent
      - real_reach: median non-sponsored views, reach efficiency
      - engagement_quality: tier-adjusted engagement rate minus penalty
      - momentum: upload cadence / activity rate
      - consistency: inverted view consistency CV (1 / (1 + cv))
    """
    competitor_brands = competitor_brands or []
    existing_cols = set(df.columns)

    # 1. Join fit scores if provided, or read existing fit_score / domain_purity
    if fit_scores_df is not None:
        df = df.join(fit_scores_df.select("channel_id", "fit_score"), on="channel_id", how="left")
        df = df.withColumn("fit_raw", F.coalesce(F.col("fit_score"), F.lit(0.0)))
    elif "fit_score" in existing_cols:
        df = df.withColumn("fit_raw", F.coalesce(F.col("fit_score"), F.lit(0.5)))
    elif "domain_purity" in existing_cols:
        df = df.withColumn("fit_raw", F.coalesce(F.col("domain_purity"), F.lit(0.5)))
    else:
        df = df.withColumn("fit_raw", F.lit(0.5))

    # Ensure fit is bounded in [0, 1]
    df = df.withColumn(
        "comp_fit",
        F.when(F.col("fit_raw") < 0.0, 0.0)
        .when(F.col("fit_raw") > 1.0, 1.0)
        .otherwise(F.col("fit_raw"))
        .cast("double"),
    )

    # 2. Conversion evidence in [0, 1]
    if "promo_lift" in existing_cols and "sponsored_count" in existing_cols:
        conv_expr = F.when(
            F.col("promo_lift").isNotNull(),
            F.when(F.col("promo_lift") <= 0.0, 0.0)
            .when(F.col("promo_lift") >= 3.0, 1.0)
            .otherwise(F.col("promo_lift") / 3.0),
        ).otherwise(
            F.when(F.col("sponsored_count") > 0, F.least(F.col("sponsored_rate") * 2.0, F.lit(0.5)))
            .otherwise(None)
        )
    elif "promo_lift" in existing_cols:
        conv_expr = F.when(
            F.col("promo_lift").isNotNull(),
            F.when(F.col("promo_lift") <= 0.0, 0.0)
            .when(F.col("promo_lift") >= 3.0, 1.0)
            .otherwise(F.col("promo_lift") / 3.0),
        ).otherwise(
            F.when(F.col("sponsored_rate") > 0, F.least(F.col("sponsored_rate") * 2.0, F.lit(0.5)))
            .otherwise(None)
            if "sponsored_rate" in existing_cols else None
        )
    elif "sponsored_rate" in existing_cols:
        conv_expr = F.when(F.col("sponsored_rate") > 0, F.least(F.col("sponsored_rate") * 2.0, F.lit(0.5))).otherwise(None)
    else:
        conv_expr = F.lit(None)

    df = df.withColumn("comp_conversion_evidence", conv_expr.cast("double"))

    # 3. Real reach in [0, 1]
    if "median_views_nonsponsored" in existing_cols and "median_views" in existing_cols:
        views_col = F.coalesce(F.col("median_views_nonsponsored"), F.col("median_views"), F.lit(100.0))
    elif "median_views_nonsponsored" in existing_cols:
        views_col = F.coalesce(F.col("median_views_nonsponsored"), F.lit(100.0))
    elif "median_views" in existing_cols:
        views_col = F.coalesce(F.col("median_views"), F.lit(100.0))
    else:
        views_col = F.lit(1000.0)

    df = df.withColumn(
        "comp_real_reach",
        F.when(views_col <= 100.0, 0.0)
        .when(views_col >= 1_000_000.0, 1.0)
        .otherwise((F.log10(views_col) - 2.0) / 4.0)
        .cast("double"),
    )

    # 4. Engagement quality in [0, 1]
    if "engagement_rate" in existing_cols:
        eng_col = F.coalesce(F.col("engagement_rate"), F.lit(0.0))
        df = df.withColumn(
            "comp_engagement_quality",
            F.when(eng_col <= 0.0, 0.0)
            .when(eng_col >= 0.10, 1.0)
            .otherwise(eng_col / 0.10)
            .cast("double"),
        )
    else:
        df = df.withColumn("comp_engagement_quality", F.lit(0.3).cast("double"))

    # 5. Momentum in [0, 1]
    if "upload_cadence_days" in existing_cols:
        cadence = F.coalesce(F.col("upload_cadence_days"), F.lit(14.0))
        df = df.withColumn(
            "comp_momentum",
            F.when(cadence <= 7.0, 1.0)
            .when(cadence >= 60.0, 0.1)
            .otherwise(1.0 - (cadence - 7.0) / 53.0 * 0.9)
            .cast("double"),
        )
    else:
        df = df.withColumn("comp_momentum", F.lit(0.5).cast("double"))

    # 6. Consistency in [0, 1]
    if "view_consistency_cv" in existing_cols:
        cv = F.coalesce(F.col("view_consistency_cv"), F.lit(1.0))
        df = df.withColumn(
            "comp_consistency",
            (F.lit(1.0) / (F.lit(1.0) + F.greatest(cv, F.lit(0.0)))).cast("double"),
        )
    else:
        df = df.withColumn("comp_consistency", F.lit(0.5).cast("double"))

    # 7. Penalties
    if "sponsored_rate" in existing_cols:
        sp_rate = F.coalesce(F.col("sponsored_rate"), F.lit(0.0))
        df = df.withColumn(
            "penalty_saturation",
            F.when(sp_rate > 0.5, (sp_rate - 0.5) / 0.5 * 10.0)
            .otherwise(0.0)
            .cast("double"),
        )
    else:
        df = df.withColumn("penalty_saturation", F.lit(0.0).cast("double"))

    if "competitor_brand_count" in existing_cols:
        df = df.withColumn(
            "penalty_competitor",
            F.when(F.col("competitor_brand_count") > 0, 15.0).otherwise(0.0).cast("double"),
        )
    else:
        df = df.withColumn("penalty_competitor", F.lit(0.0).cast("double"))

    # Add convenience aliases for component scores
    df = (
        df.withColumn("fit_score", F.col("comp_fit"))
        .withColumn("conversion_score", F.coalesce(F.col("comp_conversion_evidence"), F.lit(0.0)))
        .withColumn("reach_score", F.col("comp_real_reach"))
        .withColumn("engagement_score", F.col("comp_engagement_quality"))
        .withColumn("momentum_score", F.col("comp_momentum"))
        .withColumn("consistency_score", F.col("comp_consistency"))
    )

    return df


def calculate_promotion_potential_score(
    df: DataFrame,
    scoring_cfg: dict[str, Any] | None = None,
) -> DataFrame:
    """
    Computes the final weighted score with dynamic weight renormalisation for
    missing components, applies penalties, and computes within-domain/tier percentile ranks.

    Parameters
    ----------
    df : DataFrame
        DataFrame containing `comp_*` and `penalty_*` columns.
    scoring_cfg : dict, optional
        Loaded from config/scoring.yaml.

    Returns
    -------
    DataFrame with:
      - raw_score: 0–100 weighted score
      - promotion_potential_score: 0–100 percentile rank within domain x tier
      - partial_evidence: boolean flag if any component was missing
      - contribution_*: explainability points for each component
    """
    scoring_cfg = scoring_cfg or get_scoring_config()
    components_cfg = scoring_cfg.get("components", {})

    w_fit = float(components_cfg.get("fit", {}).get("weight", 25))
    w_conv = float(components_cfg.get("conversion_evidence", {}).get("weight", 25))
    w_reach = float(components_cfg.get("real_reach", {}).get("weight", 15))
    w_eng = float(components_cfg.get("engagement_quality", {}).get("weight", 15))
    w_mom = float(components_cfg.get("momentum", {}).get("weight", 10))
    w_cons = float(components_cfg.get("consistency", {}).get("weight", 10))

    # Identify missing components per row and compute effective total weight
    # Available weight = sum of weights for non-null components
    has_fit = F.col("comp_fit").isNotNull()
    has_conv = F.col("comp_conversion_evidence").isNotNull()
    has_reach = F.col("comp_real_reach").isNotNull()
    has_eng = F.col("comp_engagement_quality").isNotNull()
    has_mom = F.col("comp_momentum").isNotNull()
    has_cons = F.col("comp_consistency").isNotNull()

    # Flag partial evidence if ANY component is missing
    partial_flag = (~has_fit) | (~has_conv) | (~has_reach) | (~has_eng) | (~has_mom) | (~has_cons)
    df = df.withColumn("partial_evidence", partial_flag)

    eff_weight = (
        F.when(has_fit, w_fit).otherwise(0.0)
        + F.when(has_conv, w_conv).otherwise(0.0)
        + F.when(has_reach, w_reach).otherwise(0.0)
        + F.when(has_eng, w_eng).otherwise(0.0)
        + F.when(has_mom, w_mom).otherwise(0.0)
        + F.when(has_cons, w_cons).otherwise(0.0)
    )
    # Ensure no division by zero
    eff_weight = F.greatest(eff_weight, F.lit(1e-6))

    # Weight renormalisation factor: scale factor to bring sum to 100
    norm_factor = 100.0 / eff_weight

    # Individual contributions (points out of 100)
    df = df.withColumn(
        "contribution_fit",
        F.round(F.coalesce(F.col("comp_fit"), F.lit(0.0)) * (w_fit * norm_factor), 2),
    )
    df = df.withColumn(
        "contribution_conversion_evidence",
        F.round(F.coalesce(F.col("comp_conversion_evidence"), F.lit(0.0)) * (w_conv * norm_factor), 2),
    )
    df = df.withColumn(
        "contribution_real_reach",
        F.round(F.coalesce(F.col("comp_real_reach"), F.lit(0.0)) * (w_reach * norm_factor), 2),
    )
    df = df.withColumn(
        "contribution_engagement_quality",
        F.round(F.coalesce(F.col("comp_engagement_quality"), F.lit(0.0)) * (w_eng * norm_factor), 2),
    )
    df = df.withColumn(
        "contribution_momentum",
        F.round(F.coalesce(F.col("comp_momentum"), F.lit(0.0)) * (w_mom * norm_factor), 2),
    )
    df = df.withColumn(
        "contribution_consistency",
        F.round(F.coalesce(F.col("comp_consistency"), F.lit(0.0)) * (w_cons * norm_factor), 2),
    )

    # Base weighted score (0–100)
    base_score = (
        F.col("contribution_fit")
        + F.col("contribution_conversion_evidence")
        + F.col("contribution_real_reach")
        + F.col("contribution_engagement_quality")
        + F.col("contribution_momentum")
        + F.col("contribution_consistency")
    )

    # Total penalties
    total_penalty = F.col("penalty_saturation") + F.col("penalty_competitor")

    # Net raw score (clipped to 0–100)
    raw_score = F.greatest(F.least(base_score - total_penalty, F.lit(100.0)), F.lit(0.0))
    df = df.withColumn("raw_score", F.round(raw_score, 2))

    # Percentile rank within domain and tier
    # Window partitioned by (size_tier) or (domain, size_tier)
    part_cols = []
    if "primary_domain" in df.columns:
        part_cols.append("primary_domain")
    if "size_tier" in df.columns:
        part_cols.append("size_tier")

    if part_cols:
        w_spec = Window.partitionBy(*part_cols)
        w_order = Window.partitionBy(*part_cols).orderBy("raw_score")
        # Percentile rank in [0, 100]
        # percentile = (rank - 1) / (count - 1) * 100 if count > 1 else 50.0
        df = df.withColumn("_rank", F.rank().over(w_order))
        df = df.withColumn("_count", F.count("*").over(w_spec))
        df = df.withColumn(
            "promotion_potential_score",
            F.when(F.col("_count") <= 1, 50.0)
            .otherwise(
                F.round((F.col("_rank") - 1) / (F.col("_count") - 1) * 100.0, 1)
            ),
        ).drop("_rank", "_count")
    else:
        # Whole population percentile
        w_all = Window.orderBy("raw_score")
        w_cnt = Window.partitionBy()
        df = df.withColumn("_rank", F.rank().over(w_all))
        df = df.withColumn("_count", F.count("*").over(w_cnt))
        df = df.withColumn(
            "promotion_potential_score",
            F.when(F.col("_count") <= 1, 50.0)
            .otherwise(
                F.round((F.col("_rank") - 1) / (F.col("_count") - 1) * 100.0, 1)
            ),
        ).drop("_rank", "_count")

    return df


def rank_creators_for_brief(
    spark: SparkSession,
    product_brief: str = "",
    competitor_brands: list[str] | None = None,
) -> DataFrame:
    """
    Full Phase 7 scoring pipeline:
      1. Load gold influencer profiles
      2. Join sponsorship metrics
      3. Compute semantic fit scores
      4. Score components, apply dynamic renormalisation & penalties
      5. Rank within domain and tier
    """
    gold_path = str(local("gold", "channel_influencer_profiles"))
    df_gold = spark.read.parquet(gold_path)

    # Join sponsorship metrics (select only columns not already in df_gold)
    sp_path = str(local("silver", "channel_sponsorship_metrics"))
    try:
        df_sp = spark.read.parquet(sp_path).select(
            "channel_id", "median_views_nonsponsored", "promo_lift"
        )
        df_merged = df_gold.join(df_sp, on="channel_id", how="left")
    except Exception:
        df_merged = df_gold.withColumn("median_views_nonsponsored", F.col("median_views")).withColumn("promo_lift", F.lit(None).cast("double"))

    # Compute fit scores if brief provided
    fit_df = None
    if product_brief.strip():
        from src.ranking.fit_score import build_channel_text_profiles, ChannelFitScorer
        profiles = build_channel_text_profiles(spark)
        scorer = ChannelFitScorer(num_features=2048).fit(profiles)
        fit_df = scorer.compute_fit_scores(spark, product_brief)

    # Compute component scores
    df_components = compute_component_scores(
        df_merged,
        fit_scores_df=fit_df,
        competitor_brands=competitor_brands,
    )

    # Final score & percentile rank
    df_scored = calculate_promotion_potential_score(df_components)
    return df_scored
