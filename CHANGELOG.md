# Changelog

All notable changes to the **Domain-Aware YouTube Influencer Detection & Promotion-Potential Ranking** pipeline are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Phase 8: Streamlit Application & Interactive Discovery Dashboard] - 2026-10-21

### Added
- **Multi-Page Streamlit Application (`src/app/main.py`, `dashboard.py`)**:
  - Completely rewritten to read precomputed gold tables (Parquet/CSV) with **zero Spark startup delay** on page loads (`T-A1`).
  - Modern dark-mode UI with glassmorphic cards, custom typography, status badges, and interactive Plotly visualizations (`src/app/components.py`).
  - Prominent research and governance disclaimer banner on all views (`"Predicted promotion potential from public data; not measured sales."`).
- **Discovery & Search Page (`src/app/pages_impl/find_influencers.py`)**:
  - Pure-Python semantic domain predictor (`src/app/domain_predictor.py`) classifying product briefs into macro and micro-domains without invoking Spark.
  - Robust handling of empty, whitespace, and odd/corrupted input text (`T-A2`).
  - Multi-tier filtering (Nano, Micro, Macro, Mega), domain focus thresholds, and score sliders.
  - Interactive Greedy Knapsack Portfolio Budget Simulator (`src/app/portfolio_optimizer.py`) optimizing campaign reach and spend allocation per CPM rate card.
  - CSV export for shortlisted candidates.
- **Creator Intelligence Card Page (`src/app/pages_impl/creator_card.py`)**:
  - Searchable channel deep-dive with tier badge and promotion potential score gauge.
  - Interactive radar chart and horizontal bar chart breakdown of the 6 score components.
  - Sponsorship track record: catalog sponsored count, sponsored view multiplier, and promo lift.
  - Audience consistency signals: view volatility (CV), upload cadence, and channel longevity.
  - Partial evidence indicator banner.
- **Model Registry & Governance Page (`src/app/pages_impl/model_results.py`)**:
  - Live inspection of `metrics/model_registry.csv` displaying train, validation, and test metrics across domain and influencer classifiers and regression models (`T-A3`).
  - Zero hardcoded numbers in source code (`T-A4`).
  - Visual model comparison chart against majority baselines.
  - Run inspector displaying confusion matrix heatmaps (`confusion_matrix.csv`), parameters, and metrics JSON.
  - Time-split backtest benchmark comparison table and Plotly bar chart (`metrics/backtest_results.csv`).
- **Pipeline Operations Page (`src/app/pages_impl/pipeline_status.py`)**:
  - Quota ledger monitor: daily units consumed vs cap (8,000 units), search calls vs search cap (20 calls).
  - 30-day retention policy compliance badge (`src/maintenance/purge_api_data.py`).
  - Recent YouTube API audit log viewer (`logs/api_calls.jsonl`).
  - Data lake layer health and record counts across Raw, Silver, and Gold partitions.
- **Phase 8 Smoke Tests (`tests/unit/test_app.py`)**:
  - 5 tests covering T-A1 (app imports without Spark), T-A2 (empty/odd text handling), T-A3 (sample registry rendering), T-A4 (no hardcoded numbers in metrics page), and end-to-end page rendering.

---

## [Phase 7: Promotion-Potential Score, Calibration & Time-Split Backtest] - 2026-10-21

### Added
- **CPM Rate Card Config (`config/rate_card.yaml`)**:
  - Benchmark CPM rates by channel size tier: Nano ($15), Micro ($20), Macro ($25), Mega ($35).
- **Product Fit Scoring Engine (`src/ranking/fit_score.py`)**:
  - Vectorizes product brief using Spark ML Tokenizer, StopWordsRemover, CountVectorizer, and IDF.
  - Computes cosine similarity between brief vector and channel text profile vectors.
- **Promotion-Potential Score Engine (`src/ranking/score.py`)**:
  - Computes 6-component composite score according to `config/scoring.yaml`:
    - Domain/Product Fit (25%)
    - Influencer Probability (20%)
    - Size Tier Efficiency (15%)
    - Audience Authenticity (15%)
    - Promo Lift Track Record (15%)
    - Consistency & Cadence (10%)
  - Dynamic weight renormalisation when components are unavailable.
  - Deducts penalties for authenticity flag breaches (-15 pts) and promo lift decay (-10 pts).
  - Within-domain and within-tier percentile normalization (`percentile_rank`).
- **Calibration Regressor (`src/models/promo_lift_regressor.py`)**:
  - Trained `GBTRegressor` on channel features to predict promotional lift (`run_20261021_054959_promolift_gbt`).
  - Test RMSE = 7.4158, Test MAE = 7.0063.
  - Statistically significant rank alignment with composite Promotion-Potential Score: Spearman $\rho = 0.4585$ ($p = 0.0026$).
- **Time-Split Backtest Evaluation (`src/ranking/backtest.py`)**:
  - Evaluated on temporal holdout with cutoff $T = \text{2019-01-01}$ (asserts historical features use strictly $\le T$).
  - Evaluated on 6,149 post-$T$ videos across 112 active channels.
  - Promotion-Potential Score beats baselines:
    - **Precision@5 = 0.6000** (vs 0.0000 for MedianViews, 0.4000 for Activity).
    - **NDCG@5 = 0.6005** (vs 0.5013 for MedianViews, 0.5739 for Activity).
- **Greedy Portfolio Optimizer (`src/ranking/portfolio.py`)**:
  - Budget-constrained channel selection using score-per-dollar efficiency.
  - Enforces tier diversification caps and CPM cost modeling.
- **Phase 7 Test Suite (`tests/spark/test_ranking.py`)**:
  - Tests T-R1 through T-R6 and portfolio allocator: weight summation, determinism, missing component renormalisation, percentile bounds, temporal leakage guard, and NDCG hand fixtures.

---

## [Phase 6: Live Enrichment Funnel, Comments & Audience Quality] - 2026-10-21

### Added
- **Enrichment Configuration (`config/enrichment.yaml`)**:
  - Four-stage funnel thresholds (domain gate, influencer prob ≥ 0.55, reach ≥ 5,000, cap 50 candidates).
  - Comment sampling parameters (5 videos/channel, 2 pages/video, 200 comments max, 5% label export fraction).
  - 17-pattern purchase-intent keyword regex groups.
  - Loyalty proxy (`loyal_videos_min: 2`) and authenticity thresholds (dup share < 15%, top-1 share < 10%, top-5 share < 30%, spike × 5).
- **Multi-Stage Enrichment Funnel (`src/enrichment/funnel.py`)**:
  - Stage 1: Domain gate — channels must appear in silver domain profiles.
  - Stage 2: Influencer probability gate (GBT score ≥ 0.55).
  - Stage 3: Reach gate — `median_views` or `engagement_rate × channel_age_days` proxy ≥ 5,000.
  - Stage 4: Top-N cap by probability, respecting `max_api_candidates`.
  - Annotates candidates with `funnel_rank`, `funnel_pass_rate`, `enrichment_mode`.
  - Writes shortlist to `data/gold/enrichment_candidates` (`.dryrun` suffix in dry-run mode).
- **YouTube API Client with QuotaGuard (`src/enrichment/youtube_client.py`)**:
  - `QuotaGuard`: per-run unit cap enforced before every API call; raises `QuotaExceededError` on breach.
  - `YouTubeClient`: dual `dry_run` / `live` modes; all calls logged to `logs/api_calls.jsonl` (key never logged).
  - Methods: `get_channel_stats`, `get_top_videos`, `iter_comment_threads` (page-bounded).
  - Exponential back-off with jitter on HTTP 429/5xx errors.
- **Comment Sampler & Purchase-Intent Classifier (`src/enrichment/comment_sampler.py`)**:
  - Reservoir sampling (Algorithm R) for bounded memory across multi-page comment streams.
  - Salted SHA-256 author ID hashing — raw author IDs never written to disk (`COMMENT_HASH_SALT` env var).
  - Rule-based purchase-intent classification (17 keyword regex patterns, configurable threshold).
  - Stratified label export to `labels/purchase_intent_labelled.csv` (balanced intent/non-intent).
- **Audience Quality & Authenticity Module (`src/enrichment/audience_quality.py`)**:
  - `loyal_commenter_share`: fraction of hashed authors appearing in ≥ 2 distinct videos.
  - `duplicate_comment_share`: exact duplicate (author+text) fraction.
  - `top1_commenter_share` / `top5_commenter_share`: commenter concentration metrics.
  - `comment_spike_flag`: any video with > 5× channel-mean comments.
  - `any_authenticity_flag`: OR of all individual flags; channelled to gold table.
  - Saves to `data/gold/audience_quality`.
- **Phase 6 Pipeline Orchestrator (`src/enrichment/pipeline.py`)**:
  - End-to-end runner: funnel → API snapshot → comment sampling → label export → audience quality.
  - Each step is error-isolated; non-fatal failures are captured in summary dict.
  - Returns structured summary with counts, quota units used, and elapsed time.
  - CLI flags: `--mode`, `--max-units`, `--max-candidates`.
- **Phase 6 Smoke Tests (`tests/spark/test_enrichment.py`)**:
  - 10 smoke tests T-E1 through T-E10 covering: QuotaGuard cap enforcement, dry-run safety, SHA-256 hash determinism/one-way property, purchase-intent rules, reservoir sampling reproducibility, duplicate share (zero case), top-1 commenter share, authenticity flag triggering, funnel cap, and loyalty metric zero case.

---

## [Phase 5: Channel Features & Influencer Classification] - 2026-10-21

### Added
- **Influencer Classification Config (`config/influencer.yaml`)**:
  - Encoded Option B ground-truth label definition (`median_views >= 10000.0` AND `sponsored_count >= 1`), strict leakage guard exclusions, and dataset quantile cut points for size tiers.
- **Channel Feature Engineering Engine (`src/influencer/features.py`)**:
  - Aggregates behavioral and temporal signals: `video_count`, `mean_duration`, `engagement_rate`, `view_consistency_cv`, `channel_age_days`, `upload_cadence_days`, `domain_purity`, `in_domain_share`.
  - Assigns size tiers: `nano` (<2,511), `micro` (2,511–8,011), `macro` (8,011–127,745), and `mega` (>=127,745) based on empirical YouNiverse channel quantiles.
  - Handles feature nulls safely with zero row drops.
- **Influencer Classifier Pipeline (`src/influencer/classifier.py`)**:
  - Trains and compares Random Forest, GBT, and Logistic Regression with balanced inverse-frequency class weights ($w_0 = 0.625, w_1 = 2.54$).
  - GBT chosen as top model: Val PR-AUC = 0.6914 (beating baseline 0.1969 by +351%), Val ROC-AUC = 0.9091, Val Macro-F1 = 0.8366, Val Accuracy = 85.19% (beating majority baseline 80.31%).
  - Extracted feature importances: `video_count` (20.5%), `mean_duration` (17.0%), `engagement_rate` (16.3%), `channel_age_days` (13.4%), `view_consistency_cv` (12.8%).
  - Persisted best GBT model to `data/models/influencer_classifier_gbt` and gold table to `data/gold/channel_influencer_profiles`.
- **Phase 5 Smoke Tests (`tests/spark/test_influencer.py`)**:
  - Smoke tests `T-I1` through `T-I5` covering leakage guard column disjointness, exhaustive/mutually exclusive size tiers, PR-AUC baseline beating, class weighting, and null safety.

---

## [Phase 4: Sponsorship Detection & Promo Lift] - 2026-10-20

### Added
- **Sponsorship Rule Configuration (`config/sponsorship.yaml`)**:
  - Declarative patterns for disclosure phrases, affiliate links, promo codes, UTM parameters, candidate brands, and minimum video thresholds.
- **Sponsorship Detection Engine (`src/sponsorship/detector.py`)**:
  - Video-level regex-based detection across titles, descriptions, and tags.
  - Extracts evidence fields: `has_disclosure`, `has_affiliate_link`, `has_promo_code`, `has_utm`, `is_sponsored`.
- **Channel Promo Lift Calculator (`src/sponsorship/promo_lift.py`)**:
  - Computes `sponsored_rate`, `sponsored_count`, `nonsponsored_count`, and `promo_lift = median(views_sponsored) / median(views_nonsponsored)`.
  - Enforces strict null returns (never 0) when fewer than 3 videos exist on either side, with zero-division protection.
- **Sponsorship Pipeline Runner (`src/sponsorship/pipeline.py`)**:
  - Ingests silver video dataset, persists video-level features to `data/silver/sponsorship_video_features`, and saves channel metrics to `data/silver/channel_sponsorship_metrics`.
  - Identified 5,625 sponsored videos (11.25%) across 50,000 records, and valid promo lift across 41 qualifying channels (median lift: 1.258).
- **Stratified Human Label Export (`scripts/export_sponsor_label_sample.py`)**:
  - Exported 300-video sample to `labels/sponsor_to_label.csv` for human verification.
- **Smoke Tests (`tests/spark/test_sponsorship.py`)**:
  - Smoke tests `T-S1` through `T-S4` covering positive/negative handwritten fixtures, null on low sample size, hand-computed value match, and division-by-zero protection.

---

## [Phase 3: Domain Taxonomy & Domain Classification] - 2026-10-20

### Added
- **Domain Taxonomy & Config (`config/domains/taxonomy.yaml`, `config/domains/beauty_personal_care.yaml`)**:
  - Hierarchical macro-to-micro categorization for Beauty & Personal Care (Skincare, Makeup, Haircare, Nail Art, Fragrance, Personal Hygiene).
  - Explicit mapping to YouNiverse `Howto & Style` and related category metadata.
- **Stratified Human Label Sample (`labels/domain_to_label.csv`)**:
  - 500-video balanced sample exported via `scripts/export_domain_label_sample.py` for ground truth validation.
- **Text Preprocessing Engine (`src/classification/text_cleaner.py`)**:
  - Native Spark SQL cleaning (URL stripping, emoji normalization, punctuation removal, whitespace collapsing, and description truncation).
- **Channel-Isolated Dataset Splitter (`src/classification/dataset_splitter.py`)**:
  - Grouped channel splitting ensuring zero channel leakage across train (28,156), val (14,596), and test (7,248) splits.
- **Benchmark Baselines (`src/classification/baselines.py`)**:
  - Majority-class baseline (val accuracy = 89.74%).
  - Keyword-rule matching baseline (val accuracy = 94.87%, macro-F1 = 83.09%).
- **PySpark ML Classification Pipeline (`src/classification/domain_classifier.py`)**:
  - Tokenizer -> StopWordsRemover -> CountVectorizer -> IDF -> Classifier pipeline.
  - Trained and compared Logistic Regression, Naive Bayes, and LinearSVC.
  - Naive Bayes selected as best regularized model (Train Acc: 97.22%, Val Acc: 95.83%, Test Acc: 97.53%, Val Macro-F1: 95.92%).
  - Best model pipeline saved to `data/models/domain_classifier_naive_bayes`.
- **Channel Domain Roll-up (`src/classification/channel_rollup.py`)**:
  - Computes channel-level primary domain, in-domain video share, and domain purity bounded in [0, 1].
  - Saved to `data/silver/channel_domain_profiles`.
- **Phase 3 Smoke Tests (`tests/spark/test_domain_classifier.py`)**:
  - Smoke tests `T-C1` through `T-C6` all verified passing.

---

## [Phase 2: Infrastructure and Data Layer] - 2026-10-20

### Added
- **YouNiverse Dev Sample Extractor (`scripts/extract_dev_sample.py`)**:
  - Deterministic 50,000-row streaming extractor reading from raw `yt_metadata_en.jsonl.gz`.
- **YouNiverse Ingestion Engine (`src/ingestion/load_youniverse.py`)**:
  - PySpark batch conversion from raw JSONL Gzip to partitioned Silver Parquet (`data/silver/youniverse_metadata`).
  - Supports `--full`, `--local`, and `--overwrite` with zero silent fallbacks.
  - Strict round-trip row count verification.
- **Spark Test Suite (`tests/spark/test_data_layer.py`)**:
  - Comprehensive smoke test suite covering T-D1 through T-D6 (round-trip, row counts, duplicate checks, cap validation, idempotency, and loud failure on bad URIs).
- **Data Documentation**:
  - `docs/data_dictionary.md`: Complete column definitions, types, nullability, and semantics.
  - `docs/data_quality_report.md`: Exact statistics across 50,000 rows (0 duplicate IDs, 127 channels, 15 categories, 2.24% missing like/dislike counts).

### Changed
- **Spark Session Configuration (`src/common/spark_session.py`)**:
  - Added Windows environment auto-detection for OpenJDK 17, `HADOOP_HOME`, and `PYSPARK_PYTHON` interpreter parity.
- **Verification Harness (`scripts/check_all.py`)**:
  - Updated to safely scan and verify all 20 unit and Spark test cases automatically.

---

## [Phase 1: Foundation, Safety, and Quota Guard] - 2026-10-20

### Added
- **Quota Guard System (`src/ingestion/quota_guard.py`)**:
  - Implemented thread-safe `QuotaGuard` with ledger tracking in `state/quota_ledger.json`.
  - Configured Pacific Midnight (`America/Los_Angeles`) date rollover and daily cap (8,000 units).
  - Pre-request unit reservation enforcing `QuotaBudgetExceeded` before network calls.
  - Independent cap tracking for `search.list` calls.
- **YouTube Client Gateway (`src/ingestion/yt_client.py`)**:
  - Established single entrypoint for `googleapiclient`.
  - 50-item automatic batching for `channels.list` and `videos.list`.
  - Dry-run mode by default with pre-flight cost estimation.
- **Metrics Logger & Registry (`src/common/metrics_logger.py`)**:
  - Append-only model registry tracking all 32 required audit columns.
  - Automatic validation ensuring non-NaN/missing accuracy numbers.
  - Per-run metric directory structure (`metrics/runs/<run_id>/`).
- **Data Pruning Utility (`src/maintenance/purge_api_data.py`)**:
  - Automated 30-day API snapshot partition purger for YouTube Terms compliance.
- **Automated Verification Harness (`scripts/check_all.py`)**:
  - Cross-platform verification script validating secrets leaks, single-entrypoint compliance, Python compilation, and unit test suites.
- **Unit Test Suite (`tests/unit/`)**:
  - 10 Quota Guard tests (`test_tq1_reserve_increments_ledger` to `test_tq10_purge_respects_retention`).
  - 4 Model Metrics Logger tests (`test_tm1` to `test_tm4`).
- **Documentation**:
  - `docs/AUDIT.md`: Detailed audit verifying findings A1–A10 against legacy prototype.
  - `docs/OPEN_QUESTIONS.md`: Comprehensive environmental facts (OS, Java, Docker, Disk, RAM) and questionnaire.
  - `docs/compliance.md`: YouTube API Developer Policy governance overview.
  - `.env.example`: Secure environment configuration template with zero exposed secrets.

### Changed
- Quarantined legacy prototype files into `archive/legacy_sentiment_prototype/`.
- Updated `.gitignore` to prevent leaking API keys, large datasets, model weights, local state, and execution logs.
- Refactored `README.md` to represent honest promotion-potential scoring architecture.

### Removed
- **Eliminated synthetic comment injection**: Completely removed `publish_fallback_comments_for_query` and `INFLUENCER_COMMENTS_MAP`.
- Removed obsolete deep-learning dependencies (`transformers`, `gliner`, `torch`, `clickhouse-connect`).
