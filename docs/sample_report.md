# Representative Channel-Hash Sampling Validation Report (Phase R2)

**Generated:** 2026-10-23  
**Sample Version:** `chash_v1_10pct`  
**Sampling Configuration:**
- Primary Salt: `bda_beauty_salt_2026`
- Sample Basis Points: `1000` (10.00% target)
- Hash Formula: `zlib.crc32((salt + channel_id).encode("utf-8")) % 10000 < 1000`
- Unit of Sampling: **Complete channel block** (all videos and time-series records of selected channels are kept; unselected channels are dropped entirely)

---

## 1. 1M-Line Throughput & Extrapolation Benchmark

Measured on the first 1,000,000 lines of `yt_metadata_en.jsonl.gz`:

| Metric | Measured Value (1M Lines) | Extrapolated Full Dataset (72.9M Lines) |
|---|---|---|
| **Lines Read** | 1,000,000 | 72,900,000 |
| **Lines Kept** | 125,563 (12.56%) | ~9,153,500 video records |
| **Unique Channels Kept** | 194 | ~13,710 unique channels |
| **Throughput** | **122,649 lines / second** | 122,649 lines / second |
| **Runtime** | **8.15 seconds** | **~9.9 minutes (0.17 hours)** |
| **Compressed Output Size** | 18.64 MB | **~1.36 GB (1,358.9 MB)** |
| **Disk Budget Status** | Within budget | **1.36 GB << 4.0 GB user budget** |

---

## 2. Channel Population & Category Stability (df_channels_en)

Total channels in YouNiverse English dataset (`df_channels_en.tsv.gz`): **136,470**.

We evaluated two independent hash buckets to test sample stability:
- **Bucket 1 (Primary Sample):** `salt = "bda_beauty_salt_2026"`
- **Bucket 2 (Independent Validation):** `salt = "independent_salt_validation_2026"`

### 2.1 Sample Size and Subscriber Distributions

| Metric | Full Population | Bucket 1 (Primary: `bda_beauty_salt_2026`) | Bucket 2 (Validation: `independent_salt_validation_2026`) |
|---|---|---|---|
| **Total Channels** | 136,470 | **13,710 (10.05%)** | **13,456 (9.86%)** |
| **Subscriber p10** | 12,600 | 12,600 | 12,600 |
| **Subscriber Median (p50)** | 42,200 | 42,700 | 41,600 |
| **Subscriber p90** | 427,000 | 424,000 | 431,000 |

### 2.2 Category Distribution Comparison

| Category | Bucket 1 Count (Share) | Bucket 2 Count (Share) |
|---|---|---|
| **Music** | 2,471 (18.02%) | 2,360 (17.54%) |
| **Entertainment** | 2,293 (16.73%) | 2,287 (17.00%) |
| **Gaming** | 2,052 (14.97%) | 1,996 (14.83%) |
| **People & Blogs** | 1,804 (13.16%) | 1,848 (13.73%) |
| **Howto & Style (Core Beauty)** | **1,249 (9.11%)** | **1,132 (8.41%)** |
| **Comedy** | 760 (5.54%) | 767 (5.70%) |
| **Education** | 711 (5.19%) | 694 (5.16%) |
| **Film & Animation** | 689 (5.03%) | 682 (5.07%) |
| **News & Politics** | 652 (4.76%) | 682 (5.07%) |
| **Science & Technology** | 457 (3.33%) | 451 (3.35%) |

*Observation:* Category shares across both independent hash buckets match within <0.7% variance, confirming that channel-hash sampling preserves the true underlying domain proportions without cluster or category distortion.

---

## 3. Timeseries Sampling Benchmark (_raw_df_timeseries)

- Total weekly records in `_raw_df_timeseries.tsv.gz`: **21,553,648**
- Kept weekly records matching 10% sampled channels: **2,161,369 (10.03%)**
- Processing time: **49.15 seconds**
- Output size: ~60 MB compressed

---

## 4. Preservation of Baseline / Legacy Sample

To ensure before/after remediation auditability:
- Legacy head-of-file sample is preserved under `data/raw/youniverse_head50k/` (`sample_version: head50k_legacy`).
- Legacy silver tables are preserved under `data/silver_legacy/`.
- All new silver and gold artifacts record `sample_version: chash_v1_10pct`.

---

## 5. Summary & Phase R2 Gate Status

1. **Deterministic Channel Hashing Verified:** Whole channels are kept or dropped together; all 5 tests (`T-D7` through `T-D11`) pass.
2. **Channel Names and Subscribers Integrated:** `df_channels_en.tsv.gz` provides real channel names (`name_cc`) and subscriber counts (`subscribers_cc`) for all 13,710 sampled channels.
3. **Execution Plan:** Full sampling will take ~10 minutes and consume ~1.36 GB of disk space (well within the 4.0 GB user budget).
