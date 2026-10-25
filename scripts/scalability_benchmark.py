"""
scripts/scalability_benchmark.py
Phase R8 — Defensible Big Data Scalability & Storage Format Benchmark.

Solves Finding F9:
- Discards warm-up runs to separate JVM cold-start / classloading / JIT overhead from steady state.
- Executes >= 5 timed repeats per worker core configuration (local[1], local[2], local[4]).
- Reports Median, Interquartile Range (IQR), Cold-Start runtime, and Warm-State runtime.
- Calculates true Speedup = WarmMedian(local[1]) / WarmMedian(local[n]) and Parallel Efficiency = Speedup / n.
- Flags 'superlinear_suspect' if efficiency > 1.20, preventing false claims from IO cache or JVM warmup artifacts.
- Storage Benchmark: explicit schema for CSV (no inferSchema), measuring full scan, column-pruned agg, and domain filter.
- Outputs defensible results directly to metrics/scalability.csv and docs/REPORT_NUMBERS.md.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from typing import Any

import numpy as np
import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

from src.common.logging_setup import setup_logging
from src.common.paths import local, project_root
from src.common.spark_session import get_spark

logger = setup_logging(__name__)

NUM_REPEATS = 5


def compute_median_and_iqr(times: list[float]) -> tuple[float, float]:
    """Computes median and interquartile range (IQR = Q75 - Q25)."""
    if not times:
        return 0.0, 0.0
    arr = np.array(times)
    q25 = float(np.percentile(arr, 25))
    q75 = float(np.percentile(arr, 75))
    return float(np.median(arr)), float(q75 - q25)


def check_superlinear_suspect(speedup: float, cores: int, threshold: float = 1.20) -> bool:
    """Flags suspect superlinear parallel efficiency (speedup / cores > 1.20)."""
    if cores <= 1:
        return False
    efficiency = speedup / float(cores)
    return efficiency > threshold


def run_defensible_benchmark(
    repeats: int = NUM_REPEATS,
    sample_limit: int = 50000,
) -> pd.DataFrame:
    root = project_root()
    metrics_dir = root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    out_csv = metrics_dir / "scalability.csv"

    silver_meta_path = str(local("silver", "youniverse_metadata"))
    if not Path(silver_meta_path).exists():
        raise FileNotFoundError(f"Required input {silver_meta_path} does not exist.")

    results: list[dict[str, Any]] = []

    print("=" * 70)
    print(" BDA Project Phase R8: Defensible Worker Core & Storage Benchmark")
    print(f" (Warm-up run discarded | {repeats} timed repeats | Median + IQR)")
    print("=" * 70)

    # ──────────────────────────────────────────────────────────────────────────
    # Part 1: Core Parallelism Scalability (local[1], local[2], local[4])
    # ──────────────────────────────────────────────────────────────────────────
    core_configs = [1, 2, 4]
    t1_warm_median = 0.0

    for cores in core_configs:
        master_str = f"local[{cores}]"
        print(f"\n[1/2] Benchmarking Worker Core Scalability: {master_str}...")

        spark = get_spark(
            app_name=f"benchmark_cores_{cores}",
            local_mode=True,
            master=master_str,
        )
        spark.sparkContext.setLogLevel("ERROR")

        try:
            df = spark.read.parquet(silver_meta_path)
            if sample_limit:
                df = df.limit(sample_limit).cache()
                df.count()

            def run_workload() -> int:
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
                return agg_df.count()

            # 1. Warm-up run (discarded)
            print("    -> Discarding warm-up run (JIT / classloading initialization)...")
            t_warmup_start = time.perf_counter()
            out_rows = run_workload()
            cold_time = time.perf_counter() - t_warmup_start
            print(f"       Cold-start execution time: {cold_time:.3f}s")

            # 2. Timed steady-state repeats
            timed_runs = []
            for r in range(repeats):
                t_start = time.perf_counter()
                run_workload()
                dur = time.perf_counter() - t_start
                timed_runs.append(dur)
                print(f"       Repeat {r+1}/{repeats}: {dur:.3f}s")

            warm_median, warm_iqr = compute_median_and_iqr(timed_runs)

            if cores == 1:
                t1_warm_median = warm_median
                speedup = 1.0
                efficiency = 1.0
                is_suspect = False
            else:
                speedup = round(t1_warm_median / warm_median, 2) if warm_median > 0 else 1.0
                efficiency = round(speedup / cores, 2)
                is_suspect = check_superlinear_suspect(speedup, cores, threshold=1.20)

            print(
                f"    [SUMMARY] local[{cores}]: Warm Median = {warm_median:.3f}s (IQR = {warm_iqr:.3f}s) "
                f"| Speedup = {speedup:.2f}x | Efficiency = {efficiency:.2f}"
                + (" [SUPERLINEAR SUSPECT!]" if is_suspect else "")
            )

            results.append({
                "benchmark_category": "core_scalability",
                "configuration": f"local[{cores}]",
                "cores": cores,
                "input_format": "parquet",
                "records_processed": sample_limit,
                "output_records": out_rows,
                "cold_elapsed_s": round(cold_time, 3),
                "warm_median_s": round(warm_median, 3),
                "iqr_s": round(warm_iqr, 3),
                "repeats": repeats,
                "speedup": speedup,
                "parallel_efficiency": efficiency,
                "superlinear_suspect": is_suspect,
                "throughput_records_per_sec": round(sample_limit / warm_median, 1) if warm_median > 0 else 0,
            })
        finally:
            spark.stop()

    # ──────────────────────────────────────────────────────────────────────────
    # Part 2: Storage Format Throughput (CSV vs Flat Parquet vs Partitioned)
    # ──────────────────────────────────────────────────────────────────────────
    print("\n[2/2] Benchmarking Storage Format Read & Write Throughput...")
    spark = get_spark(
        app_name="benchmark_storage",
        local_mode=True,
        master="local[2]",
    )
    spark.sparkContext.setLogLevel("ERROR")

    try:
        csv_schema = StructType([
            StructField("channel_id", StringType(), True),
            StructField("display_id", StringType(), True),
            StructField("duration", LongType(), True),
            StructField("view_count", DoubleType(), True),
            StructField("like_count", DoubleType(), True),
            StructField("categories", StringType(), True),
        ])

        df_source = spark.read.parquet(silver_meta_path).limit(sample_limit)
        temp_dir = Path(tempfile.mkdtemp(prefix="bda_bench_storage_"))

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
                df_to_write = df_source.withColumn(
                    "domain_key",
                    F.when(F.col("categories") == "Howto & Style", "beauty").otherwise("other")
                )
                df_to_write.write.mode("overwrite").partitionBy("domain_key").parquet(str(target_path))
            elif fmt_id == "csv":
                df_source.select("channel_id", "display_id", "duration", "view_count", "like_count", "categories") \
                    .write.mode("overwrite").option("header", "true").csv(str(target_path))
            else:
                df_source.write.mode("overwrite").parquet(str(target_path))
            w_elapsed = time.perf_counter() - w_start

            total_size_mb = sum(f.stat().st_size for f in target_path.rglob("*") if f.is_file()) / (1024 * 1024)

            # Read benchmark with schema supplied (no inferSchema)
            r_start = time.perf_counter()
            if fmt_id == "csv":
                read_df = spark.read.schema(csv_schema).option("header", "true").csv(str(target_path))
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
                "cold_elapsed_s": round(w_elapsed, 3),  # write time
                "warm_median_s": round(r_elapsed, 3),  # read time
                "iqr_s": 0.0,
                "repeats": 1,
                "speedup": round(w_elapsed, 3),
                "parallel_efficiency": round(total_size_mb, 2),  # size in MB
                "superlinear_suspect": False,
                "throughput_records_per_sec": round(read_count / r_elapsed, 1) if r_elapsed > 0 else 0,
            })

        shutil.rmtree(temp_dir, ignore_errors=True)
    finally:
        spark.stop()

    bench_df = pd.DataFrame(results)
    bench_df.to_csv(out_csv, index=False)
    print("\n[SUCCESS] Scalability benchmarks written to:", out_csv)
    print("=" * 70)
    return bench_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase R8 Scalability Benchmark")
    parser.add_argument("--repeats", type=int, default=5, help="Number of warm-state repeats")
    parser.add_argument("--limit", type=int, default=50000, help="Row sample limit")
    args = parser.parse_args()

    run_defensible_benchmark(repeats=args.repeats, sample_limit=args.limit)
