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

## 2. Integrity and Preprocessing Notes

1. **Temporal Horizon:** The dataset reflects YouTube state through **late 2019**. In compliance with project guidelines, this data is treated as historical baseline; fresh API snapshots are strictly used for live shortlisted candidates.
2. **Channel Splitting Integrity:** All machine learning splits (train/val/test) MUST group by `channel_id` to prevent data leakage between identical creator upload styles.
3. **Missing Ratings Handling:** The 2.24% null rate in `like_count` and `dislike_count` correlates with disabled public ratings on select videos. Feature engineering functions must impute with median or flag as unrated rather than dropping the video.
