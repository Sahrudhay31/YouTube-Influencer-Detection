# Domain-Aware YouTube Influencer Detection & Promotion-Potential Ranking

A big-data engineering system built on Apache Hadoop HDFS and Apache Spark (SQL + MLlib) designed to analyze YouTube creators, evaluate domain authority, detect sponsorship activities, and rank creators by **Promotion-Potential Score** for product marketing campaigns.

---

## ⚠️ Honest Framing & Scientific Scope

> **Important Disclosure:** Public YouTube metadata contains **zero sales, conversion, or ROI figures**.  
> The system outputs a **Promotion-Potential Score** (a calibrated statistical estimate of promotional fit, audience alignment, and engagement lift), **not measured sales or revenue ROI**. This repository never claims to measure direct sales or guarantee ROI.

---

## 🏗️ Target Architecture

```
[ Academic Ingestion ]                  [ Live Targeted API Enrichment ]
YouNiverse Dataset (Zenodo)              YouTube Data API v3 (Quota Guard)
          │                                           │ (max 8,000 units/day)
          ▼                                           ▼
   /bda/raw/youniverse/                     /bda/raw/api/dt=YYYY-MM-DD/
  (Metadata & Time Series)                   (30-day Retention TTL)
          │                                           │
          └─────────────────┬─────────────────────────┘
                            ▼
           [ Silver Zone: Partitioned Parquet ]
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
   [ Domain Classification ]   [ Sponsorship & Lift ]
   - Macro/Micro Domain TF-IDF - Heuristic Disclosures
   - Channel Domain Rollup     - Promo Lift vs Organic Baseline
               │                         │
               └────────────┬────────────┘
                            ▼
          [ Channel Features & Influencer Classifier ]
          - Audience Velocity, Upload Consistency
          - Imbalanced Classifier (PR-AUC / ROC-AUC)
                            │
                            ▼
               [ Promotion-Potential Scoring ]
          - Audience Quality & Intent Sampling
          - Multi-tier Ranking & Time-split Backtest
                            │
                            ▼
        [ Gold Zone / Streamlit Decision App ]
```

---

## 📊 Model Registry & Measured Results

All metrics below are automatically populated from real runs in `metrics/` using `scripts/update_readme_metrics.py`. Hand-typed metrics are strictly forbidden.

<!-- MODEL_RESULTS_START -->
| Model Name | Task | Algorithm | Train Acc | Val Acc | Test Acc | Macro F1 | PR-AUC | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| *No model runs recorded yet. Run model training pipelines in Phase 3–5 to populate real metrics.* | - | - | - | - | - | - | - | Pending |
<!-- MODEL_RESULTS_END -->

---

## ⚙️ Configuration

Configuration files are located in `config/`:
- `config/settings.yaml`: Paths, HDFS URIs, random seeds, split ratios (70/15/15), dev sample fractions.
- `config/quota.yaml`: API unit caps (8,000 daily cap, 20 search calls, 1,500 per-run max).
- `config/quota_costs.yaml`: Unit cost per endpoint grounded in official YouTube documentation.
- `config/scoring.yaml`: Calibrated weights for Promotion-Potential Score components.
- `config/domains/taxonomy.yaml`: Hierarchical macro-to-micro domain taxonomy.
- `config/domains/beauty_personal_care.yaml`: Domain keywords, sponsor patterns, and purchase intent phrases.

---

## 🚀 Quickstart & Verification

### 1. Environment Setup
```powershell
# Copy environment template
cp .env.example .env
# Edit .env and supply your YouTube Data API v3 key (keep YT_MODE=dry_run initially)
```

### 2. Run Verification Suite
Run the automated test suite and compliance checks:
```powershell
python scripts/check_all.py
```

This verifies:
1. **Secrets Scan**: Ensures no API keys exist outside `archive/`.
2. **Single Entrypoint**: Confirms only `src/ingestion/yt_client.py` imports `googleapiclient`.
3. **Python Syntax**: Compiles all source files.
4. **Unit Tests**: Runs all Quota Guard (`T-Q1` to `T-Q10`) and Metrics Logger (`T-M1` to `T-M4`) tests.

### 3. Estimate API Cost in Dry-Run
```powershell
python -m src.ingestion.plan --channels 10 --videos-per-channel 10 --comment-videos 3
```

---

## 🛡️ YouTube API Compliance & Privacy Governance

- **Strict Quota Control:** Managed by `src/ingestion/quota_guard.py` with Pacific midnight ledger rollover (`state/quota_ledger.json`).
- **Data Retention Enforcement:** `src/maintenance/purge_api_data.py` enforces deletion of raw API partitions older than 30 days to strictly comply with YouTube Developer Terms.
- **Privacy Hashing:** Commenter channel IDs are irreversibly hashed with `COMMENT_HASH_SALT` for loyalty analysis. Raw usernames and personal identifiers are never stored.

---

## ⚠️ Known Limitations & Assumptions

1. **Historical vs Live Data:** YouNiverse provides a robust historical baseline (2019). Live YouTube API snapshots are used selectively for shortlisted candidates.
2. **Proxy vs Direct Conversion:** Engagement rate, view velocity, and purchase-intent comment ratios serve as proxies for influencer marketing effectiveness, not financial ROI.
3. **Language Scope:** Version 1.0 targets English metadata and comments only.
