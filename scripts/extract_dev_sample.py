"""
scripts/extract_dev_sample.py
Extracts a clean dev sample from YouNiverse compressed raw file.
Adheres to settings.yaml dev_sample_max_rows (default 50,000).
"""
import gzip
import os
import time
from pathlib import Path
import yaml

with open("config/settings.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

max_rows = cfg.get("data", {}).get("dev_sample_max_rows", 50000)
source_file = Path(r"C:\Users\SAHRUHDAY CHIRRA\Downloads\yt_metadata_en.jsonl.gz")
out_dir = Path("data/raw/youniverse")
out_dir.mkdir(parents=True, exist_ok=True)
out_file = out_dir / "yt_metadata_en.jsonl.gz"

print(f"Reading from: {source_file}")
print(f"Writing max {max_rows} rows to: {out_file}")

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
print(f" Extracted {count:,} rows in {dur:.2f}s ({size_mb:.2f} MB)")
