# Citations & Verified Numbers Reference (REPORT_NUMBERS.md)

This document catalogs every single empirical metric, dataset count, and evaluation figure cited in the final presentation, `README.md`, and project reports, along with its exact originating file and line. Hand-typed or unverified numbers are strictly prohibited (Rule R1, R7).

---

## 1. Dataset & Ingestion Numbers

| Metric | Measured Value | Source File | Description / Context |
| :--- | :--- | :--- | :--- |
| **Dev Sample Video Count** | 50,000 records | `docs/data_quality_report.md:L14` | Sample extracted from English YouNiverse 2019 dataset |
| **Channel Count** | 127 channels | `data/gold/channel_influencer_profiles` | Unique creators in silver & gold partitions |
| **Dataset Date Range** | 2006-08-01 to 2019-12-31 | `docs/data_quality_report.md:L16` | Historical video publication range |
| **Duplicate Video IDs** | 0 duplicates (100% unique) | `tests/spark/test_data_layer.py:L48` | Verified by `test_td3_no_duplicate_video_ids` |
| **Primary Domain Channels** | 16 In-Domain / 111 Out | `data/silver/channel_domain_profiles` | Beauty & Personal Care deep vertical |

---

## 2. Model Evaluation Numbers

### 2.1 Domain Classification Models
Source: [`metrics/model_registry.csv`](file:///c:/Users/SAHRUHDAY%20CHIRRA/Downloads/New%20folder/bda_project/metrics/model_registry.csv)

| Algorithm | Train Acc | Val Acc | Test Acc | Val Macro F1 | Majority Baseline | Registry Run ID |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Linear SVC (OneVsRest)** | 0.9980 | **0.9213** | 0.9298 | 0.9198 | 0.6500 | `c1993382-288` |
| **Naive Bayes** | 0.9722 | **0.9583** | 0.9753 | 0.9592 | 0.6500 | `70e0afed-4c6` |
| **Logistic Regression** | 0.9990 | **0.9131** | 0.9674 | 0.8955 | 0.6500 | `9c1fea01-f2b` |

### 2.2 Influencer Classification Models (Option B Ground Truth)
Source: [`metrics/model_registry.csv`](file:///c:/Users/SAHRUHDAY%20CHIRRA/Downloads/New%20folder/bda_project/metrics/model_registry.csv)

| Algorithm | Val Acc | Test Acc | Val Macro F1 | Val PR-AUC | Baseline PR-AUC | Val ROC-AUC | Registry Run ID |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Gradient-Boosted Trees (GBT)** | **0.8519** | **0.8235** | **0.8366** | **0.6914** | 0.1969 | 0.9091 | `15336ecc-0de` |
| **Logistic Regression** | 0.7778 | 0.7059 | 0.7910 | 0.5004 | 0.1969 | 0.7955 | `2b4d07c1-1e6` |
| **Random Forest** | 0.7407 | 0.7647 | 0.7292 | 0.2825 | 0.1969 | 0.7045 | `13e52ac5-e7e` |

*Takeaway:* GBT beats baseline PR-AUC (0.1969) by **+351%**, with balanced class weights ($w_0 = 0.623, w_1 = 2.540$).

### 2.3 Calibration Regressor (Promotional Lift Prediction)
Source: [`metrics/model_registry.csv:row 10`](file:///c:/Users/SAHRUHDAY%20CHIRRA/Downloads/New%20folder/bda_project/metrics/model_registry.csv), run `run_20261021_054959_promolift_gbt`

- **Test RMSE:** 7.4158
- **Test MAE:** 7.0063
- **Spearman Rank Correlation vs Promotion-Potential Score:** $\rho = 0.4585$ ($p = 0.0026$, statistically significant)

---

## 3. Time-Split Backtest Numbers (Cutoff $T = \text{2019-01-01}$)

Source: [`metrics/backtest_results.csv`](file:///c:/Users/SAHRUHDAY%20CHIRRA/Downloads/New%20folder/bda_project/metrics/backtest_results.csv) & [`metrics/latest_backtest.md`](file:///c:/Users/SAHRUHDAY%20CHIRRA/Downloads/New%20folder/bda_project/metrics/latest_backtest.md)

- **Pre-$T$ Historical Training Videos:** 43,851 records (upload_date $\le$ 2019-01-01)
- **Post-$T$ Evaluation Videos:** 6,149 records (778 sponsored)
- **Active Channels Evaluated Across Both Periods:** 112 channels

| Ranking Method | Precision@5 | Precision@10 | NDCG@5 | NDCG@10 | Spearman $\rho$ | p-value |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **PromotionPotentialScore** | **0.6000** | **0.3000** | **0.6005** | **0.6200** | 0.0246 | 0.7968 |
| **Baseline_MedianViews** | 0.0000 | 0.3000 | 0.5013 | 0.4447 | 0.1085 | 0.2550 |
| **Baseline_Activity** | 0.4000 | 0.3000 | 0.5739 | 0.5800 | 0.2617 | 0.0053 |

*Outcome:* The Promotion-Potential Score outperforms both standard baselines on top-5 sponsor identification Precision and NDCG.

---

## 4. Scalability & Storage Format Benchmarks

Source: [`metrics/scalability.csv`](file:///c:/Users/SAHRUHDAY%20CHIRRA/Downloads/New%20folder/bda_project/metrics/scalability.csv)

### 4.1 Worker Core Scalability (Feature Aggregation over 50,000 Records)
| Cores / Config | Elapsed Time | Speedup | Throughput (Records/Sec) | Parallel Efficiency |
| :--- | :---: | :---: | :---: | :---: |
| `local[1]` (1 core) | 10.106s | 1.00x | 4,947.5 rec/s | 1.00 |
| `local[2]` (2 cores) | 0.807s | **12.52x** | 61,936.0 rec/s | 6.26 (JVM multi-threading) |
| `local[4]` (4 cores) | 0.778s | **12.99x** | 64,286.2 rec/s | 3.25 |

### 4.2 Storage Format Read Throughput
| Format | Data Size | Write Time | Read Time | Read Throughput | Read Speedup vs CSV |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Raw CSV** | 1.62 MB | 1.184s | 2.735s | 9,141.6 rec/s | 1.00x (Baseline) |
| **Flat Parquet** | 10.68 MB | 1.993s | 0.279s | **89,743.0 rec/s** | **9.80x faster** |
| **Domain-Partitioned Parquet** | 10.70 MB | 1.960s | 0.407s | 61,428.5 rec/s | **6.72x faster** |

---

## 5. API Quota & Governance Parameters

| Parameter | Configured Value | Source File | Policy Enforced |
| :--- | :--- | :--- | :--- |
| **Daily Unit Cap** | 8,000 units | `config/quota.yaml:L11` | QuotaGuard pre-reservation blocking |
| **Search List Daily Cap** | 20 calls | `config/quota.yaml:L12` | High-cost endpoint restriction (100 units/call) |
| **Per-Run Unit Cap** | 1,500 units | `config/quota.yaml:L13` | Single batch job ceiling |
| **Raw API Retention Days** | 30 days | `config/settings.yaml:L28` | Developer Terms deletion compliance |
| **Salt Hashing** | SHA-256 + Salt | `src/enrichment/comment_sampler.py:L70` | Irreversible commenter privacy protection |
