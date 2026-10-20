# Data Quality Report — YouNiverse Dev Sample

**Date:** 2026-10-20  
**Phase:** Phase 2 (Infrastructure & Data Layer)  
**Source Dataset:** YouNiverse YouTube Metadata (`yt_metadata_en.jsonl.gz`)  
**Raw Source Location:** `data/raw/youniverse/yt_metadata_en.jsonl.gz` (from 13.63 GB full archive)  
**Silver Parquet Location:** `data/silver/youniverse_metadata`  

---

## 1. Executive Summary

A deterministic 50,000-row developer sample was extracted from the full 13.63 GB YouNiverse English YouTube metadata dataset and ingested into the Silver Parquet zone using PySpark. Round-trip integrity, schema validation, idempotency, and error-handling constraints have been thoroughly verified against all Phase 2 smoke tests (`T-D1` through `T-D6`).

---

## 2. Dataset Overview & Cardinality

| Metric | Measured Value | Verification Method |
| :--- | :--- | :--- |
| **Total Ingested Rows** | **50,000** | Spark `df.count()` |
| **Unique Videos (`display_id`)** | **50,000** | Spark `df.select('display_id').distinct().count()` |
| **Duplicate Video IDs** | **0 (0.00%)** | Verified via test `T-D3` |
| **Unique Channels (`channel_id`)** | **127** | Spark `df.select('channel_id').distinct().count()` |
| **Earliest Upload Date** | **2006-09-11 00:00:00** | Spark `F.min('upload_date')` |
| **Latest Upload Date** | **2019-10-03 00:00:00** | Spark `F.max('upload_date')` |
| **Time Span** | **13.1 years** | Historical breadth across YouTube |

---

## 3. Schema & Null Rate Audit

All 12 fields defined in `docs/data_dictionary.md` were audited across the 50,000 records:

| Column Name | Inferred PySpark Type | Null Count | Null Rate (%) | Data Quality Note |
| :--- | :--- | :--- | :--- | :--- |
| `display_id` | `StringType` | 0 | 0.00% | Primary video key. 100% complete and unique. |
| `channel_id` | `StringType` | 0 | 0.00% | YouTube Channel ID. 100% complete. |
| `title` | `StringType` | 0 | 0.00% | Video title. Text features for domain classification. |
| `description` | `StringType` | 0 | 0.00% | Video description text. Rich NLP corpus. |
| `categories` | `StringType` | 0 | 0.00% | YouTube category tag. Zero unassigned categories. |
| `tags` | `StringType` | 0 | 0.00% | Creator keyword tags. |
| `duration` | `LongType` | 0 | 0.00% | Video duration in seconds. |
| `view_count` | `DoubleType` | 0 | 0.00% | Video views. Zero missing views. |
| `upload_date` | `StringType` | 0 | 0.00% | Video publish timestamp. |
| `crawl_date` | `StringType` | 0 | 0.00% | YouNiverse scraper crawl timestamp. |
| `like_count` | `DoubleType` | 1,120 | **2.24%** | Disabled/hidden public likes on specific videos. |
| `dislike_count` | `DoubleType` | 1,120 | **2.24%** | Exactly mirrors `like_count` when ratings disabled. |

### Handling Missing Ratings:
The 2.24% missing rating rate is an authentic reflection of YouTube creators choosing to disable like/dislike displays on their videos. In Phase 4 feature engineering, these missing values will be handled with explicit indicator columns and zero imputation rather than row deletion, preserving channel volume metrics.

---

## 4. Category Distribution

The dev sample encompasses 15 categories, with substantial representation in categories relevant to influencer promotion analysis:

| Category | Record Count | Percentage (%) | Relevance to Project Domain |
| :--- | :--- | :--- | :--- |
| **Music** | 11,929 | 23.86% | Macro Out-of-Domain baseline |
| **Gaming** | 10,578 | 21.16% | Macro Out-of-Domain baseline |
| **People & Blogs** | 4,850 | 9.70% | Lifestyle / Vlogs / In-domain overlap |
| **Science & Technology** | 3,868 | 7.74% | Gadget / Tech review baseline |
| **News & Politics** | 3,487 | 6.97% | News commentary baseline |
| **Entertainment** | 3,460 | 6.92% | Entertainment baseline |
| **Howto & Style** | **3,283** | **6.57%** | **Core Macro Domain: Beauty, Skincare, Haircare** |
| **Education** | 1,952 | 3.90% | Tutorials / Informational |
| **Film & Animation** | 1,181 | 2.36% | Creative media |
| **Sports** | 1,056 | 2.11% | Fitness / Athletics |
| **Pets & Animals** | 1,052 | 2.10% | Animal content |
| **Travel & Events** | 962 | 1.92% | Travel vlogs |
| **Comedy** | 916 | 1.83% | Sketches / Humor |
| **Autos & Vehicles** | 713 | 1.43% | Automotive reviews |
| **Nonprofits & Activism** | 713 | 1.43% | Social awareness |

*Insight:* With 3,283 videos in **Howto & Style** and 4,850 in **People & Blogs**, the dev sample contains thousands of beauty, skincare, and personal care tutorials and reviews for Phase 3 domain classifier training and validation.

---

## 5. Verification Test Suite Status

| Test Identifier | Test Case Name | Status | Verified Behavior |
| :--- | :--- | :--- | :--- |
| **T-D1** | `test_td1_write_read_round_trip` | **PASSED** | Parquet write -> read round trip produces exact input match. |
| **T-D2** | `test_td2_and_td4_silver_parquet_row_count` | **PASSED** | Silver Parquet row count matches raw ingestion (50,000 rows). |
| **T-D3** | `test_td3_no_duplicate_video_ids` | **PASSED** | Verified zero duplicate video IDs in silver dataset. |
| **T-D4** | `test_td2_and_td4_silver_parquet_row_count` | **PASSED** | Row count respects configured cap (`<= 50,000`). |
| **T-D5** | `test_td5_idempotent_write` | **PASSED** | Re-running ingestion job without overwrite preserves existing data safely. |
| **T-D6** | `test_td6_loud_failure_on_bad_uri` | **PASSED** | Unreachable storage locations fail loudly; no silent local fallback. |

---

## 6. Recommendations for Phase 3

1. **Category Label Mapping:** Map `Howto & Style` (plus beauty sub-niches in `People & Blogs`) to positive in-domain labels, while using balanced negative sampling from `Music`, `Gaming`, `Science & Technology`, and `News & Politics`.
2. **Channel-Based Split:** Ensure all 50,000 videos are grouped strictly by `channel_id` before performing the 70/15/15 train/val/test split to prevent data leakage between train and test sets.
