# Open Questions & Environmental Audit (Phase 0)

This document records environmental measurements taken on the host system and critical architectural decisions required before proceeding past Phase 1.

---

## 1. Verified Environmental Facts (Host Machine)

| Metric | Measured Value | Analysis / Implication |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 (64-bit) | PowerShell 7 / Windows execution environment. |
| **Python Version** | Python 3.14.7 | Very recent Python release; PySpark native wheels generally target Python 3.9–3.12. Local execution of PySpark requires either Java 8/11/17 or Dockerized Spark containers. |
| **Java (`java -version`)** | **Not Installed / Not on PATH** | Spark 3.5.x strictly requires Java 8, 11, or 17. Local Spark jobs cannot run until OpenJDK or Java 11/17 is installed, or Spark runs inside Docker. |
| **Docker (`docker --version`)** | **Not Installed / Not on PATH** | Docker Desktop or WSL2 Docker daemon is required to run the Hadoop NameNode/DataNode containers (`docker-compose.yml`). |
| **Free Disk Space (C:)** | **39.4 GB Free** (330 GB Used / 42.3 GB Available) | Full YouNiverse compressed dataset + Parquet conversion requires ~150–300 GB. **The host disk cannot accommodate the full dataset.** We MUST use a filtered dev sample (~500 MB to 2 GB) or an external drive. |
| **System RAM** | **16.0 GB RAM** | Sufficient for local development, local Spark sessions (`local[2]` or `local[4]`), and single-domain model training. |
| **CPU Resources** | **16 Logical Processors** | Excellent multi-threading capacity for parallel data processing. |

---

## 2. Blocking Questionnaire (Q-ENV through Q-CLUSTER)

### ❓ DECISION NEEDED: Q-ENV (Environment & Runtime Strategy)
- **What was verified:** Python 3.14.7 is active; Java and Docker are currently not found on system PATH.
- **Options:**
  - **Option A (Recommended for Windows):** Install OpenJDK 11 or 17 and Docker Desktop (with WSL2 backend). This allows Hadoop to run in Docker and Spark to run either locally or inside containers.
  - **Option B (Pure Local Dev Sample Mode):** Install OpenJDK 11 locally; use Local filesystem mode (`file:///...`) for raw/silver zones during initial development until Docker Desktop is launched.
- **My Recommendation:** Install OpenJDK 11 (e.g., Eclipse Temurin 11) and ensure Docker Desktop is running.

---

### ❓ DECISION NEEDED: Q-DATA (YouNiverse Storage & Sample Strategy)
- **What was verified:** Available disk space on drive `C:` is **39.4 GB**. The full Zenodo YouNiverse dataset (`yt_metadata_en.jsonl.gz` + `df_timeseries_en.csv.gz`) requires ~150 GB download and ~300 GB uncompressed/Parquet.
- **Options:**
  - **Option A (Recommended):** Download/extract a bounded dev sample (e.g., first 50,000–100,000 channels matching the target domain) consuming < 5 GB disk space.
  - **Option B:** Provide an external storage drive path (e.g., `D:\` or external SSD with >300 GB free) if full 150 GB ingestion is desired.
- **My Recommendation:** Start with Option A (dev sample fraction configured in `config/settings.yaml`).

---

### ❓ DECISION NEEDED: Q-LICENSE (Zenodo Dataset Terms)
- **Context:** The YouNiverse dataset is hosted on Zenodo (Record 4814914, EPFL / Ribeiro et al.).
- **Action Required:** User must confirm that Zenodo's Creative Commons (CC-BY 4.0 / non-commercial or academic) terms align with the user's project objectives.

---

### ❓ DECISION NEEDED: Q-DOMAIN (Initial Macro & Micro Domain)
- **Recommendation:** **Beauty & Personal Care** (with micro-domains: *Skincare*, *Makeup*, *Haircare*).
- **Language Scope:** English metadata and comments only for v1. Non-English and mixed-language comments are excluded using language detection / character ASCII filtering during text cleaning.

---

### ❓ DECISION NEEDED: Q-INFRA (Kafka Ingestion)
- **Context:** YouTube Data API quota is strictly 10,000 units/day (general) and 100 queries/day (`search.list`). API ingestion is intrinsically rate-limited batch work, not high-throughput unbound streaming.
- **Recommendation:** Decouple Kafka from the core batch path; keep Kafka commented in `docker-compose.yml` for optional streaming demonstration. Store ingestion checkpoints directly in HDFS raw zone.

---

### ❓ DECISION NEEDED: Q-KEY (YouTube API Key)
- **Context:** The key exposed in legacy prototype (`AIzaSyA-...`) must be revoked in Google Cloud Console.
- **Action Required:** User must obtain a new, restricted YouTube Data API v3 key and place it into `.env` as `YOUTUBE_API_KEY=...`. The pipeline runs in `dry_run` mode by default until confirmed.

---

### ❓ DECISION NEEDED: Q-LABELS (Ground Truth Dataset Annotation)
- **Context:** Machine learning models require human ground-truth labels for supervision and honest evaluation:
  1. **Domain Classifier:** ~500 video titles/descriptions labeled into domain categories.
  2. **Sponsorship Detector:** ~300 videos labeled as `sponsored` (1) vs `organic` (0).
  3. **Purchase Intent Model:** ~1,500 comments labeled as `intent` (1) vs `chatter` (0).
- **Action Required:** Confirmation of labeling timeline and format (CSV template in `labels/`).

---

### ❓ DECISION NEEDED: Q-COMPLIANCE (YouTube Developer Terms & Data Retention)
- **Policy Reference:** YouTube Developer Policies require API data (titles, descriptions, comments) to be refreshed or purged after 30 days.
- **Implemented Guard:** `src/maintenance/purge_api_data.py` enforces 30-day automated partition pruning.
- **Question:** Confirm whether retention is strictly ≤ 30 days (standard policy) or if an application for derived metrics amendment will be submitted.

---

### ❓ DECISION NEEDED: Q-CLUSTER (Compute Infrastructure)
- **Scope:** Single development workstation (16 cores, 16 GB RAM) with Spark `local[*]`, or multi-node cluster?
- **Recommendation:** Single workstation with local Spark session for Phases 1–8; multi-node scalability benchmark in Phase 9 if cluster resources become available.
