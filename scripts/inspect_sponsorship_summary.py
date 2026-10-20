"""
scripts/inspect_sponsorship_summary.py
Print 20 sample flagged videos and summary statistics of channel promo lift.
"""
from __future__ import annotations

from pyspark.sql import functions as F
from src.common.spark_session import get_spark


def inspect():
    spark = get_spark("InspectSponsorship", local_mode=True)
    df_feat = spark.read.parquet("data/silver/sponsorship_video_features")
    print("=== 20 SAMPLE FLAGGED SPONSORED VIDEOS ===")
    samples = df_feat.filter(F.col("is_sponsored") == True).select(
        "display_id", "channel_id", "title", "has_disclosure", "has_affiliate_link", "has_promo_code", "has_utm"
    ).limit(20).collect()

    for i, r in enumerate(samples, 1):
        flags = []
        if r["has_disclosure"]:
            flags.append("DISCLOSURE")
        if r["has_affiliate_link"]:
            flags.append("AFFILIATE")
        if r["has_promo_code"]:
            flags.append("PROMO_CODE")
        if r["has_utm"]:
            flags.append("UTM")
        flags_str = "+".join(flags)
        title_str = (r["title"] or "")[:70]
        print(f"{i:2d}. [{flags_str}] ({r['display_id']}) {title_str}")

    print("\n=== CHANNEL PROMO LIFT SUMMARY ===")
    df_ch = spark.read.parquet("data/silver/channel_sponsorship_metrics")
    df_ch.filter(F.col("promo_lift").isNotNull()).select(
        F.count("promo_lift").alias("channels_with_lift"),
        F.round(F.avg("promo_lift"), 3).alias("mean_lift"),
        F.round(F.min("promo_lift"), 3).alias("min_lift"),
        F.round(F.max("promo_lift"), 3).alias("max_lift"),
        F.round(F.expr("percentile_approx(promo_lift, 0.5)"), 3).alias("median_lift")
    ).show()

    spark.stop()


if __name__ == "__main__":
    inspect()
