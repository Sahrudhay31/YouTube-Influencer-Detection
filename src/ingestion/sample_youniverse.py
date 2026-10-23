"""
src/ingestion/sample_youniverse.py
Channel-hash sampling for YouNiverse raw datasets (Phase R2).

Ensures:
- Gzip is streamed line-by-line without full disk decompression.
- Channels are kept/dropped as complete blocks:
  zlib.crc32((salt + channel_id).encode("utf-8")) % 10000 < sample_basis_points
- Idempotent and deterministic across runs given the same salt and basis points.
- Checkpointing and resume capability via --resume.
- --max-lines parameter for throughput measurement and dry runs.
- Samples video metadata, channels metadata (with channel names and subscribers),
  and weekly time series.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
import time
import zlib
from pathlib import Path
from typing import Any, Generator

import yaml

from src.common.config import get_settings
from src.common.logging_setup import setup_logging

logger = setup_logging(__name__)


def is_channel_kept(channel_id: str, salt: str, basis_points: int) -> bool:
    """Deterministic channel-hash sampling rule."""
    if not channel_id:
        return False
    digest = zlib.crc32((salt + channel_id).encode("utf-8"))
    return (digest % 10000) < basis_points


def extract_channel_id_from_json_line(line: str) -> str | None:
    """
    Fast extraction of channel_id from a YouNiverse JSONL line.
    Falls back to json.loads if direct substring search is ambiguous.
    """
    idx = line.find('"channel_id": "')
    if idx != -1:
        end_idx = line.find('"', idx + 15)
        if end_idx != -1:
            return line[idx + 15:end_idx]
    try:
        data = json.loads(line)
        return data.get("channel_id")
    except Exception:
        return None


def sample_metadata(
    source_path: Path,
    dest_path: Path,
    salt: str,
    basis_points: int,
    max_lines: int | None = None,
    resume: bool = False,
    checkpoint_path: Path | None = None,
    checkpoint_interval: int = 500000,
) -> dict[str, Any]:
    """
    Stream metadata JSONL gzip line-by-line and write sampled lines.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if checkpoint_path is None:
        checkpoint_path = dest_path.parent / "metadata_checkpoint.json"

    start_line = 0
    lines_read = 0
    lines_kept = 0
    kept_channels: set[str] = set()

    if resume and checkpoint_path.exists():
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as cp_file:
                cp = json.load(cp_file)
                start_line = cp.get("lines_read", 0)
                lines_kept = cp.get("lines_kept", 0)
                kept_channels = set(cp.get("kept_channels", []))
                logger.info(
                    "Resuming metadata sampling from line %d (already kept %d lines)",
                    start_line,
                    lines_kept,
                )
        except Exception as exc:
            logger.warning("Failed to load checkpoint (%s); starting from line 0", exc)
            start_line = 0

    mode = "at" if (resume and start_line > 0 and dest_path.exists()) else "wt"
    open_dest = gzip.open(dest_path, mode, encoding="utf-8")

    t0 = time.time()
    last_log_time = t0

    try:
        with gzip.open(source_path, "rt", encoding="utf-8", errors="ignore") as in_f:
            for idx, line in enumerate(in_f):
                if idx < start_line:
                    continue
                if max_lines is not None and lines_read >= max_lines:
                    break

                lines_read += 1
                ch_id = extract_channel_id_from_json_line(line)
                if ch_id and is_channel_kept(ch_id, salt, basis_points):
                    open_dest.write(line if line.endswith("\n") else line + "\n")
                    lines_kept += 1
                    kept_channels.add(ch_id)

                if lines_read % checkpoint_interval == 0:
                    open_dest.flush()
                    now = time.time()
                    elapsed = now - t0
                    rate = lines_read / elapsed if elapsed > 0 else 0
                    logger.info(
                        "Metadata progress: %d lines read, %d kept (%d unique channels) [%.0f lines/s]",
                        lines_read,
                        lines_kept,
                        len(kept_channels),
                        rate,
                    )
                    # Save checkpoint
                    with open(checkpoint_path, "w", encoding="utf-8") as cp_file:
                        json.dump(
                            {
                                "lines_read": start_line + lines_read,
                                "lines_kept": lines_kept,
                                "kept_channels": list(kept_channels)[:5000],  # sample for checkpoint
                                "kept_channel_count": len(kept_channels),
                                "timestamp": time.time(),
                            },
                            cp_file,
                        )
    finally:
        open_dest.close()

    total_time = time.time() - t0
    rate = lines_read / total_time if total_time > 0 else 0
    out_size_bytes = dest_path.stat().st_size if dest_path.exists() else 0

    stats = {
        "lines_read": lines_read,
        "lines_kept": lines_kept,
        "unique_channels": len(kept_channels),
        "kept_fraction": (lines_kept / lines_read) if lines_read > 0 else 0.0,
        "elapsed_seconds": total_time,
        "throughput_lines_per_sec": rate,
        "output_size_bytes": out_size_bytes,
        "output_size_mb": round(out_size_bytes / (1024 * 1024), 2),
    }

    # Final checkpoint update
    if checkpoint_path:
        with open(checkpoint_path, "w", encoding="utf-8") as cp_file:
            json.dump({**stats, "kept_channels": list(kept_channels)}, cp_file)

    logger.info(
        "Metadata sampling complete: %d lines read, %d kept (%d channels) in %.2fs (%.0f lines/s, %.2f MB)",
        lines_read,
        lines_kept,
        len(kept_channels),
        total_time,
        rate,
        stats["output_size_mb"],
    )
    return stats


def sample_channels(
    source_path: Path,
    dest_path: Path,
    salt: str,
    basis_points: int,
) -> dict[str, Any]:
    """
    Stream df_channels_en.tsv.gz, keep channels matching hash rule,
    and write to dest_path.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    total = 0
    kept = 0
    kept_channels: set[str] = set()

    with gzip.open(source_path, "rt", encoding="utf-8", errors="ignore") as in_f, \
         gzip.open(dest_path, "wt", encoding="utf-8") as out_f:
        reader = csv.reader(in_f, delimiter="\t")
        writer = csv.writer(out_f, delimiter="\t", lineterminator="\n")

        header = next(reader)
        writer.writerow(header)
        ch_idx = header.index("channel") if "channel" in header else 2

        for row in reader:
            total += 1
            if len(row) <= ch_idx:
                continue
            ch_id = row[ch_idx]
            if is_channel_kept(ch_id, salt, basis_points):
                writer.writerow(row)
                kept += 1
                kept_channels.add(ch_id)

    total_time = time.time() - t0
    out_size_bytes = dest_path.stat().st_size if dest_path.exists() else 0
    stats = {
        "channels_total": total,
        "channels_kept": kept,
        "kept_fraction": (kept / total) if total > 0 else 0.0,
        "elapsed_seconds": total_time,
        "output_size_bytes": out_size_bytes,
        "output_size_mb": round(out_size_bytes / (1024 * 1024), 2),
    }
    logger.info(
        "Channels sampling complete: %d total, %d kept in %.2fs (%.2f MB)",
        total,
        kept,
        total_time,
        stats["output_size_mb"],
    )
    return stats


def sample_timeseries(
    source_path: Path,
    dest_path: Path,
    salt: str,
    basis_points: int,
    max_lines: int | None = None,
) -> dict[str, Any]:
    """
    Stream _raw_df_timeseries.tsv.gz, keep channels matching hash rule,
    and write to dest_path.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    total = 0
    kept = 0
    kept_channels: set[str] = set()

    with gzip.open(source_path, "rt", encoding="utf-8", errors="ignore") as in_f, \
         gzip.open(dest_path, "wt", encoding="utf-8") as out_f:
        reader = csv.reader(in_f, delimiter="\t")
        writer = csv.writer(out_f, delimiter="\t", lineterminator="\n")

        header = next(reader)
        writer.writerow(header)
        ch_idx = header.index("channel") if "channel" in header else 0

        for row in reader:
            if max_lines is not None and total >= max_lines:
                break
            total += 1
            if len(row) <= ch_idx:
                continue
            ch_id = row[ch_idx]
            if is_channel_kept(ch_id, salt, basis_points):
                writer.writerow(row)
                kept += 1
                kept_channels.add(ch_id)

    total_time = time.time() - t0
    out_size_bytes = dest_path.stat().st_size if dest_path.exists() else 0
    stats = {
        "timeseries_total": total,
        "timeseries_kept": kept,
        "unique_channels": len(kept_channels),
        "kept_fraction": (kept / total) if total > 0 else 0.0,
        "elapsed_seconds": total_time,
        "output_size_bytes": out_size_bytes,
        "output_size_mb": round(out_size_bytes / (1024 * 1024), 2),
    }
    logger.info(
        "Timeseries sampling complete: %d total, %d kept (%d channels) in %.2fs (%.2f MB)",
        total,
        kept,
        len(kept_channels),
        total_time,
        stats["output_size_mb"],
    )
    return stats


def parse_args():
    parser = argparse.ArgumentParser(description="YouNiverse Channel-Hash Sampler.")
    parser.add_argument(
        "--metadata-source",
        type=str,
        default=os.environ.get("YOUNIVERSE_METADATA_PATH", ""),
        help="Path to raw yt_metadata_en.jsonl.gz (or set YOUNIVERSE_METADATA_PATH env var)",
    )
    parser.add_argument(
        "--channels-source",
        type=str,
        default=os.environ.get("YOUNIVERSE_CHANNELS_PATH", ""),
        help="Path to raw df_channels_en.tsv.gz (or set YOUNIVERSE_CHANNELS_PATH env var)",
    )
    parser.add_argument(
        "--timeseries-source",
        type=str,
        default=os.environ.get("YOUNIVERSE_TIMESERIES_PATH", ""),
        help="Path to raw _raw_df_timeseries.tsv.gz (or set YOUNIVERSE_TIMESERIES_PATH env var)",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="data/raw/youniverse",
        help="Target directory for sampled gzip files.",
    )
    parser.add_argument(
        "--basis-points",
        type=int,
        default=None,
        help="Basis points out of 10000 (default from config/settings.yaml).",
    )
    parser.add_argument(
        "--salt",
        type=str,
        default=None,
        help="Salt string for hashing (default from config/settings.yaml).",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=None,
        help="Maximum lines to process from metadata (e.g. 1000000 for throughput benchmark).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume sampling using checkpoint.",
    )
    parser.add_argument(
        "--measure-only",
        action="store_true",
        help="Run 1M line throughput measurement on metadata without full overwrite.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    settings = get_settings()
    data_cfg = settings.get("data", {})

    salt = args.salt or data_cfg.get("sample_salt", "bda_beauty_salt_2026")
    basis_points = args.basis_points or data_cfg.get("sample_basis_points", 1000)
    sample_version = data_cfg.get("sample_version", "chash_v1_10pct")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_source = Path(args.metadata_source)
    channels_source = Path(args.channels_source)
    ts_source = Path(args.timeseries_source)

    print(f"=== YouNiverse Channel-Hash Sampler ({sample_version}) ===")
    print(f"Salt: {salt}")
    print(f"Basis points: {basis_points} ({basis_points/100:.1f}%)")
    print(f"Target directory: {out_dir}")

    if args.measure_only:
        measure_max = args.max_lines or 1000000
        temp_dest = out_dir / "temp_measure_metadata.jsonl.gz"
        print(f"\n[1/1] Measuring throughput on first {measure_max:,} lines of metadata...")
        stats = sample_metadata(
            source_path=meta_source,
            dest_path=temp_dest,
            salt=salt,
            basis_points=basis_points,
            max_lines=measure_max,
        )
        if temp_dest.exists():
            temp_dest.unlink()
        print("\n=== Throughput Measurement Results ===")
        print(f"Lines read: {stats['lines_read']:,}")
        print(f"Lines kept: {stats['lines_kept']:,} ({stats['kept_fraction']*100:.2f}%)")
        print(f"Unique channels kept: {stats['unique_channels']:,}")
        print(f"Throughput: {stats['throughput_lines_per_sec']:,.0f} lines/sec")
        print(f"Elapsed: {stats['elapsed_seconds']:.2f} seconds")
        # Extrapolate for full ~72.9M lines
        full_lines = 72900000
        est_sec = full_lines / stats["throughput_lines_per_sec"]
        est_kept_lines = full_lines * stats["kept_fraction"]
        est_size_mb = (stats["output_size_mb"] / stats["lines_read"]) * full_lines
        print(f"\nExtrapolated full run (72.9M lines):")
        print(f"  Estimated runtime: {est_sec/60:.1f} minutes ({est_sec/3600:.2f} hours)")
        print(f"  Estimated kept video records: {est_kept_lines:,.0f}")
        print(f"  Estimated output size: {est_size_mb:,.1f} MB ({est_size_mb/1024:.2f} GB)")
        sys.exit(0)

    # 1. Sample Channels (with channel names and true subscribers)
    if channels_source.exists():
        print(f"\n[1/3] Sampling channels from {channels_source}...")
        ch_dest = out_dir / "df_channels_en.tsv.gz"
        ch_stats = sample_channels(channels_source, ch_dest, salt, basis_points)
        print(f"Channels: {ch_stats['channels_kept']:,} kept of {ch_stats['channels_total']:,} ({ch_stats['output_size_mb']} MB)")
    else:
        print(f"[WARN] Channels source not found: {channels_source}")

    # 2. Sample Timeseries (weekly views and subscribers)
    if ts_source.exists():
        print(f"\n[2/3] Sampling timeseries from {ts_source}...")
        ts_dest = out_dir / "df_timeseries_en.tsv.gz"
        ts_stats = sample_timeseries(ts_source, ts_dest, salt, basis_points, max_lines=args.max_lines)
        print(f"Timeseries: {ts_stats['timeseries_kept']:,} kept of {ts_stats['timeseries_total']:,} ({ts_stats['output_size_mb']} MB)")
    else:
        print(f"[WARN] Timeseries source not found: {ts_source}")

    # 3. Sample Metadata (videos)
    if meta_source.exists():
        print(f"\n[3/3] Sampling metadata from {meta_source}...")
        meta_dest = out_dir / "yt_metadata_en.jsonl.gz"
        meta_stats = sample_metadata(
            source_path=meta_source,
            dest_path=meta_dest,
            salt=salt,
            basis_points=basis_points,
            max_lines=args.max_lines,
            resume=args.resume,
        )
        print(f"Metadata: {meta_stats['lines_kept']:,} kept of {meta_stats['lines_read']:,} ({meta_stats['output_size_mb']} MB)")
    else:
        print(f"[WARN] Metadata source not found: {meta_source}")

    print("\n[OK] Sampling pipeline complete.")


if __name__ == "__main__":
    main()
