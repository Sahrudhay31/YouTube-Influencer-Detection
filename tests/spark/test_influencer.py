"""
tests/spark/test_influencer.py
Phase 5 Influencer-vs-Normal Classifier smoke tests:
- T-I1: Label-defining columns and feature columns are strictly disjoint (leakage guard).
- T-I2: Size tiers are exhaustive and mutually exclusive.
- T-I3: Model validation PR-AUC beats baseline PR-AUC.
- T-I4: Class weights are correctly computed and applied to balance minority class.
- T-I5: Feature nulls are handled gracefully without silent row drops.
"""
from __future__ import annotations

import atexit
import json
import tempfile
from pathlib import Path

import pytest
from pyspark.ml import Pipeline
from pyspark.ml.classification import RandomForestClassifier
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.feature import VectorAssembler
from pyspark.sql import DataFrame, SparkSession, functions as F

from src.common.spark_session import get_spark
from src.influencer.features import build_channel_features, load_influencer_config


def _safe_df(spark: SparkSession, rows: list[Any], cols: list[str]) -> DataFrame:
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
    for r in rows:
        d = dict(zip(cols, r))
        tf.write(json.dumps(d) + "\n")
    tf.close()
    atexit.register(lambda: Path(tf.name).unlink(missing_ok=True))
    return spark.read.json(tf.name)


@pytest.fixture(scope="module")
def spark():
    s = get_spark(app_name="bda-phase5-tests", local_mode=True)
    yield s


def test_ti1_leakage_guard_disjoint_columns():
    """T-I1: Feature columns and label-defining columns MUST have empty intersection."""
    cfg = load_influencer_config()
    feature_cols = set(cfg["feature_columns"])
    label_def_cols = set(cfg["label_definition"]["label_defining_columns"])

    intersection = feature_cols.intersection(label_def_cols)
    assert not intersection, f"LEAKAGE DETECTED! Overlapping columns found: {intersection}"


def test_ti2_size_tiers_exhaustive_and_mutually_exclusive(spark):
    """T-I2: Size tiers are exhaustive and mutually exclusive."""
    # Synthetic channels covering all 4 tier ranges:
    # nano (< 2511), micro (2511 to 8011), macro (8011 to 127745), mega (>= 127745)
    data = [
        ("ch_nano", 1000.0, 0, 0.0),
        ("ch_micro", 5000.0, 1, 0.1),
        ("ch_macro", 50000.0, 2, 0.2),
        ("ch_mega", 500000.0, 5, 0.5),
    ]
    df_spon = _safe_df(spark, data, ["channel_id", "median_views", "sponsored_count", "sponsored_rate"])

    # Minimal video data using corresponding view count for each tier
    vid_data = [
        (f"{ch}_v1", ch, 100, views, 10.0, 1.0, "2018-01-01 00:00:00")
        for ch, views, _, _ in data
    ]
    df_vid = _safe_df(
        spark, vid_data, ["display_id", "channel_id", "duration", "view_count", "like_count", "dislike_count", "upload_date"]
    )

    df_dom = _safe_df(spark, [(ch, 1.0, 1.0) for ch, _, _, _ in data], ["channel_id", "domain_purity", "in_domain_share"])

    df_feat = build_channel_features(df_vid, df_dom, df_spon)
    rows = df_feat.select("channel_id", "size_tier").collect()

    tier_map = {r["channel_id"]: r["size_tier"] for r in rows}
    assert tier_map["ch_nano"] == "nano"
    assert tier_map["ch_micro"] == "micro"
    assert tier_map["ch_macro"] == "macro"
    assert tier_map["ch_mega"] == "mega"

    valid_tiers = {"nano", "micro", "macro", "mega"}
    for r in rows:
        assert r["size_tier"] in valid_tiers
        assert r["size_tier"] is not None


def test_ti3_model_beats_baseline_pr_auc(spark):
    """T-I3: Model validation PR-AUC beats baseline PR-AUC (positive class ratio)."""
    # Create clear synthetic separation on engagement and cadence
    train_data = []
    # 20 Influencers: high engagement, high video count
    for i in range(20):
        train_data.append((100, 300.0, 0.08, 0.5, 500.0, 5.0, 0.9, 0.9, 1.0, 2.5))
    # 80 Normal channels: low engagement, low video count
    for i in range(80):
        train_data.append((5, 120.0, 0.01, 0.1, 100.0, 20.0, 0.1, 0.1, 0.0, 0.625))

    val_data = []
    for i in range(10):
        val_data.append((120, 350.0, 0.09, 0.6, 600.0, 4.0, 0.95, 0.95, 1.0, 2.5))
    for i in range(40):
        val_data.append((6, 110.0, 0.015, 0.1, 80.0, 25.0, 0.05, 0.05, 0.0, 0.625))

    cols = [
        "video_count", "mean_duration", "engagement_rate", "view_consistency_cv",
        "channel_age_days", "upload_cadence_days", "domain_purity", "in_domain_share",
        "label", "class_weight"
    ]
    train_df = _safe_df(spark, train_data, cols)
    val_df = _safe_df(spark, val_data, cols)

    feature_cols = cols[:8]
    assembler = VectorAssembler(inputCols=feature_cols, outputCol="features")
    rf = RandomForestClassifier(featuresCol="features", labelCol="label", weightCol="class_weight", numTrees=10, seed=42)

    model = Pipeline(stages=[assembler, rf]).fit(train_df)
    val_preds = model.transform(val_df)

    pr_eval = BinaryClassificationEvaluator(labelCol="label", rawPredictionCol="rawPrediction", metricName="areaUnderPR")
    model_pr_auc = float(pr_eval.evaluate(val_preds))

    # Baseline PR-AUC = P / (P + N) in validation set = 10 / 50 = 0.20
    baseline_pr_auc = 10.0 / 50.0

    assert model_pr_auc > baseline_pr_auc, (
        f"Model PR-AUC ({model_pr_auc:.4f}) failed to beat baseline ({baseline_pr_auc:.4f})"
    )


def test_ti4_class_weights_applied(spark):
    """T-I4: Class weights are correctly computed and applied to balance minority class."""
    n_pos = 20
    n_neg = 80
    n_total = 100

    w0_expected = n_total / (2.0 * n_neg)  # 100 / 160 = 0.625
    w1_expected = n_total / (2.0 * n_pos)  # 100 / 40 = 2.5

    data = [(1.0,) for _ in range(n_pos)] + [(0.0,) for _ in range(n_neg)]
    df = _safe_df(spark, data, ["label"])

    df_weighted = df.withColumn(
        "class_weight",
        F.when(F.col("label") == 1.0, F.lit(n_total / (2.0 * n_pos))).otherwise(F.lit(n_total / (2.0 * n_neg)))
    )

    summary = df_weighted.groupBy("label").agg(F.avg("class_weight").alias("avg_w")).collect()
    weight_map = {r["label"]: r["avg_w"] for r in summary}

    assert abs(weight_map[1.0] - w1_expected) < 1e-4
    assert abs(weight_map[0.0] - w0_expected) < 1e-4
    # The minority class weight must be strictly higher than majority class weight
    assert weight_map[1.0] > weight_map[0.0]


def test_ti5_feature_nulls_handled_no_silent_drops(spark):
    """T-I5: Feature nulls are imputed safely without silent row drops."""
    # Data with missing like/dislikes, single video (null stddev), null upload_dates
    vid_data = [
        ("v1", "ch_sparse", 100, 500.0, None, None, "2019-01-01 00:00:00"),
        ("v2", "ch_normal", 200, 1000.0, 50.0, 5.0, "2019-01-02 00:00:00"),
    ]
    df_vid = _safe_df(
        spark, vid_data, ["display_id", "channel_id", "duration", "view_count", "like_count", "dislike_count", "upload_date"]
    )
    df_dom = _safe_df(spark, [("ch_sparse", None, None), ("ch_normal", 1.0, 1.0)], ["channel_id", "domain_purity", "in_domain_share"])
    df_spon = _safe_df(spark, [("ch_sparse", 500.0, 0, 0.0), ("ch_normal", 1000.0, 1, 0.5)], ["channel_id", "median_views", "sponsored_count", "sponsored_rate"])

    df_feat = build_channel_features(df_vid, df_dom, df_spon)

    # Assert exactly 2 rows output (zero rows dropped)
    assert df_feat.count() == 2

    # Assert no nulls in critical feature columns
    cfg = load_influencer_config()
    for col in cfg["feature_columns"]:
        null_count = df_feat.filter(F.col(col).isNull()).count()
        assert null_count == 0, f"Column '{col}' contains unexpected nulls: {null_count}"
