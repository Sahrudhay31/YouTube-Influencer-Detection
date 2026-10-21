"""
src/influencer/classifier.py
Phase 5 Influencer-vs-Normal Channel Classification Workflow.
Trains Random Forest, GBT, and Logistic Regression with balanced class weights.
Enforces strict feature disjointness from label-defining columns (Leakage Guard).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from pyspark.ml import Pipeline
from pyspark.ml.classification import RandomForestClassifier, GBTClassifier, LogisticRegression
from pyspark.ml.evaluation import BinaryClassificationEvaluator, MulticlassClassificationEvaluator
from pyspark.ml.feature import VectorAssembler, StandardScaler
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from src.common.config import get_settings
from src.common.logging_setup import setup_logging
from src.common.metrics_logger import log_model_run
from src.common.paths import local
from src.common.spark_session import get_spark
from src.influencer.features import build_channel_features, load_influencer_config

logger = setup_logging(__name__)


def compute_binary_metrics(predictions: DataFrame) -> dict[str, float]:
    """
    Computes Accuracy, Macro-F1, F1-Positive, PR-AUC, and ROC-AUC.
    """
    acc_eval = MulticlassClassificationEvaluator(labelCol="label", predictionCol="prediction", metricName="accuracy")
    f1_eval = MulticlassClassificationEvaluator(labelCol="label", predictionCol="prediction", metricName="f1")
    pr_eval = BinaryClassificationEvaluator(labelCol="label", rawPredictionCol="rawPrediction", metricName="areaUnderPR")
    roc_eval = BinaryClassificationEvaluator(labelCol="label", rawPredictionCol="rawPrediction", metricName="areaUnderROC")

    acc = float(acc_eval.evaluate(predictions))
    macro_f1 = float(f1_eval.evaluate(predictions))
    pr_auc = float(pr_eval.evaluate(predictions))
    roc_auc = float(roc_eval.evaluate(predictions))

    # Binary positive class precision & recall
    tp = predictions.filter((F.col("prediction") == 1.0) & (F.col("label") == 1.0)).count()
    fp = predictions.filter((F.col("prediction") == 1.0) & (F.col("label") == 0.0)).count()
    fn = predictions.filter((F.col("prediction") == 0.0) & (F.col("label") == 1.0)).count()

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1_pos = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0

    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "f1_positive": f1_pos,
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
    }


def train_influencer_classifiers(
    local_mode: bool = True,
    save_models: bool = True,
) -> dict:
    spark = get_spark("InfluencerClassifierWorkflow", local_mode=local_mode)
    cfg = get_settings()
    inf_cfg = load_influencer_config()

    # 1. Load inputs
    video_path = str(local("silver", "youniverse_metadata"))
    domain_path = str(local("silver", "channel_domain_profiles"))
    spon_path = str(local("silver", "channel_sponsorship_metrics"))

    logger.info("Loading inputs from silver zone...")
    df_video = spark.read.parquet(video_path)
    df_domain = spark.read.parquet(domain_path)
    df_spon = spark.read.parquet(spon_path)

    # 2. Build channel features
    logger.info("Engineering channel features...")
    df_features = build_channel_features(df_video, df_domain, df_spon)
    df_features = df_features.cache()
    n_channels = df_features.count()

    # 3. Leakage Guard verification:
    # Feature columns MUST be disjoint from label_defining_columns
    feature_cols = inf_cfg["feature_columns"]
    label_def_cols = inf_cfg["label_definition"]["label_defining_columns"]
    overlap = set(feature_cols).intersection(set(label_def_cols))
    if overlap:
        raise ValueError(f"LEAKAGE VIOLATION: Feature columns overlap with label definition columns: {overlap}")

    # 4. Class Balance & Weighting
    n_pos = df_features.filter(F.col("label") == 1.0).count()
    n_neg = n_channels - n_pos
    baseline_pr_auc = n_pos / n_channels if n_channels > 0 else 0.0
    majority_acc = n_neg / n_channels if n_channels > 0 else 0.0

    logger.info(
        "Class balance: Total=%d, Positive=%d (%.1f%%), Negative=%d (%.1f%%)",
        n_channels, n_pos, (n_pos / n_channels) * 100, n_neg, (n_neg / n_channels) * 100
    )
    logger.info("Baseline PR-AUC: %.4f | Majority Accuracy: %.4f", baseline_pr_auc, majority_acc)

    # Calculate class weights: w_0 = N / (2 * N_0), w_1 = N / (2 * N_1)
    w0 = float(n_channels / (2.0 * n_neg))
    w1 = float(n_channels / (2.0 * n_pos))
    df_weighted = df_features.withColumn(
        "class_weight",
        F.when(F.col("label") == 1.0, F.lit(w1)).otherwise(F.lit(w0))
    )

    # 5. Split channels 70/15/15 deterministically
    seed = cfg["data"]["seed"]
    train_df, val_df, test_df = df_weighted.randomSplit([0.70, 0.15, 0.15], seed=seed)
    train_df = train_df.cache()
    val_df = val_df.cache()
    test_df = test_df.cache()

    n_train = train_df.count()
    n_val = val_df.count()
    n_test = test_df.count()
    logger.info("Channel split: train=%d, val=%d, test=%d", n_train, n_val, n_test)

    # 6. Feature pipeline: VectorAssembler -> StandardScaler
    assembler = VectorAssembler(inputCols=feature_cols, outputCol="raw_features")
    scaler = StandardScaler(inputCol="raw_features", outputCol="features", withStd=True, withMean=True)

    classifiers = [
        (
            "random_forest",
            RandomForestClassifier(featuresCol="features", labelCol="label", weightCol="class_weight", numTrees=30, seed=seed),
        ),
        (
            "gbt",
            GBTClassifier(featuresCol="features", labelCol="label", weightCol="class_weight", maxIter=20, seed=seed),
        ),
        (
            "logistic_regression",
            LogisticRegression(featuresCol="features", labelCol="label", weightCol="class_weight", maxIter=20),
        ),
    ]

    results = {}
    best_val_pr_auc = -1.0
    best_model_name = None
    best_fitted_pipeline = None

    for model_name, clf in classifiers:
        logger.info("--- Training %s ---", model_name)
        t0 = time.time()
        pipeline = Pipeline(stages=[assembler, scaler, clf])
        fitted = pipeline.fit(train_df)
        train_time = round(time.time() - t0, 2)

        # Predictions
        train_preds = fitted.transform(train_df)
        val_preds = fitted.transform(val_df)
        test_preds = fitted.transform(test_df)

        m_train = compute_binary_metrics(train_preds)
        m_val = compute_binary_metrics(val_preds)
        m_test = compute_binary_metrics(test_preds)

        logger.info(
            "%s: Val Acc=%.4f, Val F1=%.4f, Val PR-AUC=%.4f (Baseline=%.4f), Val ROC-AUC=%.4f",
            model_name, m_val["accuracy"], m_val["macro_f1"], m_val["pr_auc"], baseline_pr_auc, m_val["roc_auc"]
        )

        # Extract feature importance if available (RF / GBT)
        feat_importances = []
        if hasattr(fitted.stages[-1], "featureImportances"):
            importances = fitted.stages[-1].featureImportances.toArray()
            for col, imp in zip(feature_cols, importances):
                feat_importances.append({"feature": col, "importance": float(imp)})
            feat_importances.sort(key=lambda x: x["importance"], reverse=True)
            logger.info("Top features for %s: %s", model_name, feat_importances[:3])

        # Log model
        run_id = log_model_run(
            model_name=f"influencer_classifier_{model_name}",
            task="influencer_classification",
            algorithm=model_name,
            hyperparameters={"seed": seed, "features": feature_cols},
            dataset_version="dev_sample_50k_channels",
            split_seed=seed,
            n_train=n_train,
            n_val=n_val,
            n_test=n_test,
            class_distribution_train={"influencer": n_pos, "normal": n_neg},
            train_accuracy=m_train["accuracy"],
            val_accuracy=m_val["accuracy"],
            test_accuracy=m_test["accuracy"],
            train_macro_f1=m_train["macro_f1"],
            val_macro_f1=m_val["macro_f1"],
            test_macro_f1=m_test["macro_f1"],
            val_pr_auc=m_val["pr_auc"],
            val_roc_auc=m_val["roc_auc"],
            majority_baseline_accuracy=majority_acc,
            train_time_s=train_time,
            spark_master=spark.conf.get("spark.master", "local[*]"),
            feature_importance=feat_importances,
            notes=f"Option B label. Baseline PR-AUC={baseline_pr_auc:.4f}. Top feature={feat_importances[0]['feature'] if feat_importances else 'N/A'}",
        )

        results[model_name] = {
            "run_id": run_id,
            "train_acc": m_train["accuracy"],
            "val_acc": m_val["accuracy"],
            "test_acc": m_test["accuracy"],
            "val_pr_auc": m_val["pr_auc"],
            "val_roc_auc": m_val["roc_auc"],
            "val_f1": m_val["macro_f1"],
            "feature_importance": feat_importances,
        }

        if m_val["pr_auc"] > best_val_pr_auc:
            best_val_pr_auc = m_val["pr_auc"]
            best_model_name = model_name
            best_fitted_pipeline = fitted

    logger.info("Best model based on validation PR-AUC: %s (val_pr_auc=%.4f)", best_model_name, best_val_pr_auc)

    # 7. Persist best model
    if save_models and best_fitted_pipeline is not None:
        save_path = local("models", f"influencer_classifier_{best_model_name}")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        best_fitted_pipeline.write().overwrite().save(str(save_path))
        logger.info("Saved best model pipeline to: %s", save_path)

    # 8. Save gold channel profiles with predictions and size tiers
    all_preds = best_fitted_pipeline.transform(df_weighted)
    out_gold = str(local("gold", "channel_influencer_profiles"))
    all_preds.write.mode("overwrite").parquet(out_gold)
    logger.info("Saved gold channel influencer profiles to: %s (channels=%d)", out_gold, all_preds.count())

    spark.stop()
    return results


if __name__ == "__main__":
    train_influencer_classifiers()
