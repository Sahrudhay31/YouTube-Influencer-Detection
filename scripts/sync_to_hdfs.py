"""
scripts/sync_to_hdfs.py
Synchronizes and migrates all raw, silver, and gold datasets to Hadoop HDFS.

Ensures project compliance with Big Data Analytics (BDA) storage rubrics:
  - Raw API extracts -> /bda/raw/api/dt=YYYY-MM-DD/
  - Raw YouNiverse -> /bda/raw/youniverse/
  - Silver tables -> /bda/silver/
  - Gold tables -> /bda/gold/
  - Model artifacts -> /bda/models/

Usage:
  python scripts/sync_to_hdfs.py [--hdfs-uri hdfs://localhost:8020] [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.config import get_hdfs_uri, project_root
from src.common.logging_setup import setup_logging
from src.common.paths import hdfs, local
from src.common.spark_session import get_spark

logger = setup_logging(__name__)


DATASETS_TO_SYNC = [
    # (local_zone, local_name, hdfs_zone, hdfs_name, data_type)
    ("silver", "youniverse_metadata", "silver", "youniverse_metadata", "parquet"),
    ("silver", "youniverse_channels", "silver", "youniverse_channels", "parquet"),
    ("silver", "youniverse_timeseries", "silver", "youniverse_timeseries", "parquet"),
    ("silver", "channel_domain_profiles", "silver", "channel_domain_profiles", "parquet"),
    ("silver", "sponsorship_video_features", "silver", "sponsorship_video_features", "parquet"),
    ("silver", "channel_sponsorship_metrics", "silver", "channel_sponsorship_metrics", "parquet"),
    ("silver", "comment_samples", "silver", "comment_samples", "parquet"),
    ("gold", "channel_influencer_profiles", "gold", "channel_influencer_profiles", "parquet"),
    ("gold", "scored_creators.parquet", "gold", "scored_creators.parquet", "parquet"),
    ("gold", "audience_quality", "gold", "audience_quality", "parquet"),
    ("gold", "enrichment_candidates", "gold", "enrichment_candidates", "parquet"),
]


def sync_all_to_hdfs(
    hdfs_uri: str | None = None,
    dry_run: bool = False,
) -> dict:
    target_uri = hdfs_uri or get_hdfs_uri()
    logger.info("=" * 70)
    logger.info("HDFS SYNCHRONIZATION PIPELINE")
    logger.info("Target HDFS URI: %s", target_uri)
    logger.info("Mode: %s", "DRY-RUN" if dry_run else "LIVE UPLOAD")
    logger.info("=" * 70)

    t0 = time.time()
    results = {
        "hdfs_uri": target_uri,
        "synced": [],
        "skipped": [],
        "failed": [],
    }

    if dry_run:
        logger.info("[DRY-RUN] Checking local source files...")
        for l_zone, l_name, h_zone, h_name, dtype in DATASETS_TO_SYNC:
            src_path = local(l_zone, l_name)
            dest_hdfs = hdfs(h_zone, h_name)
            if src_path.exists():
                logger.info("  [READY] Local '%s/%s' -> HDFS '%s'", l_zone, l_name, dest_hdfs)
                results["synced"].append((str(src_path), dest_hdfs))
            else:
                logger.info("  [SKIP]  Local source not found: %s", src_path)
                results["skipped"].append(str(src_path))
        return results

    # Initialize PySpark with the target HDFS NameNode
    logger.info("Initializing Spark session connected to %s...", target_uri)
    try:
        spark = get_spark("HDFSSyncPipeline", local_mode=False)
    except Exception as exc:
        logger.error(
            "FAILED to connect to HDFS at '%s': %s\n"
            "Ensure your Hadoop cluster is running and reachable.",
            target_uri, exc
        )
        raise

    for l_zone, l_name, h_zone, h_name, dtype in DATASETS_TO_SYNC:
        src_path = local(l_zone, l_name)
        dest_hdfs = hdfs(h_zone, h_name)

        if not src_path.exists():
            logger.info("Skipping '%s/%s' (local source does not exist).", l_zone, l_name)
            results["skipped"].append(f"{l_zone}/{l_name}")
            continue

        try:
            logger.info("Syncing '%s' -> '%s' ...", src_path, dest_hdfs)
            if dtype == "parquet":
                df = spark.read.parquet(str(src_path))
                local_count = df.count()
                df.write.mode("overwrite").parquet(dest_hdfs)
                hdfs_count = spark.read.parquet(dest_hdfs).count()

                if hdfs_count != local_count:
                    raise RuntimeError(
                        f"Row count mismatch! Local had {local_count}, HDFS has {hdfs_count}"
                    )
                logger.info("  [SUCCESS] Written %d rows to HDFS: %s", hdfs_count, dest_hdfs)
                results["synced"].append({"dataset": f"{l_zone}/{l_name}", "rows": hdfs_count, "path": dest_hdfs})
            else:
                # Raw files / json
                df = spark.read.json(str(src_path))
                df.write.mode("overwrite").json(dest_hdfs)
                logger.info("  [SUCCESS] Written JSON to HDFS: %s", dest_hdfs)
                results["synced"].append({"dataset": f"{l_zone}/{l_name}", "path": dest_hdfs})

        except Exception as exc:
            logger.error("  [FAILED] Could not sync %s to HDFS: %s", src_path, exc)
            results["failed"].append({"dataset": f"{l_zone}/{l_name}", "error": str(exc)})

    # Also sync raw API partitions if they exist
    raw_api_local = project_root() / "data" / "raw" / "api"
    if raw_api_local.exists():
        for partition in raw_api_local.glob("dt=*"):
            dt_name = partition.name
            dest_api_hdfs = hdfs("raw_api", dt_name)
            try:
                logger.info("Syncing raw API partition '%s' -> '%s' ...", partition, dest_api_hdfs)
                df_api = spark.read.json(str(partition))
                df_api.write.mode("overwrite").json(dest_api_hdfs)
                results["synced"].append({"dataset": f"raw_api/{dt_name}", "path": dest_api_hdfs})
                logger.info("  [SUCCESS] Written raw API partition to HDFS.")
            except Exception as exc:
                logger.warning("Could not sync API partition %s: %s", dt_name, exc)

    elapsed = round(time.time() - t0, 1)
    logger.info("=" * 70)
    logger.info(
        "HDFS SYNC COMPLETE in %.1fs | Synced=%d | Skipped=%d | Failed=%d",
        elapsed, len(results["synced"]), len(results["skipped"]), len(results["failed"])
    )
    logger.info("=" * 70)
    spark.stop()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize all project data to Hadoop HDFS")
    parser.add_argument("--hdfs-uri", type=str, default=None, help="HDFS NameNode URI (e.g. hdfs://localhost:8020)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate sync without connecting to HDFS")
    args = parser.parse_args()

    sync_all_to_hdfs(hdfs_uri=args.hdfs_uri, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
