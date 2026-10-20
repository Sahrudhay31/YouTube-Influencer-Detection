"""
src/maintenance/purge_api_data.py
Deletes raw API HDFS partitions older than retention_days.

Rules (Section 5.12):
- Supports --dry-run (default).
- Writes a purge report.
- Touches only /bda/raw/api/dt=YYYY-MM-DD/ partitions.
- Never deletes silver/gold data or YouNiverse data.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.common.config import get_settings
from src.common.logging_setup import setup_logging
from src.common.paths import hdfs, local

logger = setup_logging(__name__)

_PARTITION_RE = re.compile(r"^dt=(\d{4}-\d{2}-\d{2})$")


def purge_api_partitions(dry_run: bool = True, retention_days: int | None = None) -> dict:
    """
    Delete raw API partitions older than retention_days.

    Parameters
    ----------
    dry_run : bool
        If True (default), only reports what would be deleted.
    retention_days : int | None
        Override settings.yaml retention.raw_api_days.

    Returns
    -------
    dict with keys: checked, deleted, skipped, dry_run
    """
    try:
        import subprocess
        cfg = get_settings()
        if retention_days is None:
            retention_days = cfg["retention"]["raw_api_days"]
        warn_days = cfg["retention"]["refresh_warning_days"]

        cutoff = datetime.now(timezone.utc).date() - timedelta(days=retention_days)
        warn_cutoff = datetime.now(timezone.utc).date() - timedelta(days=warn_days)
        api_base = hdfs("raw_api")

        # List partitions via hdfs dfs -ls
        result = subprocess.run(
            ["hdfs", "dfs", "-ls", api_base],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            if "No such file or directory" in result.stderr:
                logger.info("No raw API partitions found at %s — nothing to purge.", api_base)
                return {"checked": 0, "deleted": 0, "skipped": 0, "dry_run": dry_run}
            raise RuntimeError(
                f"hdfs dfs -ls failed: {result.stderr}"
            )

        deleted: list[str] = []
        skipped: list[str] = []
        warned: list[str] = []

        for line in result.stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            path_str = parts[-1]
            dir_name = path_str.rstrip("/").split("/")[-1]
            m = _PARTITION_RE.match(dir_name)
            if not m:
                continue
            partition_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()

            if partition_date < cutoff:
                if dry_run:
                    logger.info("[DRY-RUN] Would delete: %s", path_str)
                else:
                    del_result = subprocess.run(
                        ["hdfs", "dfs", "-rm", "-r", path_str],
                        capture_output=True, text=True, timeout=60
                    )
                    if del_result.returncode != 0:
                        raise RuntimeError(f"Failed to delete {path_str}: {del_result.stderr}")
                    logger.info("Deleted partition: %s", path_str)
                deleted.append(path_str)
            else:
                if partition_date < warn_cutoff:
                    logger.warning(
                        "Partition %s is approaching expiry (%d days old; refresh at %d days).",
                        path_str, (datetime.now(timezone.utc).date() - partition_date).days, warn_days
                    )
                    warned.append(path_str)
                skipped.append(path_str)

        report = {
            "checked": len(deleted) + len(skipped),
            "deleted": len(deleted),
            "skipped": len(skipped),
            "warned_approaching_expiry": warned,
            "dry_run": dry_run,
            "cutoff_date": str(cutoff),
            "retention_days": retention_days,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

        report_dir = local("docs")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "purge_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info("Purge report written to %s", report_path)

        return report

    except Exception as exc:
        logger.error("purge_api_data failed: %s", exc)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Purge raw API HDFS partitions older than retention policy.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Default: dry-run (no actual deletes).")
    parser.add_argument("--live", action="store_true", help="Actually delete partitions.")
    parser.add_argument("--retention-days", type=int, default=None)
    args = parser.parse_args()

    dry = not args.live
    report = purge_api_partitions(dry_run=dry, retention_days=args.retention_days)
    mode = "DRY-RUN" if dry else "LIVE"
    print(f"\n[{mode}] Purge complete: {report['deleted']} deleted, {report['skipped']} kept.")


if __name__ == "__main__":
    main()
