"""
src/ingestion/load_youniverse.py
Load YouNiverse raw files into HDFS silver zone as partitioned Parquet.

Rules (Section 6):
- Dev sample uses dev_sample_fraction from settings.yaml.
- Gzip is not splittable; raw .gz → Parquet conversion done once.
- Row counts raw vs Parquet MUST match.
- HDFS failures raise loudly; no silent local fallback.
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
) -> dict[str, int]:
    """
    Convert YouNiverse raw .gz files to Parquet in HDFS silver zone.

    Parameters
    ----------
    raw_dir : str
        Local directory containing the YouNiverse .gz files.
    dev_mode : bool
        If True, uses dev_sample_fraction from settings.yaml.
    overwrite : bool
        If True, overwrites existing silver Parquet. Idempotent when False.

    Returns
    -------
    dict mapping table name → row count
    """
    spark = get_spark()
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

        # Read gzip JSONL — must print schema BEFORE assuming any column names
        df = spark.read.option("compression", "gzip").json(str(meta_raw))
        logger.info("Metadata raw schema: %s", df.schema.simpleString())

        raw_count = df.count()
        logger.info("Metadata raw row count: %d", raw_count)

        if frac < 1.0:
            df = df.sample(fraction=frac, seed=seed)
        if max_rows:
            df = df.limit(max_rows)

        sample_count = df.count()
        logger.info("Metadata sample count: %d (frac=%.4f)", sample_count, frac)

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
                "HDFS write may be corrupted."
            )
        logger.info(
            "✅ Metadata written to %s. Rows: %d. Time: %.1fs",
            out_path, verify_count, time.time() - t0
        )
        results["metadata"] = verify_count
    else:
        logger.warning("yt_metadata_en.jsonl.gz not found in %s — skipping.", raw_path)

    # ── Timeseries (df_timeseries_en.csv.gz) ─────────────────────────────────
    ts_raw = raw_path / "df_timeseries_en.csv.gz"
    if ts_raw.exists():
        t0 = time.time()
        logger.info("Loading timeseries: %s", ts_raw)

        df_ts = (
            spark.read
            .option("header", "true")
            .option("compression", "gzip")
            .csv(str(ts_raw))
        )
        logger.info("Timeseries raw schema: %s", df_ts.schema.simpleString())

        raw_ts_count = df_ts.count()
        logger.info("Timeseries raw row count: %d", raw_ts_count)

        if frac < 1.0:
            df_ts = df_ts.sample(fraction=frac, seed=seed)
        if max_rows:
            df_ts = df_ts.limit(max_rows)

        sample_count = df_ts.count()

        out_path = hdfs("silver", "youniverse_timeseries")
        mode = "overwrite" if overwrite else "ignore"
        df_ts.write.mode(mode).parquet(out_path)

        verify_count = spark.read.parquet(out_path).count()
        if verify_count != sample_count:
            raise RuntimeError(
                f"Timeseries row count mismatch: wrote {sample_count}, read back {verify_count}."
            )
        logger.info(
            "✅ Timeseries written to %s. Rows: %d. Time: %.1fs",
            out_path, verify_count, time.time() - t0
        )
        results["timeseries"] = verify_count
    else:
        logger.warning("df_timeseries_en.csv.gz not found — skipping.")

    spark.stop()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Load YouNiverse to HDFS silver Parquet.")
    parser.add_argument("--raw-dir", required=True, help="Local directory with YouNiverse .gz files.")
    parser.add_argument("--full", action="store_true", help="Load full dataset (default: dev sample).")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing Parquet.")
    args = parser.parse_args()

    counts = load_youniverse(args.raw_dir, dev_mode=not args.full, overwrite=args.overwrite)
    print("\nLoaded tables:")
    for name, count in counts.items():
        print(f"  {name}: {count:,} rows")


if __name__ == "__main__":
    main()
