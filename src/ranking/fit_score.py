"""
src/ranking/fit_score.py
Phase 7 — Domain-Aware Fit Score (TF-IDF Cosine Similarity).

Computes the semantic fit score in [0, 1] between a product brief and each
YouTube channel's text profile (titles + tags + descriptions) using the
Spark ML TF-IDF pipeline (Tokenizer -> StopWordsRemover -> CountVectorizer/HashingTF -> IDF).

Cosine similarity is computed strictly in [0, 1].
"""
from __future__ import annotations

import logging
from pathlib import Path

from pyspark.ml import Pipeline, PipelineModel
from pyspark.ml.feature import HashingTF, IDF, Normalizer, StopWordsRemover, Tokenizer
from pyspark.ml.functions import vector_to_array
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from src.classification.text_cleaner import clean_video_text
from src.common.logging_setup import setup_logging
from src.common.paths import local

logger = setup_logging(__name__)


def build_channel_text_profiles(
    spark: SparkSession,
    videos_df: DataFrame | None = None,
) -> DataFrame:
    """
    Aggregate cleaned text (title + tags + description) for all videos per channel.

    Parameters
    ----------
    spark : SparkSession
    videos_df : DataFrame, optional
        If None, reads from data/silver/sponsorship_video_features.

    Returns
    -------
    DataFrame with columns: `channel_id`, `text`.
    """
    if videos_df is None:
        video_path = str(local("silver", "sponsorship_video_features"))
        logger.info("[FitScore] Loading videos from: %s", video_path)
        videos_df = spark.read.parquet(video_path)

    # Clean text (lower, strip urls, emojis, non-alphanumeric noise)
    cleaned = clean_video_text(videos_df, output_col="video_text")

    # Aggregate all videos per channel into a single text document
    channel_texts = cleaned.groupBy("channel_id").agg(
        F.concat_ws(" ", F.collect_list("video_text")).alias("text")
    )
    return channel_texts


class ChannelFitScorer:
    """
    Fits a Spark ML TF-IDF model on channel text profiles and evaluates
    cosine similarity between product briefs and channel profiles.
    """

    def __init__(self, num_features: int = 4096):
        self.num_features = num_features
        self.pipeline_model: PipelineModel | None = None
        self.channel_norm_df: DataFrame | None = None

    def fit(self, channel_texts_df: DataFrame) -> ChannelFitScorer:
        """Fit the TF-IDF pipeline and precompute L2-normalized channel vectors."""
        tok = Tokenizer(inputCol="text", outputCol="words")
        sw = StopWordsRemover(inputCol="words", outputCol="filtered")
        tf = HashingTF(inputCol="filtered", outputCol="raw_features", numFeatures=self.num_features)
        idf = IDF(inputCol="raw_features", outputCol="tfidf_features")
        norm = Normalizer(inputCol="tfidf_features", outputCol="features", p=2.0)

        pipeline = Pipeline(stages=[tok, sw, tf, idf, norm])
        logger.info("[FitScore] Fitting TF-IDF pipeline on channel profiles...")
        self.pipeline_model = pipeline.fit(channel_texts_df)

        transformed = self.pipeline_model.transform(channel_texts_df)
        self.channel_norm_df = transformed.select("channel_id", "features")
        return self

    def compute_fit_scores(
        self,
        spark: SparkSession,
        product_brief: str,
        channel_norm_df: DataFrame | None = None,
    ) -> DataFrame:
        """
        Compute cosine similarity between product brief and each channel.

        Parameters
        ----------
        spark : SparkSession
        product_brief : str
            Free-text description of product / campaign.
        channel_norm_df : DataFrame, optional
            Precomputed normalized channel vectors. If None, uses fitted state.

        Returns
        -------
        DataFrame with columns `channel_id`, `fit_score` in [0, 1].
        """
        if self.pipeline_model is None:
            raise ValueError("ChannelFitScorer must be fitted before computing fit scores.")

        target_df = channel_norm_df if channel_norm_df is not None else self.channel_norm_df
        if target_df is None:
            raise ValueError("No channel vector DataFrame provided or cached.")

        # If product brief is empty, return 0.0 for all channels
        cleaned_brief = product_brief.strip().lower()
        if not cleaned_brief:
            return target_df.select("channel_id", F.lit(0.0).alias("fit_score"))

        # Transform product brief to unit TF-IDF vector
        import json, tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write(json.dumps({"text": cleaned_brief}) + "\n")
            q_path = f.name

        try:
            q_df = spark.read.json(q_path)
            q_trans = self.pipeline_model.transform(q_df)
            q_vec = q_trans.select("features").collect()[0]["features"]
        finally:
            try:
                Path(q_path).unlink(missing_ok=True)
            except OSError:
                pass

        q_arr = q_vec.toArray()
        active_indices = [int(i) for i, v in enumerate(q_arr) if abs(v) > 1e-6]

        if not active_indices:
            return target_df.select("channel_id", F.lit(0.0).alias("fit_score"))

        # Cosine similarity for unit vectors: dot product = sum_i(q[i] * c[i])
        channel_arr = target_df.withColumn("v_arr", vector_to_array(F.col("features")))

        dot_expr = F.lit(0.0)
        for idx in active_indices:
            weight = float(q_arr[idx])
            dot_expr = dot_expr + (F.col("v_arr")[idx] * weight)

        # Clip strictly to [0.0, 1.0]
        scored = channel_arr.withColumn("raw_sim", dot_expr)
        result = scored.withColumn(
            "fit_score",
            F.when(F.col("raw_sim") < 0.0, 0.0)
            .when(F.col("raw_sim") > 1.0, 1.0)
            .otherwise(F.col("raw_sim"))
            .cast("double"),
        ).select("channel_id", "fit_score")

        return result
