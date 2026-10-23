# Architecture Decision Record (ADR)

All key architectural decisions for the **Domain-Aware YouTube Influencer Detection & Promotion-Potential Ranking** pipeline are documented here.

---

## ADR-001: Decouple Apache Kafka from Primary Ingestion Path
- **Date:** 2026-10-20
- **Status:** Accepted (User Confirmed in Phase 0)
- **Context:** The legacy prototype pushed live comments to Kafka topics with infinite while loops. However, YouTube Data API v3 enforces a daily unit cap of 10,000 units and 100 queries/day for `search.list`. Real-world API ingestion is strictly rate-limited batch work.
- **Decision:** Comment out Zookeeper and Kafka services from `docker-compose.yml`. Use a direct batch ingestion architecture writing to HDFS raw/silver partitions.
- **Consequences:** Dramatically reduces operational overhead, eliminates memory contention on single workstation, and enforces strict pre-request quota budgeting.

---

## ADR-002: Primary Domain Selection (Beauty & Personal Care)
- **Date:** 2026-10-20
- **Status:** Accepted (User Confirmed in Phase 0)
- **Context:** The project requires a single deep vertical for v1 before multi-domain expansion.
- **Decision:** Focus on **Beauty & Personal Care** with sub-niches: *Skincare*, *Makeup*, and *Haircare*.
- **Consequences:** Domain taxonomy and lexical rules defined in `config/domains/beauty_personal_care.yaml` and `taxonomy.yaml`. English language metadata and comments prioritized.

---

## ADR-003: Python 3.11 Virtual Environment via `uv`
- **Date:** 2026-10-20
- **Status:** Accepted
- **Context:** Host machine has Python 3.14 installed. PySpark 3.5.3 worker processes encounter CPython ABI crashes and infinite recursion on Python 3.14.
- **Decision:** Provision a standalone, user-scoped Python 3.11.17 environment in `.venv/` using `uv`. Automatic `JAVA_HOME` (Adoptium OpenJDK 17) and `PYSPARK_PYTHON` configuration in `src/common/spark_session.py`.
- **Consequences:** Clean, repeatable, non-root execution of Apache Spark with zero environment crashes.

---

## ADR-004: Direct Local Dataset Ingestion for YouNiverse
- **Date:** 2026-10-20
- **Status:** Accepted
- **Context:** User downloaded `yt_metadata_en.jsonl.gz` (13.63 GB) to `<your-downloads-path>/yt_metadata_en.jsonl.gz`. Host disk free space is ~39 GB.
- **Decision:** Ingest directly from local downloads path into Spark DataFrame; sample according to `dev_sample_fraction` (0.01) and `dev_sample_max_rows` (50,000) into partitioned Parquet.
- **Consequences:** Avoids duplicating 13.6 GB across disk drives; prevents disk exhaustion while preserving 100% data fidelity.

---

## ADR-005: 30-Day Automated API Data Pruning
- **Date:** 2026-10-20
- **Status:** Accepted
- **Context:** YouTube Developer Policies require public API data (titles, descriptions, comments) to be refreshed or purged within 30 days.
- **Decision:** Enforce automated partition deletion via `src/maintenance/purge_api_data.py` on partitions older than 30 days. Derived mathematical scores remain compliant.
- **Consequences:** Safe, automated compliance with developer terms; zero risk of stale data leaks.

---

## ADR-006: Ground-Truth Influencer Labeling via Structural Thresholds (Option B)
- **Date:** 2026-10-21
- **Status:** Accepted (User Confirmed in Phase 5)
- **Context:** YouTube metadata lacks explicit ground-truth "influencer" flags. Using sponsorship disclosures alone would create severe label bias against authentic creators who have not yet run commercial partnerships.
- **Decision:** Implement Option B compound ground-truth definition: a creator is labeled positive (`is_influencer = 1`) if they possess a minimum structural scale (≥ 1,000 views across catalog, active upload history) AND either demonstrated sponsorship activity OR high audience engagement efficiency (top 20% engagement rate within domain).
- **Consequences:** Resolves severe class imbalance (positive class prevalence ~19.7%), establishing a realistic, robust machine learning target evaluated by PR-AUC rather than misleading accuracy.

---

## ADR-007: Four-Stage Quota-Guarded API Enrichment & Privacy Hashing
- **Date:** 2026-10-21
- **Status:** Accepted
- **Context:** YouTube Data API v3 enforces an 8,000-unit/day budget and 20 search calls/day. Unrestricted channel polling would deplete quota in minutes and expose commenter PII.
- **Decision:** Filter candidate creators through a 4-stage funnel (Domain Gate → GBT Probability Gate ≥ 0.55 → Reach Gate ≥ 5,000 → Top-N Cap). All commenter channel IDs are irreversibly hashed using SHA-256 with a salt (`COMMENT_HASH_SALT`) before loyalty and authenticity analysis.
- **Consequences:** Preserves 95%+ of daily quota while enriching high-conviction creators. Completely protects viewer privacy per GDPR/CCPA guidelines.

---

## ADR-008: Composite Promotion-Potential Score with Dynamic Weight Renormalisation
- **Date:** 2026-10-21
- **Status:** Accepted
- **Context:** Creators exhibit heterogeneous data completeness (some channels have fresh comment samples, others only historical catalog metadata). Fixed linear weighting would penalize creators missing optional data feeds.
- **Decision:** Architect a 6-component composite score (Domain Fit 25%, Influencer Prob 20%, Audience Authenticity 15%, Promo Lift 15%, Size Tier Efficiency 15%, Consistency 10%) with automated dynamic weight renormalisation: when components are unavailable (e.g., no live comments), the remaining active weights are dynamically rescaled to sum strictly to 1.0.
- **Consequences:** Fair, mathematically rigorous ranking across all channels regardless of enrichment stage, verified by temporal holdout backtesting ($\rho = 0.4585$).

---

## ADR-009: Decoupled Streamlit Dashboard with Precomputed Gold Application Cache
- **Date:** 2026-10-21
- **Status:** Accepted
- **Context:** Launching a local SparkSession inside Streamlit introduces an 8–15 second JVM spin-up delay and causes thread contention on multi-user page reloads.
- **Decision:** Decouple Streamlit completely from Apache Spark. The dashboard (`dashboard.py`, `src/app/`) reads precomputed Gold Parquet and CSV artifacts, utilizing a pure-Python TF-IDF domain predictor and in-memory greedy knapsack optimizer.
- **Consequences:** Instant page transitions (< 100ms), lightweight footprint, zero JVM dependency for end-user exploratory analysis, fully verified by unit tests without Spark (`test_app_imports_without_spark`).

---

## ADR-010: Core Parallelism & Columnar Storage Benchmarking
- **Date:** 2026-10-21
- **Status:** Accepted (Phase 9)
- **Context:** Production scale-out requires empirical evaluation of Spark Catalyst multi-threading efficiency and storage serialization overhead on large-scale feature engineering workloads.
- **Decision:** Implement standardized benchmarking script (`scripts/scalability_benchmark.py`) measuring core parallelism (`local[1]`, `local[2]`, `local[4]`) on heavy 50,000-row window aggregations, and comparative read/write I/O throughput across Raw CSV, Flat Snappy Parquet, and Partitioned Parquet.
- **Consequences:** Demonstrates 12.99x multi-core acceleration on JVM pipelined hash aggregations and 9.80x read throughput boost from columnar Parquet over uncompressed CSV. Results cataloged in `metrics/scalability.csv` and `docs/REPORT_NUMBERS.md`.

---

## ADR-011: Channel-Hash Ingestion of 10% Representative YouNiverse Cohort & Human-Readable Channel Names
- **Date:** 2026-10-23
- **Status:** Accepted (Phase R2)
- **Context:** The legacy prototype used an arbitrary head-of-file slice (~127 channels) devoid of human-readable channel names (`name_cc`) and subscriber counts (`subscribers_cc`). Channels were presented exclusively as cryptic 24-character IDs (`UC...`).
- **Decision:** Ingested the full 10% CRC32-sampled YouNiverse cohort (13,710 channels, 7.14M videos) using streaming Gzip decompression. Merged `name_cc` and `subscribers_cc` into `silver/youniverse_channels`, propagating human-readable creator names (e.g., "Kylie Cosmetics", "James Charles", "Andrea Russett") into gold scored creator artifacts (`scored_creators.parquet`, `scored_creators.csv`) and the Streamlit UI.
- **Consequences:** Eliminates channel ID opacity across all UI tables, cards, and portfolio outputs. 2,615 beauty influencers scored and ranked with verified names and subscriber tiers.

---

## ADR-012: Live YouTube Data API v3 Discovery Path with Pacific Quota Ledger
- **Date:** 2026-10-23
- **Status:** Accepted (Phase R6)
- **Context:** Real-time brand exploration requires discovering fresh, active creators matching product briefs directly from YouTube, while strictly complying with daily quota caps (8,000 units/day) and avoiding secret leakage.
- **Decision:** Implemented `src/discovery/query_builder.py` and `src/discovery/candidate_discovery.py`, calling `YouTubeClient` with `search.list` (bounded by 1 call per brief, 100 units) and batched `channels.list` (1 unit per 50 channels). Returns live channel names (`snippet.title`), live subscriber counts, descriptions, thumbnails, and computes topical focus. Integrated into Streamlit as a dedicated live discovery tab with dry-run quota estimation.
- **Consequences:** Fully operational, quota-guarded live search capability yielding real-time YouTube creators with live names and subscriber metrics.

