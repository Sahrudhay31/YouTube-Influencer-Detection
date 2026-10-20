"""
src/classification/domain_classifier.py
Phase 3 Domain Classifier training, evaluation, comparison, and logging.
Trains and compares Logistic Regression, Naive Bayes, and LinearSVC.
Logs all models to metrics/model_registry.csv and updates README.md.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from pyspark.ml import Pipeline, PipelineModel
from pyspark.ml.classification import LogisticRegression, NaiveBayes, LinearSVC
from pyspark.ml.evaluation import MulticlassClassificationEvaluator
from pyspark.ml.feature import Tokenizer, StopWordsRemover, CountVectorizer, IDF
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from src.classification.baselines import evaluate_majority_baseline, evaluate_keyword_baseline
from src.classification.channel_rollup import rollup_channel_domain
from src.classification.dataset_splitter import split_by_channel
from src.classification.text_cleaner import clean_video_text
from src.common.config import get_settings
from src.common.logging_setup import setup_logging
from src.common.metrics_logger import log_model_run
from src.common.paths import local
from src.common.spark_session import get_spark

logger = setup_logging(__name__)


def compute_metrics(
    predictions: DataFrame,
    label_col: str = "label",
    pred_col: str = "prediction",
) -> tuple[float, float, list[list[int]]]:
    """
    Computes accuracy, macro-F1, and confusion matrix [[TN, FP], [FN, TP]].
    """
    evaluator_acc = MulticlassClassificationEvaluator(
        labelCol=label_col, predictionCol=pred_col, metricName="accuracy"
    )
    evaluator_f1 = MulticlassClassificationEvaluator(
        labelCol=label_col, predictionCol=pred_col, metricName="f1"
    )

    acc = float(evaluator_acc.evaluate(predictions))
    macro_f1 = float(evaluator_f1.evaluate(predictions))

    # Confusion matrix:
    # row 0: label=0 -> col 0: pred=0 (TN), col 1: pred=1 (FP)
    # row 1: label=1 -> col 0: pred=0 (FN), col 1: pred=1 (TP)
    tn = predictions.filter((F.col(label_col) == 0.0) & (F.col(pred_col) == 0.0)).count()
    fp = predictions.filter((F.col(label_col) == 0.0) & (F.col(pred_col) == 1.0)).count()
    fn = predictions.filter((F.col(label_col) == 1.0) & (F.col(pred_col) == 0.0)).count()
    tp = predictions.filter((F.col(label_col) == 1.0) & (F.col(pred_col) == 1.0)).count()

    cm = [[int(tn), int(fp)], [int(fn), int(tp)]]
    return acc, macro_f1, cm


def train_and_evaluate(
    input_parquet: str | None = None,
    save_models: bool = True,
    local_mode: bool = True,
) -> dict:
    """
    Runs the complete Phase 3 Domain Classifier training and evaluation workflow.
    """
    spark = get_spark("DomainClassifierWorkflow", local_mode=local_mode)
    cfg = get_settings()

    if input_parquet is None:
        input_parquet = str(local("silver", "youniverse_metadata"))

    logger.info("Loading silver dataset from: %s", input_parquet)
    df_raw = spark.read.parquet(input_parquet)
    total_raw = df_raw.count()
    logger.info("Loaded %d rows.", total_raw)

    # 1. Assign weak domain label: 1.0 = beauty_personal_care, 0.0 = out_of_domain
    df_labeled = df_raw.withColumn(
        "label",
        F.when(F.col("categories") == "Howto & Style", F.lit(1.0)).otherwise(F.lit(0.0)),
    )

    # 2. Text cleaning
    df_clean = clean_video_text(df_labeled, output_col="text")

    # 3. Channel-based split (strictly by channel_id)
    train_df, val_df, test_df = split_by_channel(df_clean)
    train_df = train_df.cache()
    val_df = val_df.cache()
    test_df = test_df.cache()

    n_train = train_df.count()
    n_val = val_df.count()
    n_test = test_df.count()
    logger.info("Channel split counts: train=%d, val=%d, test=%d", n_train, n_val, n_test)

    # Class distribution in train
    pos_train = train_df.filter(F.col("label") == 1.0).count()
    neg_train = n_train - pos_train
    class_dist_train = {"beauty_personal_care": pos_train, "out_of_domain": neg_train}

    # 4. Baselines
    majority_acc = evaluate_majority_baseline(train_df, val_df)
    kw_metrics = evaluate_keyword_baseline(val_df)
    logger.info("Majority baseline accuracy on validation: %.4f", majority_acc)
    logger.info(
        "Keyword rule baseline on validation: acc=%.4f, f1=%.4f",
        kw_metrics["accuracy"],
        kw_metrics["macro_f1"],
    )

    # 5. Shared feature pipeline: Tokenizer -> StopWordsRemover -> CountVectorizer -> IDF
    tokenizer = Tokenizer(inputCol="text", outputCol="words")
    remover = StopWordsRemover(inputCol="words", outputCol="filtered_words")
    cv = CountVectorizer(inputCol="filtered_words", outputCol="raw_features", minDF=2.0)
    idf = IDF(inputCol="raw_features", outputCol="features")

    models_to_train = [
        ("logistic_regression", LogisticRegression(featuresCol="features", labelCol="label", maxIter=20, regParam=0.01)),
        ("naive_bayes", NaiveBayes(featuresCol="features", labelCol="label", smoothing=1.0)),
        ("linear_svc", LinearSVC(featuresCol="features", labelCol="label", maxIter=20, regParam=0.01)),
    ]

    results = {}
    best_val_f1 = -1.0
    best_model_name = None
    best_fitted_pipeline = None

    for model_name, classifier in models_to_train:
        logger.info("--- Training %s ---", model_name)
        t0 = time.time()
        pipeline = Pipeline(stages=[tokenizer, remover, cv, idf, classifier])
        fitted = pipeline.fit(train_df)
        train_time = round(time.time() - t0, 2)

        # Predictions
        train_preds = fitted.transform(train_df)
        val_preds = fitted.transform(val_df)
        test_preds = fitted.transform(test_df)

        train_acc, train_f1, train_cm = compute_metrics(train_preds)
        val_acc, val_f1, val_cm = compute_metrics(val_preds)
        test_acc, test_f1, test_cm = compute_metrics(test_preds)

        logger.info(
            "%s: train_acc=%.4f, val_acc=%.4f, test_acc=%.4f | val_f1=%.4f",
            model_name, train_acc, val_acc, test_acc, val_f1
        )

        overfit_gap = train_acc - val_acc

        # Model registry logging
        run_id = log_model_run(
            model_name=f"domain_classifier_{model_name}",
            task="domain_classification",
            algorithm=model_name,
            hyperparameters={"minDF": 2.0, "algorithm": model_name},
            dataset_version="dev_sample_50k",
            split_seed=cfg["data"]["seed"],
            n_train=n_train,
            n_val=n_val,
            n_test=n_test,
            class_distribution_train=class_dist_train,
            train_accuracy=train_acc,
            val_accuracy=val_acc,
            test_accuracy=test_acc,
            train_macro_f1=train_f1,
            val_macro_f1=val_f1,
            test_macro_f1=test_f1,
            majority_baseline_accuracy=majority_acc,
            train_time_s=train_time,
            spark_master=spark.conf.get("spark.master", "local[*]"),
            confusion_matrix=val_cm,
            notes=f"Weak-label agreement; keyword baseline acc={kw_metrics['accuracy']:.4f}",
        )

        results[model_name] = {
            "run_id": run_id,
            "train_acc": train_acc,
            "val_acc": val_acc,
            "test_acc": test_acc,
            "val_f1": val_f1,
            "train_time": train_time,
            "confusion_matrix": val_cm,
        }

        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            best_model_name = model_name
            best_fitted_pipeline = fitted

    logger.info("Best model based on validation F1: %s (val_f1=%.4f)", best_model_name, best_val_f1)

    # 6. Save the best model
    if save_models and best_fitted_pipeline is not None:
        save_path = local("models", f"domain_classifier_{best_model_name}")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        best_fitted_pipeline.write().overwrite().save(str(save_path))
        logger.info("Saved best model pipeline to: %s", save_path)

    # 7. Channel roll-up with the best model
    logger.info("Performing channel roll-up...")
    all_preds = best_fitted_pipeline.transform(df_clean)
    channel_profiles = rollup_channel_domain(all_preds)
    out_rollup = str(local("silver", "channel_domain_profiles"))
    channel_profiles.write.mode("overwrite").parquet(out_rollup)
    logger.info("Channel domain profiles saved to: %s (channels=%d)", out_rollup, channel_profiles.count())

    spark.stop()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Phase 3 Domain Classifiers")
    parser.add_argument("--parquet", type=str, default=None, help="Input silver Parquet path")
    args = parser.parse_args()
    train_and_evaluate(input_parquet=args.parquet)
