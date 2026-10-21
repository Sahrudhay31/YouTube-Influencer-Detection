"""
tests/spark/test_domain_classifier.py
Phase 3 Domain Classifier smoke tests:
- T-C1: Pipeline fits on fixture and outputs probabilities summing to ~1.
- T-C2: Channel-based split ensures no channel appears in two splits.
- T-C3: Classifier beats the majority-class baseline on validation.
- T-C4: Shuffled-label run drops to near chance.
- T-C5: Saved model reloads and gives identical predictions on 10 rows.
- T-C6: Roll-up purity is bounded in [0, 1].
"""
from __future__ import annotations

import atexit
import json
import tempfile
from pathlib import Path

import pytest
from pyspark.ml import Pipeline, PipelineModel
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.feature import Tokenizer, StopWordsRemover, CountVectorizer, IDF
from pyspark.sql import DataFrame, SparkSession, functions as F

from src.classification.baselines import evaluate_majority_baseline
from src.classification.channel_rollup import rollup_channel_domain
from src.classification.dataset_splitter import split_by_channel
from src.classification.text_cleaner import clean_video_text
from src.common.paths import local
from src.common.spark_session import get_spark


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
    s = get_spark(app_name="bda-phase3-tests", local_mode=True)
    yield s


def test_tc1_probabilities_sum_to_one(spark):
    """T-C1: Pipeline fits on a 20-row fixture and outputs probabilities summing to ~1.0."""
    data = []
    # 10 beauty, 10 non-beauty
    for i in range(10):
        data.append((f"ch_{i}", f"makeup beauty skincare foundation tutorial {i}", 1.0))
    for i in range(10, 20):
        data.append((f"ch_{i}", f"gaming minecraft walkthrough speedrun episode {i}", 0.0))

    df = _safe_df(spark, data, ["channel_id", "text", "label"])

    tokenizer = Tokenizer(inputCol="text", outputCol="words")
    remover = StopWordsRemover(inputCol="words", outputCol="filtered_words")
    cv = CountVectorizer(inputCol="filtered_words", outputCol="raw_features", minDF=1.0)
    idf = IDF(inputCol="raw_features", outputCol="features")
    lr = LogisticRegression(featuresCol="features", labelCol="label", maxIter=5)

    pipeline = Pipeline(stages=[tokenizer, remover, cv, idf, lr])
    model = pipeline.fit(df)

    preds = model.transform(df)
    assert preds.count() == 20

    for row in preds.collect():
        prob = row["probability"].toArray()
        prob_sum = float(sum(prob))
        assert abs(prob_sum - 1.0) < 1e-4, f"Probabilities do not sum to 1.0: {prob_sum}"


def test_tc2_no_channel_in_multiple_splits(spark):
    """T-C2: Channel-based split ensures no channel appears in multiple splits."""
    data = []
    for ch_idx in range(50):
        for vid_idx in range(5):
            data.append((f"channel_{ch_idx}", f"video_{ch_idx}_{vid_idx}", 1.0 if ch_idx % 2 == 0 else 0.0))

    df = _safe_df(spark, data, ["channel_id", "title", "label"])
    train_df, val_df, test_df = split_by_channel(df, ratios=[0.70, 0.15, 0.15], seed=42)

    train_channels = set(r["channel_id"] for r in train_df.select("channel_id").distinct().collect())
    val_channels = set(r["channel_id"] for r in val_df.select("channel_id").distinct().collect())
    test_channels = set(r["channel_id"] for r in test_df.select("channel_id").distinct().collect())

    # Assert mutual disjointness
    assert train_channels.isdisjoint(val_channels), f"Overlap train-val: {train_channels & val_channels}"
    assert train_channels.isdisjoint(test_channels), f"Overlap train-test: {train_channels & test_channels}"
    assert val_channels.isdisjoint(test_channels), f"Overlap val-test: {val_channels & test_channels}"
    assert len(train_channels) + len(val_channels) + len(test_channels) == 50


def test_tc3_model_beats_majority_baseline(spark):
    """T-C3: Trained classifier validation accuracy beats majority-class baseline."""
    # Use synthetic fixture with clean separation
    train_data = []
    for i in range(40):
        train_data.append((f"ch_pos_{i}", f"skincare routine makeup review blush {i}", 1.0))
    for i in range(60):
        train_data.append((f"ch_neg_{i}", f"fortnite gaming highlights montage kill {i}", 0.0))

    val_data = []
    for i in range(40, 50):
        val_data.append((f"ch_pos_{i}", f"skincare cream moisturizer foundation {i}", 1.0))
    for i in range(60, 75):
        val_data.append((f"ch_neg_{i}", f"fortnite gameplay battle royale {i}", 0.0))

    train_df = _safe_df(spark, train_data, ["channel_id", "text", "label"])
    val_df = _safe_df(spark, val_data, ["channel_id", "text", "label"])

    majority_baseline = evaluate_majority_baseline(train_df, val_df)

    tokenizer = Tokenizer(inputCol="text", outputCol="words")
    remover = StopWordsRemover(inputCol="words", outputCol="filtered_words")
    cv = CountVectorizer(inputCol="filtered_words", outputCol="raw_features", minDF=1.0)
    idf = IDF(inputCol="raw_features", outputCol="features")
    lr = LogisticRegression(featuresCol="features", labelCol="label", maxIter=10)

    model = Pipeline(stages=[tokenizer, remover, cv, idf, lr]).fit(train_df)
    preds = model.transform(val_df)

    correct = preds.filter(F.col("prediction") == F.col("label")).count()
    model_acc = correct / preds.count()

    assert model_acc > majority_baseline, (
        f"Model accuracy ({model_acc:.4f}) failed to beat majority baseline ({majority_baseline:.4f})"
    )


def test_tc4_shuffled_label_drops_to_near_chance(spark):
    """T-C4: Shuffling labels destroys predictive signal and drops held-out test accuracy to near chance."""
    words_pool = ["beauty", "skincare", "tutorial", "makeup", "review", "routine", "gaming", "vlog"]
    data = []
    for i in range(120):
        # Sample text from shared vocabulary without unique row IDs
        text_sample = " ".join([words_pool[(i + j) % len(words_pool)] for j in range(4)])
        data.append((f"ch_{i}", text_sample, 1.0 if i < 60 else 0.0))

    df = _safe_df(spark, data, ["channel_id", "text", "label"])
    # Randomly shuffle labels across the dataset
    df_shuffled = df.withColumn("label", F.when(F.rand(seed=99) > 0.5, 1.0).otherwise(0.0))

    train_df, test_df = df_shuffled.randomSplit([0.7, 0.3], seed=42)

    tokenizer = Tokenizer(inputCol="text", outputCol="words")
    remover = StopWordsRemover(inputCol="words", outputCol="filtered_words")
    cv = CountVectorizer(inputCol="filtered_words", outputCol="raw_features", minDF=2.0)
    idf = IDF(inputCol="raw_features", outputCol="features")
    lr = LogisticRegression(featuresCol="features", labelCol="label", maxIter=5, regParam=0.1)

    model = Pipeline(stages=[tokenizer, remover, cv, idf, lr]).fit(train_df)
    preds = model.transform(test_df)

    correct = preds.filter(F.col("prediction") == F.col("label")).count()
    acc = correct / preds.count()

    # Held-out evaluation on shuffled labels must fall near chance (0.30 - 0.70)
    assert 0.30 <= acc <= 0.70, f"Shuffled test accuracy unexpectedly high: {acc:.4f}"


def test_tc5_saved_model_reloads_with_identical_predictions(spark, tmp_path):
    """T-C5: Saved model reloads from disk and produces identical predictions."""
    data = [(f"ch_{i}", f"text sample {i}", 1.0 if i % 2 == 0 else 0.0) for i in range(10)]
    df = _safe_df(spark, data, ["channel_id", "text", "label"])

    tokenizer = Tokenizer(inputCol="text", outputCol="words")
    cv = CountVectorizer(inputCol="words", outputCol="features", minDF=1.0)
    lr = LogisticRegression(featuresCol="features", labelCol="label", maxIter=5)

    pipe = Pipeline(stages=[tokenizer, cv, lr])
    model = pipe.fit(df)

    preds_original = model.transform(df).select("prediction").collect()

    save_dir = str(tmp_path / "test_model_reload")
    model.write().overwrite().save(save_dir)

    reloaded_model = PipelineModel.load(save_dir)
    preds_reloaded = reloaded_model.transform(df).select("prediction").collect()

    assert [r["prediction"] for r in preds_original] == [r["prediction"] for r in preds_reloaded]


def test_tc6_rollup_purity_bounded_zero_to_one(spark):
    """T-C6: Channel domain purity is mathematically bounded in [0.0, 1.0]."""
    preds_data = [
        ("ch1", 1.0),
        ("ch1", 1.0),
        ("ch1", 0.0),
        ("ch2", 0.0),
        ("ch2", 0.0),
        ("ch3", 1.0),
    ]
    df = _safe_df(spark, preds_data, ["channel_id", "prediction"])
    rollup_df = rollup_channel_domain(df)

    for row in rollup_df.collect():
        purity = row["domain_purity"]
        share = row["in_domain_share"]
        assert 0.0 <= purity <= 1.0, f"Domain purity out of bounds: {purity}"
        assert 0.0 <= share <= 1.0, f"In-domain share out of bounds: {share}"

    # Specifically for ch1 (2 in-domain, 1 out-of-domain out of 3 total)
    ch1_row = rollup_df.filter(F.col("channel_id") == "ch1").first()
    assert ch1_row["video_count"] == 3
    assert ch1_row["primary_domain"] == 1.0
    assert abs(ch1_row["domain_purity"] - (2 / 3)) < 1e-4
