"""
scripts/extract_dev_sample.py
Extracts a clean dev sample from YouNiverse compressed raw file.
Adheres to settings.yaml dev_sample_max_rows (default 50,000).
Reads source file from CLI argument --source or YOUNIVERSE_SOURCE_PATH environment variable.
"""
import argparse
import gzip
import os
import sys
import time
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

def parse_args():
    parser = argparse.ArgumentParser(description="Extract dev sample from raw YouNiverse gzip archive.")
    parser.add_argument(
        "--source",
        type=str,
        default=os.environ.get("YOUNIVERSE_SOURCE_PATH", ""),
        help="Path to source yt_metadata_en.jsonl.gz (or set YOUNIVERSE_SOURCE_PATH env var)"
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Max rows to extract (overrides settings.yaml)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    settings_path = ROOT / "config" / "settings.yaml"
    with open(settings_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    max_rows = args.max_rows or cfg.get("data", {}).get("dev_sample_max_rows", 50000)

    if not args.source:
        print("[ERROR] No source path specified. Provide --source <path> or set YOUNIVERSE_SOURCE_PATH.", file=sys.stderr)
        sys.exit(1)

    source_file = Path(args.source)
    if not source_file.exists():
        print(f"[ERROR] Source file not found: {source_file}", file=sys.stderr)
        sys.exit(1)

    out_dir = ROOT / "data" / "raw" / "youniverse"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "yt_metadata_en.jsonl.gz"

    print(f"Reading from: {source_file}")
    print(f"Writing max {max_rows:,} rows to: {out_file}")

    t0 = time.time()
    count = 0

    with gzip.open(source_file, "rb") as fin, gzip.open(out_file, "wb") as fout:
        for line in fin:
            fout.write(line)
            count += 1
            if count >= max_rows:
                break

    dur = time.time() - t0
    size_mb = out_file.stat().st_size / (1024 * 1024)
    print(f"[OK] Extracted {count:,} rows in {dur:.2f}s ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
