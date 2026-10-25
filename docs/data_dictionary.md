# Data Dictionary: YouNiverse Dataset (`yt_metadata_en`)

> **Verified On:** 2026-10-20  
> **Source File:** `yt_metadata_en.jsonl.gz` (Zenodo record 4814914)  
> **Inspected Sample:** 50,000 rows (`data/raw/youniverse/yt_metadata_en.jsonl.gz`)  
> **Profiling Engine:** Apache Spark 3.5.3 (local mode)

---

## 1. Verified Column Specifications

| Column Name | Spark Data Type | Null Count | Null Rate | Description / Semantics | Example Value |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`display_id`** | `string` | 0 | 0.00% | Unique 11-character YouTube video identifier (equivalent to YouTube API `video_id`). | `"SBqSc91Hn9g"` |
| **`channel_id`** | `string` | 0 | 0.00% | Unique 24-character YouTube channel identifier (starts with `UC`). Primary key for channel rollup and split isolation. | `"UCzWrhkg9eK5I8Bm3HfV-unA"` |
| **`title`** | `string` | 0 | 0.00% | Public title of the video. Used for domain classification and sponsorship detection. | `"Lego City Police Lego Firetruck Cartoons..."` |
| **`description`** | `string` | 0 | 0.00% | Full video description text. Primary source for sponsorship disclosure tokens, affiliate links, and promo codes. | `"Lego City Police Lego Firetruck Cartoons..."` |
| **`categories`** | `string` | 0 | 0.00% | YouTube top-level category string assigned to the video. | `"Film & Animation"` |
| **`tags`** | `string` | 0 | 0.00% | Comma-separated metadata tags provided by the creator. | `"lego city,lego police,lego city episodes"` |
| **`duration`** | `long` | 0 | 0.00% | Length of the video in integer seconds. | `1159` |
| **`view_count`** | `double` | 0 | 0.00% | Total views recorded at crawl time (late 2019). Base metric for reach and promo lift. | `1057.0` |
| **`like_count`** | `double` | 1,120 | 2.24% | Total public likes recorded at crawl time. Null when creator disabled public ratings. | `8.0` |
| **`dislike_count`** | `double` | 1,120 | 2.24% | Total public dislikes recorded prior to YouTube's public dislike removal. | `1.0` |
| **`upload_date`** | `string` | 0 | 0.00% | Timestamp when the video was uploaded (formatted as `YYYY-MM-DD HH:MM:SS`). | `"2016-09-28 00:00:00"` |
| **`crawl_date`** | `string` | 0 | 0.00% | High-resolution timestamp when metadata was harvested by the YouNiverse crawler. | `"2019-10-31 20:19:26.270363"` |

---

## 2. Channels Table (`silver/youniverse_channels`)

> **Source File:** `df_channels_en.tsv.gz` (Zenodo record 4814914)  
> **Table Location:** `data/silver/youniverse_channels`  
> **Total Records (10% Sample):** 13,710 channels

| Column Name | Spark Data Type | Description / Semantics | Example Value |
| :--- | :--- | :--- | :--- |
| **`channel_id`** | `string` | Unique 24-character YouTube channel ID (`UC...`). Primary key. | `"UCucot-Zp428OwkyRm2I7v2Q"` |
| **`channel_name`** | `string` | Human-readable YouTube channel name (from `name_cc`). | `"James Charles"` |
| **`subscribers`** | `long` | Verified subscriber count at crawl time (from `subscribers_cc`). Enables subscriber size tiers. | `16100000` |
| **`category`** | `string` | Primary channel category (from `category_cc`). | `"Entertainment"` |
| **`videos`** | `string` | Total video count reported by channel (from `videos_cc`). | `"273"` |
| **`join_date`** | `string` | Channel creation date (`YYYY-MM-DD`). | `"2015-12-02"` |

---

## 3. Weekly Time Series Table (`silver/youniverse_timeseries`)

> **Source File:** `_raw_df_timeseries.tsv.gz` (Zenodo record 4814914)  
> **Table Location:** `data/silver/youniverse_timeseries`  
> **Total Records (10% Sample):** 2,161,369 weekly records across 15,381 channel time series

| Column Name | Spark Data Type | Description / Semantics | Example Value |
| :--- | :--- | :--- | :--- |
| **`channel_id`** | `string` | Unique YouTube channel ID (`UC...`). | `"UCxJWPpPED-J24znoKyKZYjg"` |
| **`category`** | `string` | Category at time series observation. | `"Comedy"` |
| **`datetime`** | `string` | Weekly timestamp (`YYYY-MM-DD 00:00:00`). | `"2017-07-03 00:00:00"` |
| **`views`** | `string` | Cumulative view count up to the week. | `"394085.67"` |
| **`delta_views`** | `string` | Weekly view velocity (views added during the week). | `"191591.11"` |
| **`subs`** | `string` | Cumulative subscriber count. | `"1046.0"` |
| **`delta_subs`** | `string` | Weekly subscriber growth. | `"395.78"` |
| **`videos`** | `string` | Total videos uploaded up to the week. | `"6"` |
| **`delta_videos`** | `string` | Videos uploaded during the week. | `"1"` |
| **`activity`** | `string` | Activity score level. | `"2"` |

---

## 4. Integrity and Preprocessing Notes

1. **Temporal Horizon:** The dataset reflects YouTube state through **late 2019**. In compliance with project guidelines, this data is treated as historical baseline; fresh API snapshots are strictly used for live shortlisted candidates.
2. **Channel Splitting Integrity:** All machine learning splits (train/val/test) MUST group by `channel_id` to prevent data leakage between identical creator upload styles.
3. **Missing Ratings Handling:** The null rate in `like_count` and `dislike_count` correlates with disabled public ratings on select videos. Feature engineering functions must impute with median or flag as unrated rather than dropping the video.
4. **Channel Name Joins:** Downstream gold tables and the Streamlit application join `silver/youniverse_channels` on `channel_id` to provide human-readable channel names alongside channel IDs and direct YouTube URLs.

---

## 5. Canonical Behavioral Metrics

### Engagement Rate (`engagement_rate`)
Defined uniformly in `src/common/engagement.py`:
$$\text{Engagement Rate} = \frac{\sum \text{likes} + \sum \text{dislikes}}{\max(\sum \text{views}, 1.0)}$$
- **Implementation:** `src/common/engagement.py::calculate_engagement_expr` (PySpark Column expression) and `calculate_engagement_rate` (scalar Python function).
- **Consumer Modules:**
  - `src/influencer/features.py` for channel behavioral feature engineering.
  - `src/ranking/backtest.py` for pre-cutoff and post-cutoff evaluation.
  - `src/ranking/score.py` for composite promotion-potential scoring.
  - `scripts/build_gold_cohort.py` for gold scored creators table.
- **Null / Missing Value Rule:** When `like_count` or `dislike_count` are null (disabled ratings), they coalesce to $0.0$; when `views` is 0, engagement rate resolves to $0.0$.

