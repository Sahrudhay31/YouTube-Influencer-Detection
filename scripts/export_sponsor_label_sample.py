"""
scripts/export_sponsor_label_sample.py
Export a stratified ~300-video sample to labels/sponsor_to_label.csv
for human ground-truth validation of sponsorship detection rules.
"""
from __future__ import annotations

import csv
from pathlib import Path
from pyspark.sql import functions as F
from src.common.paths import local
from src.common.spark_session import get_spark
from src.sponsorship.detector import add_sponsorship_features


def export_sponsor_sample(output_csv: str = "labels/sponsor_to_label.csv", n_samples: int = 300):
    spark = get_spark("ExportSponsorSample", local_mode=True)
    parquet_path = str(local("silver", "youniverse_metadata"))
    df = spark.read.parquet(parquet_path)

    # Add sponsorship features
    df_feat = add_sponsorship_features(df)

    # Stratified: ~150 rule-positive and ~150 rule-negative
    pos = df_feat.filter(F.col("is_sponsored") == True)
    neg = df_feat.filter(F.col("is_sponsored") == False)

    n_pos = n_samples // 2
    n_neg = n_samples - n_pos

    sample_pos = pos.limit(n_pos)
    sample_neg = neg.limit(n_neg)

    combined = sample_pos.unionByName(sample_neg).orderBy(F.rand(seed=42))

    rows = combined.select(
        "display_id", "channel_id", "title", "description",
        "is_sponsored", "has_disclosure", "has_affiliate_link", "has_promo_code", "has_utm"
    ).collect()
    spark.stop()

    out_file = Path(output_csv)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "display_id", "channel_id", "title", "description_snippet",
            "rule_is_sponsored", "has_disclosure", "has_affiliate_link", "has_promo_code", "has_utm",
            "human_is_sponsored", "notes"
        ])
        for r in rows:
            clean_title = (r["title"] or "").replace("\r", " ").replace("\n", " ").strip()
            desc_snippet = (r["description"] or "")[:200].replace("\r", " ").replace("\n", " ").strip()
            writer.writerow([
                r["display_id"], r["channel_id"], clean_title, desc_snippet,
                r["is_sponsored"], r["has_disclosure"], r["has_affiliate_link"], r["has_promo_code"], r["has_utm"],
                "", ""
            ])

    print(f"Exported {len(rows)} rows to {output_csv}")


if __name__ == "__main__":
    export_sponsor_sample()
