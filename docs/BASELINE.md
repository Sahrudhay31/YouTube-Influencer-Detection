# BASELINE FREEZE — PRE-REMEDIATION

> **Freeze Timestamp:** 2026-10-23T11:10:00+05:30  
> **Git Commit:** `4bef4c9399935eab98686b284f7134f4a5de2a35`  
> **Git Tag:** `pre-remediation`  
> **Snapshots Created:**  
> - `metrics/baseline_pre_remediation/`  
> - `docs/baseline_config/`  

---

## 1. System & Runtime Environment

| Component | Verified Specification | Command Source |
| :--- | :--- | :--- |
| **Operating System** | Microsoft Windows 11 Home Single Language | `Get-CimInstance Win32_OperatingSystem` |
| **Virtualenv Python** | Python 3.11.17 (`.venv/Scripts/python.exe`) | `.\.venv\Scripts\python.exe --version` |
| **Host System Python** | Python 3.14.7 | `python --version` |
| **Apache Spark** | PySpark 3.5.3 | `python -c "import pyspark; print(pyspark.__version__)"` |
| **Java JDK** | OpenJDK 17.0.20.1 (Temurin-17.0.20.1+1) | `java -version` |
| **CPU Architecture** | 8 physical cores, 16 logical processors | `Get-CimInstance Win32_Processor` |
| **System Memory** | 16.05 GB total RAM (~477 MB free physical at measurement) | `Get-CimInstance Win32_OperatingSystem` |
| **Disk Space (C:)** | 106.19 GB Free / 248.30 GB Used | `Get-PSDrive C` |
| **Docker** | **Not installed / not in PATH** | `docker : CommandNotFoundException` |

---

## 2. Test Suite Execution (`python scripts/check_all.py`)

Executed on `2026-10-23`:
```
============================================================
 BDA Project Phase Gate Verification (check_all)
============================================================
[1/4] Running secrets scan...
  [OK] Secrets scan passed: No API keys found outside archive/.
[2/4] Running single-entrypoint check for googleapiclient...
  [OK] Single-import check passed: Only src/ingestion/yt_client.py imports googleapiclient.
[3/4] Running Python compilation / syntax checks...
  [OK] All Python files compiled cleanly.
[4/4] Running unit tests via pytest...
  [OK] All unit tests passed.
============================================================
[SUCCESS] ALL CHECKS PASSED!
================== 57 passed, 1 warning in 93.23s (0:01:33) ===================
```
- **Total Tests:** 57 collected
- **Passed:** 57 (100%)
- **Failed:** 0
- **Warnings:** 1 (DeprecationWarning: distutils in `pyspark.ml.image`)

---

## 3. Baseline Model Metrics (from `metrics/model_registry.csv`)

### 3.1 Domain Classification (Binary: `beauty_personal_care` vs `out_of_domain`)
*Note: Evaluated against keyword/rule weak labels (0 human labels in `labels/domain_to_label.csv`).*
- **Majority Class Baseline Accuracy:** 0.8974
- **Keyword Baseline Accuracy:** 0.9487

| Model / Algorithm | Train Acc | Val Acc | Test Acc | Val Macro-F1 | Notes / Warnings |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `domain_classifier_logistic_regression` | 0.9990 | 0.9131 | 0.9674 | 0.8955 | ⚠️ SUSPICIOUS: Train Acc > 0.98 |
| `domain_classifier_naive_bayes` | 0.9722 | 0.9583 | 0.9753 | 0.9592 | Agreement with weak labels |
| `domain_classifier_linear_svc` | 0.9980 | 0.9213 | 0.9298 | 0.9198 | ⚠️ SUSPICIOUS: Train Acc > 0.98 |

### 3.2 Influencer Classification (`is_influencer`)
*Note: Evaluated against structural threshold definition Option B on 127 total channels (83 train / 27 val / 17 test).*
- **Baseline PR-AUC (Prevalence):** 0.1969

| Model / Algorithm | Train Acc | Val Acc | Test Acc | Val Macro-F1 | Val PR-AUC | Notes / Warnings |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `influencer_classifier_random_forest` | 0.9759 | 0.7407 | 0.7647 | 0.7292 | 0.2825 | ⚠️ OVERFIT: Gap = 0.2352 |
| `influencer_classifier_gbt` | 1.0000 | 0.8519 | 0.8235 | 0.8366 | 0.6914 | ⚠️ OVERFIT: Gap = 0.1481; Train Acc = 1.0 |
| `influencer_classifier_logistic_regression` | 0.7470 | 0.7778 | 0.7059 | 0.7910 | 0.5004 | Baseline model |

### 3.3 Promotional Lift Regressor (`promo_lift_regressor_gbt`)
*Note: Trained on small cohort of 41 channels with non-null lift (n_train=26, n_val=12, n_test=3).*

| Metric | Train Value | Val Value | Test Value | Assessment |
| :--- | :---: | :---: | :---: | :--- |
| **$R^2$** | 0.9995 | **-1.9548** | — | **Severe failure ($R^2 < 0$) — worse than predicting mean** |
| **RMSE** | 0.0580 | **4.8228** | 7.4158 | Extreme generalization error |
| **MAE** | 0.0485 | **3.6183** | — | Large prediction divergence |
| **Spearman $\rho$ vs Composite Score** | — | — | 0.4585 ($p=0.0026$) | **Circular evaluation** (composite score contains promo lift) |

---

## 4. Baseline Ranking & Time-Split Backtest (`metrics/backtest_results.csv`)

*Cutoff Date $T = \text{2019-01-01}$, 112 channels, 6,149 post-$T$ videos.*

| Ranking Method | Precision@5 | Precision@10 | NDCG@5 | NDCG@10 | Spearman $\rho$ | p-value |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **PromotionPotentialScore** | **0.6000** | **0.3000** | **0.6005** | **0.6200** | 0.0246 | 0.7968 |
| **Baseline_MedianViews** | 0.0000 | **0.3000** | 0.5013 | 0.4447 | 0.1085 | 0.2550 |
| **Baseline_Activity** | 0.4000 | **0.3000** | 0.5739 | 0.5800 | **0.2617** | **0.0053** |

*Key Findings:*
- **Precision@10 is tied** across all methods at 0.3000.
- **Spearman correlation for PromotionPotentialScore is non-significant** ($\rho = 0.0246, p = 0.7968$).
- **Baseline_Activity achieves higher and statistically significant rank correlation** ($\rho = 0.2617, p = 0.0053$).

---

## 5. Baseline Scalability & Storage Performance (`metrics/scalability.csv`)

### 5.1 Worker Core Scalability (50,000 Records, No Warm-Up)
| Worker Cores | Time (seconds) | Throughput (rec/s) | Speedup vs `local[1]` | Parallel Efficiency | Artifact Note |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `local[1]` | 10.106s | 4,947.5 | 1.00x | 1.00 | Cold JVM run (un-warmed) |
| `local[2]` | 0.807s | 61,936.0 | **12.52x** | **6.26** | **Superlinear artifact (warm JVM & OS cache)** |
| `local[4]` | 0.778s | 64,286.2 | **12.99x** | **3.25** | Un-warmed benchmark artifact |

### 5.2 Storage Format I/O Benchmark (25,000 Records)
| Storage Format | Write Time (s) | Write Throughput | Read Time (s) | Read Throughput | Read Speedup vs CSV |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Raw CSV** | 1.942s | 12,876.3 rec/s | 2.735s | 9,141.6 rec/s | 1.00x (baseline) |
| **Flat Parquet (Snappy)** | 1.487s | 16,812.8 rec/s | 0.279s | 89,743.0 rec/s | 9.80x faster |
| **Domain-Partitioned Parquet** | 2.270s | 11,012.8 rec/s | 0.407s | 61,428.5 rec/s | 6.72x faster |

---

## 6. Baseline Data Layer State

- **Current Dev Sample:** 50,000 video records derived from head-of-file sequential scan (`scripts/extract_dev_sample.py`).
- **Channel Diversity:** Exactly **127 unique channels** in `data/silver/youniverse_metadata`.
- **Loaded Tables:** Video metadata only (`youniverse_metadata`, `channel_domain_profiles`, `sponsorship_video_features`, `channel_sponsorship_metrics`).
- **Missing Tables:** No subscriber counts (`channels` table missing), no weekly growth/time-series data (`timeseries` table missing).
- **HDFS Status:** Fallback to local filesystem (`file:///`). Docker is not installed on the host.
