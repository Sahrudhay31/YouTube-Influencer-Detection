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
- **Context:** User downloaded `yt_metadata_en.jsonl.gz` (13.63 GB) to `C:\Users\SAHRUHDAY CHIRRA\Downloads\yt_metadata_en.jsonl.gz`. Host disk free space is ~39 GB.
- **Decision:** Ingest directly from local downloads path into Spark DataFrame; sample according to `dev_sample_fraction` (0.01) and `dev_sample_max_rows` (50,000) into partitioned Parquet.
- **Consequences:** Avoids duplicating 13.6 GB across disk drives; prevents disk exhaustion while preserving 100% data fidelity.

---

## ADR-005: 30-Day Automated API Data Pruning
- **Date:** 2026-10-20
- **Status:** Accepted
- **Context:** YouTube Developer Policies require public API data (titles, descriptions, comments) to be refreshed or purged within 30 days.
- **Decision:** Enforce automated partition deletion via `src/maintenance/purge_api_data.py` on partitions older than 30 days. Derived mathematical scores remain compliant.
