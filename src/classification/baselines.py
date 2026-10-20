"""
src/classification/baselines.py
Baseline classifiers for Phase 3 domain detection:
1. MajorityClassBaseline: Predicts the most frequent class in the training split.
2. KeywordRuleBaseline: Predicts in-domain if text contains domain keywords from taxonomy config.
"""
from __future__ import annotations

import yaml
from pathlib import Path
from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def evaluate_majority_baseline(
    train_df: DataFrame,
    eval_df: DataFrame,
    label_col: str = "label",
) -> float:
    """
    Computes accuracy of predicting the training set's majority class on eval_df.
    """
    majority_row = (
        train_df.groupBy(label_col)
        .count()
        .orderBy(F.desc("count"))
        .first()
    )
    if majority_row is None:
        return 0.0
    majority_class = majority_row[label_col]

    total = eval_df.count()
    if total == 0:
        return 0.0

    correct = eval_df.filter(F.col(label_col) == majority_class).count()
    return float(correct / total)


def evaluate_keyword_baseline(
    eval_df: DataFrame,
    text_col: str = "text",
    label_col: str = "label",
    config_path: str = "config/domains/beauty_personal_care.yaml",
) -> dict[str, float]:
    """
    Rule-based classifier using domain keywords.
    Predicts 1.0 (in-domain) if any keyword is present, else 0.0.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    keywords = [item["term"].lower() for item in cfg.get("keywords", {}).get("core", [])]
    if not keywords:
        keywords = ["skincare", "makeup", "haircare", "beauty", "cosmetics"]

    # Build regex pattern for word boundaries or substring match
    pattern = "|".join([rf"\b{kw}\b" for kw in keywords])

    df_preds = eval_df.withColumn(
        "pred",
        F.when(F.col(text_col).rlike(pattern), F.lit(1.0)).otherwise(F.lit(0.0)),
    )

    total = df_preds.count()
    if total == 0:
        return {"accuracy": 0.0, "macro_f1": 0.0}

    correct = df_preds.filter(F.col("pred") == F.col(label_col)).count()
    acc = float(correct / total)

    # Compute binary confusion matrix components
    tp = df_preds.filter((F.col("pred") == 1.0) & (F.col(label_col) == 1.0)).count()
    fp = df_preds.filter((F.col("pred") == 1.0) & (F.col(label_col) == 0.0)).count()
    fn = df_preds.filter((F.col("pred") == 0.0) & (F.col(label_col) == 1.0)).count()
    tn = df_preds.filter((F.col("pred") == 0.0) & (F.col(label_col) == 0.0)).count()

    prec_1 = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec_1 = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1_1 = 2 * prec_1 * rec_1 / (prec_1 + rec_1) if (prec_1 + rec_1) > 0 else 0.0

    prec_0 = tn / (tn + fn) if (tn + fn) > 0 else 0.0
    rec_0 = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    f1_0 = 2 * prec_0 * rec_0 / (prec_0 + rec_0) if (prec_0 + rec_0) > 0 else 0.0

    macro_f1 = (f1_1 + f1_0) / 2.0

    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "precision_in_domain": prec_1,
        "recall_in_domain": rec_1,
        "f1_in_domain": f1_1,
    }
