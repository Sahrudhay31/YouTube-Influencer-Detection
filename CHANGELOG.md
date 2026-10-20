# Changelog

All notable changes to the **Domain-Aware YouTube Influencer Detection & Promotion-Potential Ranking** pipeline are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
