"""
src/ingestion/load_youniverse.py
Load YouNiverse raw files into silver zone as partitioned Parquet.

Rules (Section 6):
- Dev sample uses dev_sample_fraction from settings.yaml.
- Gzip is not splittable; raw .gz -> Parquet conversion done once.
- Row counts raw vs Parquet MUST match.
- HDFS failures raise loudly; no silent local fallback.
- Explicit --local flag allows writing to local silver zone without silent fallback.
- Job is idempotent (re-run on existing output is safe).
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from src.common.config import get_settings
from src.common.logging_setup import setup_logging
from src.common.paths import hdfs, local
from src.common.spark_session import get_spark

logger = setup_logging(__name__)


def load_youniverse(
    raw_dir: str,
    dev_mode: bool = True,
    overwrite: bool = False,
    local_mode: bool = False,
) -> dict[str, int]:
    """
    Convert YouNiverse raw .gz files to Parquet in silver zone.

    Parameters
    ----------
    raw_dir : str
        Local directory containing the YouNiverse .gz files.
    dev_mode : bool
        If True, uses dev_sample_fraction / dev_sample_max_rows.
    overwrite : bool
        If True, overwrites existing silver Parquet. Idempotent when False.
    local_mode : bool
        If True, writes to local silver zone (file:///); else HDFS.
    """
    spark = get_spark(local_mode=local_mode)
    cfg = get_settings()
    seed = cfg["data"]["seed"]
    frac = cfg["data"]["dev_sample_fraction"] if dev_mode else 1.0
    max_rows = cfg["data"]["dev_sample_max_rows"] if dev_mode else None

    raw_path = Path(raw_dir)
    if not raw_path.exists():
        raise FileNotFoundError(f"YouNiverse raw directory not found: {raw_path}")

    results: dict[str, int] = {}

    # ── Metadata (yt_metadata_en.jsonl.gz) ───────────────────────────────────
    meta_raw = raw_path / "yt_metadata_en.jsonl.gz"
    if meta_raw.exists():
        t0 = time.time()
        logger.info("Loading metadata: %s", meta_raw)

        # Read gzip JSONL with explicit schema to avoid costly inference scan
        from pyspark.sql.types import StructType, StructField, StringType, DoubleType, LongType
        meta_schema = StructType([
            StructField("categories", StringType(), True),
            StructField("channel_id", StringType(), True),
            StructField("crawl_date", StringType(), True),
            StructField("description", StringType(), True),
            StructField("dislike_count", DoubleType(), True),
            StructField("display_id", StringType(), True),
            StructField("duration", LongType(), True),
            StructField("like_count", DoubleType(), True),
            StructField("tags", StringType(), True),
            StructField("title", StringType(), True),
            StructField("upload_date", StringType(), True),
            StructField("view_count", DoubleType(), True),
        ])
        df = spark.read.schema(meta_schema).json(str(meta_raw))
        logger.info("Metadata raw schema: %s", df.schema.simpleString())

        raw_count = df.count()
        logger.info("Metadata raw row count: %d", raw_count)

        if frac < 1.0:
            df = df.sample(fraction=frac, seed=seed)
        if max_rows and max_rows < raw_count:
            df = df.limit(max_rows)

        sample_count = df.count()
        logger.info("Metadata sample count: %d (frac=%.4f)", sample_count, frac)

        if local_mode:
            out_path = str(local("silver", "youniverse_metadata"))
        else:
            out_path = hdfs("silver", "youniverse_metadata")

        mode = "overwrite" if overwrite else "ignore"
        (
            df.write
            .mode(mode)
            .parquet(out_path)
        )

        # Verify: read back and count
        verify_count = spark.read.parquet(out_path).count()
        if verify_count != sample_count:
            raise RuntimeError(
                f"Row count mismatch after Parquet write: "
                f"wrote {sample_count}, read back {verify_count}. "
                "Write may be corrupted."
            )
        logger.info(
            "[OK] Metadata written to %s. Rows: %d. Time: %.1fs",
            out_path, verify_count, time.time() - t0
        )
        results["metadata"] = verify_count
    else:
        logger.warning("yt_metadata_en.jsonl.gz not found in %s — skipping.", raw_path)

    # ── Channels (df_channels_en.tsv.gz / df_channels_en.csv.gz) ──────────────
    ch_raw = raw_path / "df_channels_en.tsv.gz"
    if not ch_raw.exists():
        ch_raw = raw_path / "df_channels_en.csv.gz"

    if ch_raw.exists():
        t0 = time.time()
        logger.info("Loading channels: %s", ch_raw)
        delim = "\t" if ch_raw.name.endswith(".tsv.gz") else ","
        df_ch = (
            spark.read
            .option("header", "true")
            .option("delimiter", delim)
            .option("compression", "gzip")
            .csv(str(ch_raw))
        )
        # Standardize column names to channel_id, channel_name, subscribers, category, join_date
        if "channel" in df_ch.columns:
            df_ch = df_ch.withColumnRenamed("channel", "channel_id")
        if "name_cc" in df_ch.columns:
            df_ch = df_ch.withColumnRenamed("name_cc", "channel_name")
        if "subscribers_cc" in df_ch.columns:
            from pyspark.sql import functions as F
            df_ch = df_ch.withColumn("subscribers", F.col("subscribers_cc").cast("long"))
        if "category_cc" in df_ch.columns:
            df_ch = df_ch.withColumnRenamed("category_cc", "category")
        if "videos_cc" in df_ch.columns:
            df_ch = df_ch.withColumnRenamed("videos_cc", "videos")

        logger.info("Channels raw schema: %s", df_ch.schema.simpleString())
        raw_ch_count = df_ch.count()
        logger.info("Channels raw row count: %d", raw_ch_count)

        if frac < 1.0:
            df_ch = df_ch.sample(fraction=frac, seed=seed)
        if max_rows and max_rows < raw_ch_count:
            df_ch = df_ch.limit(max_rows)

        sample_count = df_ch.count()
        if local_mode:
            out_path = str(local("silver", "youniverse_channels"))
        else:
            out_path = hdfs("silver", "youniverse_channels")

        mode = "overwrite" if overwrite else "ignore"
        df_ch.write.mode(mode).parquet(out_path)

        verify_count = spark.read.parquet(out_path).count()
        if verify_count != sample_count:
            raise RuntimeError(
                f"Channels row count mismatch: wrote {sample_count}, read back {verify_count}."
            )
        logger.info(
            "[OK] Channels written to %s. Rows: %d. Time: %.1fs",
            out_path, verify_count, time.time() - t0
        )
        results["channels"] = verify_count
    else:
        logger.info("df_channels_en.tsv.gz not present in %s — skipping.", raw_path)

    # ── Timeseries (df_timeseries_en.tsv.gz / df_timeseries_en.csv.gz) ───────
    ts_raw = raw_path / "df_timeseries_en.tsv.gz"
    if not ts_raw.exists():
        ts_raw = raw_path / "df_timeseries_en.csv.gz"
    if not ts_raw.exists():
        ts_raw = raw_path / "_raw_df_timeseries.tsv.gz"

    if ts_raw.exists():
        t0 = time.time()
        logger.info("Loading timeseries: %s", ts_raw)
        delim = "\t" if (".tsv" in ts_raw.name) else ","

        df_ts = (
            spark.read
            .option("header", "true")
            .option("delimiter", delim)
            .option("compression", "gzip")
            .csv(str(ts_raw))
        )
        if "channel" in df_ts.columns:
            df_ts = df_ts.withColumnRenamed("channel", "channel_id")

        logger.info("Timeseries raw schema: %s", df_ts.schema.simpleString())

        raw_ts_count = df_ts.count()
        logger.info("Timeseries raw row count: %d", raw_ts_count)

        if frac < 1.0:
            df_ts = df_ts.sample(fraction=frac, seed=seed)
        if max_rows and max_rows < raw_ts_count:
            df_ts = df_ts.limit(max_rows)

        sample_count = df_ts.count()

        if local_mode:
            out_path = str(local("silver", "youniverse_timeseries"))
        else:
            out_path = hdfs("silver", "youniverse_timeseries")

        mode = "overwrite" if overwrite else "ignore"
        df_ts.write.mode(mode).parquet(out_path)

        verify_count = spark.read.parquet(out_path).count()
        if verify_count != sample_count:
            raise RuntimeError(
                f"Timeseries row count mismatch: wrote {sample_count}, read back {verify_count}."
            )
        logger.info(
            "[OK] Timeseries written to %s. Rows: %d. Time: %.1fs",
            out_path, verify_count, time.time() - t0
        )
        results["timeseries"] = verify_count
    else:
        logger.info("Timeseries file not present in %s — skipping.", raw_path)

    spark.stop()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Load YouNiverse to silver Parquet.")
    parser.add_argument("--raw-dir", required=True, help="Local directory with YouNiverse .gz files.")
    parser.add_argument("--full", action="store_true", help="Load full dataset (default: dev sample).")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing Parquet.")
    parser.add_argument("--local", action="store_true", help="Write to local silver zone (file:///) instead of HDFS.")
    args = parser.parse_args()

    counts = load_youniverse(
        args.raw_dir,
        dev_mode=not args.full,
        overwrite=args.overwrite,
        local_mode=args.local,
    )
    print("\nLoaded tables:")
    for name, count in counts.items():
        print(f"  {name}: {count:,} rows")


if __name__ == "__main__":
    main()
