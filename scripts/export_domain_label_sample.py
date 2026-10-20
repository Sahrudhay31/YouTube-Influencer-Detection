"""
scripts/export_domain_label_sample.py
Export a stratified 500-video sample to labels/domain_to_label.csv
for human verification and ground truth correction per Phase 3 tasks.
"""
from __future__ import annotations

import csv
from pathlib import Path
from pyspark.sql import functions as F
from src.common.spark_session import get_spark
from src.common.paths import local


def export_sample(output_csv: str = "labels/domain_to_label.csv", n_samples: int = 500):
    spark = get_spark("ExportDomainSample", local_mode=True)
    parquet_path = str(local("silver", "youniverse_metadata"))
    df = spark.read.parquet(parquet_path)

    # In-domain candidate (Howto & Style): assign weak_label = 1
    # Out-of-domain: assign weak_label = 0
    df_labeled = df.withColumn(
        "weak_label",
        F.when(F.col("categories") == "Howto & Style", F.lit("beauty_personal_care")).otherwise(F.lit("out_of_domain"))
    )

    in_domain = df_labeled.filter(F.col("weak_label") == "beauty_personal_care")
    out_domain = df_labeled.filter(F.col("weak_label") == "out_of_domain")

    n_pos = n_samples // 2
    n_neg = n_samples - n_pos

    sample_pos = in_domain.limit(n_pos)
    sample_neg = out_domain.limit(n_neg)

    combined = sample_pos.unionByName(sample_neg).orderBy(F.rand(seed=42))

    rows = combined.select("display_id", "channel_id", "categories", "title", "weak_label").collect()
    spark.stop()

    out_file = Path(output_csv)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["display_id", "channel_id", "category", "title", "weak_label", "human_label", "notes"])
        for r in rows:
            # Clean title of newlines for clean CSV
            clean_title = (r["title"] or "").replace("\r", " ").replace("\n", " ").strip()
            writer.writerow([r["display_id"], r["channel_id"], r["categories"], clean_title, r["weak_label"], "", ""])

    print(f"Exported {len(rows)} rows to {output_csv}")


if __name__ == "__main__":
    export_sample()
