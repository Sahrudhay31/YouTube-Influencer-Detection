# REMEDIATION AUDIT — VERIFICATION OF FINDINGS F1 TO F14

> **Audit Date:** 2026-10-23  
> **Audited By:** Antigravity Autonomous Big-Data Engineer  
> **Environment:** Windows 11, PySpark 3.5.3, Python 3.11.17 (`.venv`), Git branch `main`  
> **Methodology:** Every finding from Section 3 of `antigravity_remediation_prompt_beauty.md` was independently verified using deterministic commands and exact source code inspections.

---

## Summary of Findings

| Finding ID | Title / Core Issue | Status | Primary Location |
| :---: | :--- | :---: | :--- |
| **F1** | Plaintext API key in legacy archive; skipped by check_all scan | **CONFIRMED** | `archive/legacy_sentiment_prototype/youtube_producer.py:12` |
| **F2** | Real 64-hex comment salt committed in `.env.example` | **CONFIRMED** | `.env.example:17` |
| **F3** | Personal Windows user path hardcoded in script & ADR | **CONFIRMED** | `scripts/extract_dev_sample.py:16`, `docs/DECISIONS.md:37` |
| **F4** | Head-of-file sequential dev sample (only 127 channels) | **CONFIRMED** | `scripts/extract_dev_sample.py:28-32`, `data/silver/youniverse_metadata` |
| **F5** | Zero human labels in CSVs; weak-label agreement reported as accuracy | **CONFIRMED** | `labels/domain_to_label.csv`, `labels/sponsor_to_label.csv` |
| **F6** | Influencer label threshold mismatch & feature leakage via `video_count` | **CONFIRMED** | `config/influencer.yaml:6-8, 16`, `metrics/model_registry.csv:7` |
| **F7** | GBT promo lift regressor severely overfit / negative $R^2$ (-1.95) | **CONFIRMED** | `metrics/model_registry.csv:11`, `metrics/latest.md:14` |
| **F8** | Overclaim of backtest superiority over baselines | **CONFIRMED** | `metrics/backtest_results.csv:2-4`, `README.md:94-100` |
| **F9** | Scalability benchmark artifact: 12.5x speedup without JVM warm-up | **CONFIRMED** | `scripts/scalability_benchmark.py:63-95`, `metrics/scalability.csv:2-4` |
| **F10** | Backtest crawl-time view distortion & inconsistent engagement definitions | **CONFIRMED** | `src/influencer/features.py:57`, `src/ranking/backtest.py:145` |
| **F11** | HDFS unused in practice; silent local filesystem fallback | **CONFIRMED** | `src/common/spark_session.py:54`, `README.md:14` |
| **F12** | Subscriber counts & weekly time series missing from silver dataset | **CONFIRMED** | `data/silver/`, `config/influencer.yaml:27` |
| **F13** | Quota costs unverified; live API path never executed | **CONFIRMED** | `config/quota_costs.yaml:7-8, 18`, `logs/api_calls.jsonl` |
| **F14** | Duplicate rows in `model_registry.csv`; regression metrics omitted in `latest.md` | **CONFIRMED** | `metrics/model_registry.csv:2-7`, `metrics/latest.md:6-14` |

---

## Detailed Finding Verifications

### F1: Plaintext API Key in Legacy Archive File
- **Status:** **CONFIRMED**
- **Evidence:**
  In `archive/legacy_sentiment_prototype/youtube_producer.py` line 12:
  ```python
  YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', 'AIzaSyA-...[REDACTED]')
  ```
  In `scripts/check_all.py` lines 29–31:
  ```python
  if rel == ".env" or any(rel.startswith(p) for p in ["archive/", ".git/", ".venv/", "venv/", "__pycache__/", "state/", "logs/"]):
      continue
  ```
  Because `archive/` is excluded from the scan in `check_all.py`, the exposed API key in `archive/legacy_sentiment_prototype/youtube_producer.py` bypasses CI secrets checking.

---

### F2: Real 64-Hex Salt in `.env.example`
- **Status:** **CONFIRMED**
- **Evidence:**
  In `.env.example` line 17:
  ```properties
  COMMENT_HASH_SALT=ba06a736e6f19fe0525db725809a29e7843e490e00a760bb9cc34615f94ad178
  ```
  A real 64-character hex string was committed as the default template rather than an empty placeholder or explanatory instruction.

---

### F3: Hardcoded Personal Windows Paths
- **Status:** **CONFIRMED**
- **Evidence:**
  1. `scripts/extract_dev_sample.py` line 16:
     ```python
     source_file = Path(r"C:\Users\SAHRUHDAY CHIRRA\Downloads\yt_metadata_en.jsonl.gz")
     ```
  2. `docs/DECISIONS.md` line 37 (ADR-004):
     ```markdown
     Context: User downloaded yt_metadata_en.jsonl.gz (13.63 GB) to C:\Users\SAHRUHDAY CHIRRA\Downloads\yt_metadata_en.jsonl.gz.
     ```
  Personal Windows user paths are hardcoded in both executable code and project documentation.

---

### F4: Head-of-File Sequential Sampling & 127 Channel Bottleneck
- **Status:** **CONFIRMED**
- **Evidence:**
  1. In `scripts/extract_dev_sample.py` lines 28–32:
     ```python
     with gzip.open(source_file, "rb") as fin, gzip.open(out_file, "wb") as fout:
         for line in fin:
             fout.write(line)
             count += 1
             if count >= max_rows:
                 break
     ```
     The extraction takes the first 50,000 lines from the start of the compressed file rather than a randomized channel-hash sample.
  2. In `config/settings.yaml`, `data.dev_sample_fraction: 0.01` is defined but never referenced by `extract_dev_sample.py`.
  3. Running `pd.read_parquet('data/silver/youniverse_metadata')['channel_id'].nunique()` returns **exactly 127 unique channels** across 50,000 video records. Every subsequent model (domain, influencer, promo lift, backtest) was trained or evaluated on this biased 127-channel cohort.

---

### F5: Zero Human Labels & Weak-Label Accuracy Equivalence
- **Status:** **CONFIRMED**
- **Evidence:**
  1. In `labels/domain_to_label.csv` (500 rows), the `human_label` column has **0 non-null values** (all empty).
  2. In `labels/sponsor_to_label.csv` (300 rows), the `human_is_sponsored` column has **0 non-null values** (all empty).
  3. In `metrics/model_registry.csv` and `metrics/latest.md`, the reported validation accuracy for domain classifiers:
     - Keyword Rule Baseline: **0.9487**
     - Logistic Regression: **0.9131**
     - LinearSVC: **0.9213**
     - Majority Class Baseline: **0.8974**
     Neither machine learning model beats the keyword rule baseline on validation, and reported accuracy reflects agreement with keyword weak labels rather than human ground truth.

---

### F6: Influencer Label Definition Mismatch & Structural Feature Leakage
- **Status:** **CONFIRMED**
- **Evidence:**
  1. In `config/influencer.yaml` lines 6–8:
     ```yaml
     reach_metric: median_views
     reach_threshold: 10000.0
     sponsorship_metric: sponsored_count
     sponsorship_threshold: 1
     ```
     The label definition requires `median_views >= 10000 AND sponsored_count >= 1`.
  2. In `docs/DECISIONS.md` line 56 (ADR-006):
     ```markdown
     Decision: Implement Option B compound ground-truth definition: a creator is labeled positive (is_influencer = 1) if they possess a minimum structural scale (≥ 1,000 views across catalog, active upload history) AND either demonstrated sponsorship activity OR high audience engagement efficiency (top 20% engagement rate within domain).
     ```
     The ADR describes a completely different threshold (≥1,000 views, sponsorship OR top-20% engagement).
  3. `video_count` is included in `feature_columns` (`config/influencer.yaml:16`). Because more uploaded videos directly increases the probability of having at least 1 detected sponsored video, `video_count` structurally leaks the positive label.
  4. In `metrics/model_registry.csv` row 7 (GBT classifier):
     - Train Accuracy: **1.0000**
     - Val Accuracy: **0.8519** (Overfit gap = 0.1481)
     - Channels in train/val/test: 83 / 27 / 17.

---

### F7: GBT Promo Lift Regressor Failure ($R^2 = -1.95$) & Circular Calibration
- **Status:** **CONFIRMED**
- **Evidence:**
  1. In `metrics/model_registry.csv` row 11 (`promo_lift_regressor_gbt`):
     - `n_train: 26, n_val: 12, n_test: 3`
     - `train_r2: 0.9995` vs `val_r2: -1.9548`
     - `train_rmse: 0.0580` vs `val_rmse: 4.8228`
     A negative validation $R^2$ indicates the regressor performs substantially worse than simply predicting the mean.
  2. In `metrics/latest.md` line 14:
     `| promo_lift_regressor_gbt | regression | GBTRegressor |  |  |  |  |  | ✅ | Spearman rank correlation vs composite Promotion-Potential S |`
     The regression metrics ($R^2$, RMSE, MAE) are excluded from the table, masking the model's severe failure.
  3. `README.md` line 89 presents Spearman $\rho = 0.4585$ as "Calibration" against the composite Promotion-Potential Score. However, the composite score itself incorporates promo lift as a 15% component, creating a circular correlation.

---

### F8: Unsubstantiated Backtest Claims Over Baselines
- **Status:** **CONFIRMED**
- **Evidence:**
  In `metrics/backtest_results.csv`:
  ```csv
  method,cutoff_date,n_channels,precision@5,precision@10,ndcg@5,ndcg@10,spearman_rho,spearman_pvalue
  PromotionPotentialScore,2019-01-01,112,0.6,0.3,0.6005,0.62,0.0246,0.7968
  Baseline_MedianViews,2019-01-01,112,0.0,0.3,0.5013,0.4447,0.1085,0.255
  Baseline_Activity,2019-01-01,112,0.4,0.3,0.5739,0.58,0.2617,0.0053
  ```
  1. Precision@10 is identical across all three ranking methods (0.3000).
  2. The Spearman rank correlation for `PromotionPotentialScore` is $\rho = 0.0246$ ($p = 0.7968$, not statistically distinguishable from zero).
  3. `Baseline_Activity` achieved $\rho = 0.2617$ ($p = 0.0053$, statistically significant).
  4. Yet `README.md` line 100 asserts: *"The Promotion-Potential Score outperforms both standard baselines on top-5 sponsor conversion Precision and NDCG ranking quality."*
  5. Furthermore, `docs/DECISIONS.md` line 75 (ADR-008) asserts: *"verified by temporal holdout backtesting ($\rho = 0.4585$)"*, conflating the regressor's circular correlation with the backtest outcome.

---

### F9: Scalability Benchmark Core Speedup Artifact (12.5x on 2 Cores)
- **Status:** **CONFIRMED**
- **Evidence:**
  1. In `metrics/scalability.csv`:
     ```csv
     core_scalability,local[1],1,parquet,50000,127,10.106,1.0,1.0,4947.5
     core_scalability,local[2],2,parquet,50000,127,0.807,12.52,6.26,61936.0
     core_scalability,local[4],4,parquet,50000,127,0.778,12.99,3.25,64286.2
     ```
     `local[2]` records an elapsed time of 0.807s vs 10.106s for `local[1]`, yielding a 12.52x speedup and a parallel efficiency of 6.26 on 2 cores.
  2. In `scripts/scalability_benchmark.py` lines 63–95, `local[1]` is executed first without any prior JVM warmup in the same process, absorbing initial class loading, JIT compilation, and OS file cache warming. `local[2]` and `local[4]` then execute against hot memory and cache.
  3. `README.md` line 117 reports: *"Catalyst multi-threading delivers over 12x acceleration due to pipelined hash aggregation and JVM vectorization"*, presenting a benchmark measurement artifact as real algorithmic acceleration.

---

### F10: Pre-T Crawl-Time View Distortion & Inconsistent Engagement Formulations
- **Status:** **CONFIRMED**
- **Evidence:**
  1. In `src/ranking/backtest.py`, pre-cutoff videos ($upload\_date \le T$) are evaluated using static crawl-time view counts from late 2019. These view counts include post-$T$ organic viewership growth, while post-$T$ videos have shorter lifespans, distorting true relative lift.
  2. Engagement rate is inconsistently computed across modules:
     - In `src/influencer/features.py` lines 57, 66:
       `_total_engagement = sum(like_count + dislike_count)`
       `engagement_rate = _total_engagement / total_views`
     - In `src/ranking/backtest.py` lines 145, 203:
       `engagement_rate = sum(like_count) / sum(view_count)` (dislikes omitted).

---

### F11: Unused HDFS Architecture & Silent Local Fallback
- **Status:** **CONFIRMED**
- **Evidence:**
  1. Docker is not installed on the workstation (`docker : CommandNotFoundException`).
  2. In `src/common/spark_session.py` line 54:
     ```python
     hdfs_uri = "file:///" if (local_mode or os.environ.get("SPARK_LOCAL_MODE") == "1") else get_hdfs_uri()
     ```
  3. In all pipeline entrypoints (`src/classification/domain_classifier.py:76`, `src/influencer/classifier.py:72`, `src/sponsorship/pipeline.py:28`, `src/ranking/score.py:342`), paths are hardcoded to `local("silver", ...)`.
  4. Yet `README.md` line 14 and architecture diagrams present the system as running on `"Hadoop HDFS (Dockerized Data Lake)"`.

---

### F12: Missing Channel Metadata and Time-Series Data
- **Status:** **CONFIRMED**
- **Evidence:**
  1. In `data/silver/`, only `youniverse_metadata` (video table) and derived intermediate profiles exist. There are no tables for `channels` (subscribers) or `timeseries` (weekly subscriber/view velocity).
  2. In `config/influencer.yaml` lines 26–31, channel size tiers are forced to use `median_views` instead of actual channel subscribers because subscriber data was never loaded into silver storage.
  3. `src/ranking/score.py` contains no momentum score component from time-series velocity.

---

### F13: Unverified Quota Costs & Untested Live API Execution
- **Status:** **CONFIRMED**
- **Evidence:**
  1. In `config/quota_costs.yaml` lines 7–8, 18:
     ```yaml
     verified_on: "UNVERIFIED — confirm before live run"
     methods:
       search.list:
         cost_per_call: 100
     ```
     `search.list` is modeled as consuming 100 general quota units, whereas current YouTube API documentation establishes a dedicated search call bucket (~100 calls/day).
  2. The `state/` directory contains no `quota_ledger.json`.
  3. In `logs/api_calls.jsonl`, all 62 recorded requests have `"error": "DRY_RUN"` with status code 0. No live network call has ever been executed against YouTube Data API v3.

---

### F14: Model Registry Duplication & Omission of Regressor Performance
- **Status:** **CONFIRMED**
- **Evidence:**
  1. In `metrics/model_registry.csv`, lines 2–4 and lines 5–7 contain identical duplicate rows for `domain_classifier_logistic_regression`, `domain_classifier_naive_bayes`, and `domain_classifier_linear_svc`.
  2. In `metrics/latest.md`, the Markdown table schema specifies only classification columns:
     ```markdown
     | Model | Task | Algorithm | Train Acc | Val Acc | Test Acc | Val F1 | Val PR-AUC | Overfit | Notes |
     ```
     Regression metrics ($R^2$, RMSE, MAE) are unrendered and empty for `promo_lift_regressor_gbt`.
