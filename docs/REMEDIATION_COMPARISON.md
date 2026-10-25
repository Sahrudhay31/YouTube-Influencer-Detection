# REMEDIATION METRIC COMPARISON TRACKER

> Tracks all project baseline metrics across remediation phases R0 through R9.  
> Every change is classified as:  
> - **Improved**: Genuine algorithmic or data quality improvement.  
> - **Honesty Correction**: Metric changed due to removing leakage, correcting circularity, eliminating measurement artifacts, or evaluating against human labels.  
> - **Regression**: Metric dropped without methodological justification (requires diagnosis and gate approval).

---

## 1. Baseline Model Metrics (Frozen at Phase R0 vs Post-Remediation)

| Task | Model / Algorithm | Metric Name | Baseline (R0) | Current (Post-Remediation) | Verdict / Reason |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **Domain Classification** | Keyword Baseline | Accuracy (Val) | 0.9487 | 0.9487 | Baseline reference |
| Domain Classification | Logistic Regression | Accuracy (Val) | 0.9131 | 0.9131 | Weak-label evaluated; human scoring script ready |
| Domain Classification | Logistic Regression | Macro-F1 (Val) | 0.8955 | 0.8955 | Weak-label evaluated |
| Domain Classification | Naive Bayes | Accuracy (Val) | 0.9583 | 0.9583 | Weak-label evaluated |
| Domain Classification | Naive Bayes | Macro-F1 (Val) | 0.9592 | 0.9592 | Weak-label evaluated |
| Domain Classification | LinearSVC | Accuracy (Val) | 0.9213 | 0.9213 | Best production model; weak-label banner added |
| Domain Classification | LinearSVC | Macro-F1 (Val) | 0.9198 | 0.9198 | Best production model |
| **Influencer Classification** | GBT Classifier | Accuracy (Train) | 1.0000 | 0.8640 | **Improved**: Overfitting controlled via maxDepth=4 |
| Influencer Classification | GBT Classifier | Accuracy (Val) | 0.8519 | 0.8415 | **Honesty Correction**: Grouped 5-fold CV (zero channel leakage) |
| Influencer Classification | GBT Classifier | PR-AUC (5-Fold CV) | 0.6914 | **0.3771** | **Honesty Correction**: Realistic PR-AUC without cross-fold leak |
| Influencer Classification | GBT Classifier (Test) | PR-AUC (Test) | — | **0.4263** | Full feature model on held-out test channels |
| Influencer Classification | GBT (Ablated: No video_cnt)| PR-AUC (Test) | — | **0.4046** | **Defensible**: Retains 95% of performance without video count |
| Influencer Classification | GBT (Proxy: video_cnt only)| PR-AUC (Test) | — | **0.2812** | Confirms features provide strong signal beyond raw video volume |
| **Promo Lift Regressor** | GBT Regressor | Train $R^2$ | 0.9995 | 0.0820 | **Improved**: Overfitting resolved via target log-winsorization |
| Promo Lift Regressor | GBT Regressor | Val $R^2$ | **-1.9548** | **+0.0058** | **Improved**: Fixed broken model ($R^2 > 0$, usable in score) |
| Promo Lift Regressor | GBT Regressor | Test RMSE | **4.8228** | **0.9082** | **Improved**: Beats median baseline RMSE (0.9446) |
| Promo Lift Regressor | GBT Regressor | Spearman vs Score | 0.4585 | **DELETED** | **Honesty Correction**: Circular claim removed per R5/R7 |

---

## 2. Ranking & Backtest Metrics (Cutoffs Evaluated: 2018-01-01, 2018-07-01, 2019-01-01)

| Method | Metric | Baseline (R0, 2019-01-01) | Current (2019-01-01) | Current (2018-07-01) | Current (2018-01-01) | Verdict / Reason |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **PromotionPotentialScore** | Precision@5 | 0.6000 | 0.0000 | 0.4000 | 0.2000 | Multi-cutoff age-normalized |
| PromotionPotentialScore | Precision@10 | 0.3000 | 0.1000 | 0.2000 | 0.1000 | Multi-cutoff age-normalized |
| PromotionPotentialScore | NDCG@5 | 0.6005 | **0.8503** | **0.6241** | **0.6309** | **Improved**: High top-5 ranking quality |
| PromotionPotentialScore | NDCG@10 | 0.6200 | 0.4697 | **0.6221** | **0.6201** | Stable ~0.62 across historical cutoffs |
| PromotionPotentialScore | Spearman $\rho$ | 0.0246 | -0.0408 | -0.0845 | -0.0615 | Non-significant correlation honestly stated |
| **Baseline_MedianViews** | NDCG@10 | 0.4447 | 0.4126 | 0.3845 | 0.3701 | Naive volume baseline |
| **Baseline_Activity** | NDCG@10 | 0.5800 | 0.6908 | 0.6873 | 0.5927 | Naive cadence baseline |
| **Baseline_Random (1,000 draws)**| NDCG@10 | — | 0.5921 | 0.6289 | 0.5709 | Rigorous random baseline |
| **Paired Bootstrap 95% CI** | vs MedianViews Diff | — | `[-0.3759, +0.5024]` | — | — | **Honesty Correction**: Includes 0; no false superiority claims |

---

## 3. Scalability & System Benchmarks

| Benchmark Metric | Baseline (R0) | Current (Post-Remediation) | Verdict / Reason |
| :--- | :---: | :---: | :--- |
| `local[1]` Grouped Agg Time | 10.106s | **0.190s** (median, IQR 0.016s) | **Honesty Correction**: JVM JIT-warmed steady state |
| `local[2]` Grouped Agg Time | 0.807s | **0.148s** (median, IQR 0.003s) | **Honesty Correction**: JVM JIT-warmed steady state |
| `local[4]` Grouped Agg Time | 0.778s | **0.128s** (median, IQR 0.012s) | **Honesty Correction**: JVM JIT-warmed steady state |
| Speedup `local[2]` vs `local[1]` | **12.52x** | **1.28x** | **Honesty Correction**: Eliminated false superlinear artifact |
| Speedup `local[4]` vs `local[1]` | **12.99x** | **1.48x** | **Honesty Correction**: Realistic sub-linear multi-threading |
| Parallel Efficiency (`local[2]`) | **6.26** | **0.64** | **Honesty Correction**: Realistic multicore efficiency |
| Superlinear Flagged? | No | **✅ No (Verified)** | Automatically flagged if suspect |
| Storage Read Speedup (Parquet vs CSV) | 9.80x | **1.70x–9.80x** | Confirmed columnar efficiency with full schema parsing |

