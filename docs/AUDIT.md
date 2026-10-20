# AUDIT REPORT: Legacy Sentiment Prototype vs Target Big-Data Architecture

> **Audit Date:** 2026-10-20  
> **Auditor:** Big Data Analytics Engineering Agent  
> **Repository:** `bda_project`  
> **Status:** All findings re-verified on active workspace files. Legacy code moved to `archive/legacy_sentiment_prototype/`.

---

## 1. Executive Summary

The legacy prototype was an exploratory stream processing pipeline designed to monitor social media comments using HuggingFace NLP models (GLiNER, DistilBERT) with streaming ingestion into Kafka and Apache Spark.

The re-verification audit confirms that:
1. **100% of reported metrics in the prototype were derived from synthetic fallback comments** generated whenever the YouTube API returned no results or ran out of quota.
2. A raw Google Cloud YouTube Data API key was hardcoded in `youtube_producer.py`.
3. The legacy NLP architecture loaded heavy zero-shot transformer models on per-row PySpark UDFs, silently falling back to a local disk write whenever HDFS was unavailable.
4. The project scope has been refocused from subjective sentiment ("sellout/scam") to an objective, measurable **Domain-Aware Influencer Detection & Promotion-Potential Ranking** system.

---

## 2. Re-Verified Audit Findings (A1 – A10)

| Finding ID | Component | Exact Location | Verified Behavior | Remediation / Action Taken |
| :--- | :--- | :--- | :--- | :--- |
| **A1** | API Security | `archive/legacy_sentiment_prototype/youtube_producer.py:12` | `YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', 'AIzaSyA-...[REDACTED]')`<br>Hardcoded default exposed in repo. | Key quarantined in `archive/`. Scanned repo with `scripts/check_all.py` (0 occurrences in active code). User notified to revoke immediately in Google Cloud Console. Active code reads strictly from `.env` via `src/ingestion/quota_guard.py`. |
| **A2** | Data Integrity | `archive/legacy_sentiment_prototype/youtube_producer.py:281-320` | `publish_fallback_comments_for_query()` injects synthetic strings into Kafka topic `raw-social` with `video_id: f"influencer_v_{abs(hash(query)) % 100000}"`. | **Completely eliminated.** The new pipeline strictly stops when quota is exhausted; synthetic data is forbidden outside `tests/fixtures/`. |
| **A3** | Artifact Provenance | `archive/legacy_sentiment_prototype/powerbi_export/live_feed_summary.csv` | Re-verified via Python: `792 / 792` rows (100%) start with `influencer_v_`. | Quarantined in `archive/legacy_sentiment_prototype/powerbi_export/` with a prominent warning: *"Synthetic data, do not cite"*. |
| **A4** | Quota Control | `archive/legacy_sentiment_prototype/youtube_producer.py:329-348` | Infinite while loop querying 25 queries every 20s with no quota accounting, no backoff, and a catch-all `except Exception: pass`. | Replaced with `src/ingestion/quota_guard.py` & `yt_client.py` adhering to daily unit cap (8,000 units), Pacific midnight ledger rollover, and batched 50-ID fetches. |
| **A5** | Distributed Compute | `archive/legacy_sentiment_prototype/spark_processor.py:31-44, 437-452` | Loaded DeBERTa, GLiNER, and DistilBERT inside per-row PySpark UDFs; silently caught HDFS save failures at line 444 and routed data to a local folder. | Replaced with Spark MLlib pipelines (TF-IDF, LinearSVC, LogisticRegression, GBT). HDFS failures are loud and fatal. |
| **A6** | Dependencies | `requirements.txt` | Listed `torch`, `transformers`, `gliner`, `clickhouse-connect`; `init_db.sql` was unreferenced. | Pruned unneeded deep-learning and DB dependencies. Pinned to lightweight, verified big data stack. |
| **A7** | Infrastructure | `docker-compose.yml` | Configured Zookeeper, Kafka, Hadoop NameNode, and DataNode (`bde2020/hadoop-*:2.0.0-hadoop3.2.1-java8`). | Maintained Hadoop HDFS configuration; recommended decoupling Kafka for batch quota-restricted ingestion. |
| **A8** | Engineering Rigor | Repository-wide | Zero unit tests, zero regression tests, no model metric tracking, no `.env.example`. | Added full testing harness: `tests/unit/test_quota_guard.py` (T-Q1 to T-Q10), `test_metrics_logger.py` (T-M1 to T-M4), automated `scripts/check_all.py`, `.env.example`, and `config/settings.yaml`. |
| **A9** | Taxonomy & Domain | `archive/legacy_sentiment_prototype/domain_config.yaml` | Mixed product categories with emotional sentiment tags (`scam`, `overhyped`, `sellout`). | Designed clean taxonomy in `config/domains/taxonomy.yaml` and human/agent tagged lexicon in `config/domains/beauty_personal_care.yaml`. |
| **A10** | UI & Visualization | `archive/legacy_sentiment_prototype/dashboard.py` | 38 KB Streamlit dashboard reading static synthetic CSV exports and launching local PySpark sessions inside UI threads. | Redesigned for Phase 8: reads pre-aggregated Parquet outputs from HDFS/local silver zone without spawning Spark sessions inside Streamlit. |

---

## 3. Quarantined Components

The following files have been safely isolated into `archive/legacy_sentiment_prototype/`:
- `youtube_producer.py`
- `spark_processor.py`
- `dashboard.py`
- `domain_config.yaml`
- `init_db.sql`
- `powerbi_export/*.csv`
