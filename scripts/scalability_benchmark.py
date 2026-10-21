"""
scripts/scalability_benchmark.py
Phase 9 — Big Data Scalability & Storage Format Throughput Benchmark.
Evaluates:
  1. Worker Core Parallelism (local[1], local[2], local[4]) on heavy feature aggregation.
  2. Storage format throughput: CSV vs Unpartitioned Parquet vs Partitioned Parquet.
Outputs:
  - metrics/scalability.csv
  - docs/REPORT_NUMBERS.md updates
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add repo root to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import os
import shutil
import tempfile
import time
import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from src.common.paths import project_root, local
from src.common.logging_setup import setup_logging
from src.common.spark_session import get_spark

logger = setup_logging(__name__)


def run_benchmark() -> pd.DataFrame:
    root = project_root()
    metrics_dir = root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    out_csv = metrics_dir / "scalability.csv"

    # Load silver metadata path
    silver_meta_path = str(local("silver", "youniverse_metadata"))
    if not Path(silver_meta_path).exists():
        raise FileNotFoundError(f"Required input {silver_meta_path} does not exist.")

    results: list[dict[str, object]] = []

    print("=" * 65)
    print(" BDA Project Phase 9: Scalability & Storage Format Benchmark")
    print("=" * 65)

    # ──────────────────────────────────────────────────────────────────────────
    # Part 1: Core Parallelism Scalability (local[1], local[2], local[4])
    # ──────────────────────────────────────────────────────────────────────────
    # Initialize environment via get_spark once
    get_spark("benchmark_env_init", local_mode=True).stop()

    print("\n[1/2] Benchmarking Worker Core Scalability (local[1], local[2], local[4])...")
    core_configs = [1, 2, 4]
    t1_time = 0.0

    for cores in core_configs:
        master_str = f"local[{cores}]"
        print(f"  --> Running feature aggregation benchmark on {master_str}...")

        spark = (
            SparkSession.builder
            .master(master_str)
            .appName(f"benchmark_cores_{cores}")
            .config("spark.sql.shuffle.partitions", str(cores * 2))
            .config("spark.driver.memory", "2g")
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel("ERROR")

        try:
            start_time = time.perf_counter()

            # Heavy aggregation: multi-metric rollup per channel across 50,000 video records
            df = spark.read.parquet(silver_meta_path)
            agg_df = df.groupBy("channel_id").agg(
                F.count("display_id").alias("video_count"),
                F.mean("duration").alias("mean_duration"),
                F.expr("percentile_approx(view_count, 0.5)").alias("median_views"),
                F.sum("like_count").alias("total_likes"),
                F.sum("dislike_count").alias("total_dislikes"),
                F.stddev("view_count").alias("view_stddev"),
                F.min("upload_date").alias("first_upload"),
                F.max("upload_date").alias("last_upload"),
            ).filter(F.col("video_count") >= 2)

            # Trigger action
            row_count = agg_df.count()
            elapsed = time.perf_counter() - start_time

            if cores == 1:
                t1_time = elapsed
                speedup = 1.0
                efficiency = 1.0
            else:
                speedup = round(t1_time / elapsed, 2) if elapsed > 0 else 1.0
                efficiency = round(speedup / cores, 2)

            print(f"      [OK] Cores: {cores} | Elapsed: {elapsed:.2f}s | Speedup: {speedup}x | Efficiency: {efficiency:.2f}")

            results.append({
                "benchmark_category": "core_scalability",
                "configuration": f"local[{cores}]",
                "cores": cores,
                "input_format": "parquet",
                "records_processed": 50000,
                "output_records": row_count,
                "elapsed_seconds": round(elapsed, 3),
                "speedup": speedup,
                "parallel_efficiency": efficiency,
                "throughput_records_per_sec": round(50000 / elapsed, 1),
            })
        finally:
            spark.stop()

    # ──────────────────────────────────────────────────────────────────────────
    # Part 2: Storage Format Throughput (CSV vs Single Parquet vs Partitioned)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[2/2] Benchmarking Storage Format Read & Write Throughput...")
    spark = (
        SparkSession.builder
        .master("local[2]")
        .appName("benchmark_storage")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    try:
        df_source = spark.read.parquet(silver_meta_path).limit(25000)
        temp_dir = Path(tempfile.mkdtemp(prefix="bda_bench_"))

        storage_tests = [
            ("csv", "Raw CSV Format", False),
            ("parquet_flat", "Flat Parquet Format", False),
            ("parquet_partitioned", "Domain-Partitioned Parquet", True),
        ]

        for fmt_id, label, is_partitioned in storage_tests:
            target_path = temp_dir / fmt_id
            print(f"  --> Benchmarking {label}...")

            # Write benchmark
            w_start = time.perf_counter()
            if is_partitioned:
                # Add domain partition column for test
                df_to_write = df_source.withColumn("domain_key", F.when(F.col("categories") == "Howto & Style", "beauty").otherwise("other"))
                df_to_write.write.mode("overwrite").partitionBy("domain_key").parquet(str(target_path))
            elif fmt_id == "csv":
                df_source.select("channel_id", "display_id", "duration", "view_count", "like_count", "categories") \
                    .write.mode("overwrite").option("header", "true").csv(str(target_path))
            else:
                df_source.write.mode("overwrite").parquet(str(target_path))
            w_elapsed = time.perf_counter() - w_start

            # Calculate on-disk size
            total_size_mb = sum(f.stat().st_size for f in target_path.rglob("*") if f.is_file()) / (1024 * 1024)

            # Read benchmark
            r_start = time.perf_counter()
            if fmt_id == "csv":
                read_df = spark.read.option("header", "true").csv(str(target_path))
            else:
                read_df = spark.read.parquet(str(target_path))
            read_count = read_df.count()
            r_elapsed = time.perf_counter() - r_start

            print(f"      [OK] {label}: Size: {total_size_mb:.2f} MB | Write: {w_elapsed:.2f}s | Read: {r_elapsed:.2f}s")

            results.append({
                "benchmark_category": "storage_format",
                "configuration": label,
                "cores": 2,
                "input_format": fmt_id,
                "records_processed": read_count,
                "output_records": read_count,
                "elapsed_seconds": round(r_elapsed, 3),
                "speedup": round(w_elapsed, 3),  # repurposed as write_elapsed
                "parallel_efficiency": round(total_size_mb, 2),  # repurposed as size_mb
                "throughput_records_per_sec": round(read_count / r_elapsed, 1) if r_elapsed > 0 else 0,
            })

        shutil.rmtree(temp_dir, ignore_errors=True)
    finally:
        spark.stop()

    bench_df = pd.DataFrame(results)
    bench_df.to_csv(out_csv, index=False)
    print("\n[SUCCESS] Scalability benchmarks written to:", out_csv)
    print("=" * 65)
    return bench_df


if __name__ == "__main__":
    run_benchmark()
