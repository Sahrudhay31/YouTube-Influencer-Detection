# Changelog

All notable changes to the **Domain-Aware YouTube Influencer Detection & Promotion-Potential Ranking** pipeline are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
