"""
src/sponsorship/pipeline.py
Phase 4 End-to-end Sponsorship Detection & Promo Lift pipeline.
Transforms silver video metadata into sponsorship feature tables and channel metrics.
"""
from __future__ import annotations

import argparse
import time
from pyspark.sql import functions as F

from src.common.logging_setup import setup_logging
from src.common.paths import local
from src.common.spark_session import get_spark
from src.sponsorship.detector import add_sponsorship_features
from src.sponsorship.promo_lift import compute_channel_promo_lift

logger = setup_logging(__name__)


def run_sponsorship_pipeline(
    input_parquet: str | None = None,
    local_mode: bool = True,
) -> dict:
    spark = get_spark("SponsorshipPipeline", local_mode=local_mode)

    if input_parquet is None:
        input_parquet = str(local("silver", "youniverse_metadata"))

    t0 = time.time()
    logger.info("Loading silver videos from: %s", input_parquet)
    df = spark.read.parquet(input_parquet)
    total_videos = df.count()
    logger.info("Total videos loaded: %d", total_videos)

    # 1. Video-level sponsorship feature extraction
    df_feat = add_sponsorship_features(df)
    df_feat = df_feat.cache()

    sponsored_count = df_feat.filter(F.col("is_sponsored") == True).count()
    sponsored_pct = (sponsored_count / total_videos) * 100
    logger.info(
        "Detected %d sponsored videos out of %d (%.2f%%)",
        sponsored_count, total_videos, sponsored_pct
    )

    # Save video-level features
    out_video_parquet = str(local("silver", "sponsorship_video_features"))
    df_feat.write.mode("overwrite").parquet(out_video_parquet)
    logger.info("Saved video sponsorship features to: %s", out_video_parquet)

    # 2. Channel-level metrics & Promo Lift
    channel_metrics = compute_channel_promo_lift(df_feat)
    channel_metrics = channel_metrics.cache()

    total_channels = channel_metrics.count()
    channels_with_lift = channel_metrics.filter(F.col("promo_lift").isNotNull()).count()
    logger.info(
        "Processed %d channels: %d channels have sufficient data for Promo Lift",
        total_channels, channels_with_lift
    )

    # Save channel-level metrics
    out_channel_parquet = str(local("silver", "channel_sponsorship_metrics"))
    channel_metrics.write.mode("overwrite").parquet(out_channel_parquet)
    logger.info("Saved channel sponsorship metrics to: %s", out_channel_parquet)

    # 3. Sample 20 flagged sponsored videos for review
    flagged_samples = (
        df_feat.filter(F.col("is_sponsored") == True)
        .select("display_id", "channel_id", "title", "has_disclosure", "has_affiliate_link", "has_promo_code", "has_utm")
        .limit(20)
        .collect()
    )

    duration = round(time.time() - t0, 2)
    logger.info("Sponsorship pipeline completed in %.1f seconds.", duration)

    summary = {
        "total_videos": total_videos,
        "sponsored_videos": sponsored_count,
        "sponsored_rate_pct": sponsored_pct,
        "total_channels": total_channels,
        "channels_with_lift": channels_with_lift,
        "duration_s": duration,
        "flagged_samples": [r.asDict() for r in flagged_samples],
    }

    spark.stop()
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Phase 4 Sponsorship Detection Pipeline")
    parser.add_argument("--parquet", type=str, default=None, help="Input silver Parquet path")
    args = parser.parse_args()
    run_sponsorship_pipeline(input_parquet=args.parquet)
