# REMEDIATION METRIC COMPARISON TRACKER

> Tracks all project baseline metrics across remediation phases R0 through R9.  
> Every change is classified as:  
> - **Improved**: Genuine algorithmic or data quality improvement.  
> - **Honesty Correction**: Metric changed due to removing leakage, correcting circularity, eliminating measurement artifacts, or evaluating against human labels.  
> - **Regression**: Metric dropped without methodological justification (requires diagnosis and gate approval).

---

## 1. Baseline Model Metrics (Frozen at Phase R0)

| Task | Model / Algorithm | Metric Name | Baseline (R0) | Current (Post-Remediation) | Verdict / Reason |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **Domain Classification** | Keyword Baseline | Accuracy (Val) | 0.9487 | — | Baseline reference |
| Domain Classification | Logistic Regression | Accuracy (Val) | 0.9131 | — | Pending R4 human labels |
| Domain Classification | Logistic Regression | Macro-F1 (Val) | 0.8955 | — | Pending R4 human labels |
| Domain Classification | Naive Bayes | Accuracy (Val) | 0.9583 | — | Pending R4 human labels |
| Domain Classification | Naive Bayes | Macro-F1 (Val) | 0.9592 | — | Pending R4 human labels |
| Domain Classification | LinearSVC | Accuracy (Val) | 0.9213 | — | Pending R4 human labels |
| Domain Classification | LinearSVC | Macro-F1 (Val) | 0.9198 | — | Pending R4 human labels |
| **Influencer Classification** | GBT Classifier | Accuracy (Train) | 1.0000 | — | ⚠️ Baseline severe overfit |
| Influencer Classification | GBT Classifier | Accuracy (Val) | 0.8519 | — | Pending R5 un-leaked CV |
| Influencer Classification | GBT Classifier | PR-AUC (Val) | 0.6914 | — | Pending R5 un-leaked CV |
| Influencer Classification | Random Forest | Accuracy (Val) | 0.7407 | — | Pending R5 un-leaked CV |
| Influencer Classification | Random Forest | PR-AUC (Val) | 0.2825 | — | Pending R5 un-leaked CV |
| Influencer Classification | Logistic Regression | Accuracy (Val) | 0.7778 | — | Pending R5 un-leaked CV |
| Influencer Classification | Logistic Regression | PR-AUC (Val) | 0.5004 | — | Pending R5 un-leaked CV |
| **Promo Lift Regressor** | GBT Regressor | Train $R^2$ | 0.9995 | — | Baseline severe overfit |
| Promo Lift Regressor | GBT Regressor | Val $R^2$ | **-1.9548** | — | ⚠️ Baseline model failure |
| Promo Lift Regressor | GBT Regressor | Val RMSE | **4.8228** | — | Baseline model failure |
| Promo Lift Regressor | GBT Regressor | Spearman vs Score | 0.4585 | — | ⚠️ Circular evaluation |

---

## 2. Ranking & Backtest Metrics (Cutoff $T = \text{2019-01-01}$)

| Method | Metric | Baseline (R0) | Current (Post-Remediation) | Verdict / Reason |
| :--- | :--- | :---: | :---: | :--- |
| **PromotionPotentialScore** | Precision@5 | 0.6000 | — | Pending R7 backtest |
| PromotionPotentialScore | Precision@10 | 0.3000 | — | Pending R7 backtest |
| PromotionPotentialScore | NDCG@5 | 0.6005 | — | Pending R7 backtest |
| PromotionPotentialScore | NDCG@10 | 0.6200 | — | Pending R7 backtest |
| PromotionPotentialScore | Spearman $\rho$ | 0.0246 | — | Baseline non-significant ($p=0.7968$) |
| **Baseline_Activity** | Precision@10 | 0.3000 | — | Baseline reference |
| Baseline_Activity | Spearman $\rho$ | 0.2617 | — | Baseline significant ($p=0.0053$) |
| **Baseline_MedianViews** | Precision@10 | 0.3000 | — | Baseline reference |
| Baseline_MedianViews | Spearman $\rho$ | 0.1085 | — | Baseline reference |

---

## 3. Scalability & System Benchmarks

| Benchmark Metric | Baseline (R0) | Current (Post-Remediation) | Verdict / Reason |
| :--- | :---: | :---: | :--- |
| `local[1]` Grouped Agg Time | 10.106s | — | Pending R8 warm-up repeats |
| `local[2]` Grouped Agg Time | 0.807s | — | Pending R8 warm-up repeats |
| Speedup `local[2]` vs `local[1]` | **12.52x** | — | ⚠️ Baseline measurement artifact |
| Parallel Efficiency (`local[2]`) | **6.26** | — | ⚠️ Superlinear artifact |
| CSV Read Time (25k rows) | 2.735s | — | Pending R8 benchmark |
| Flat Parquet Read Time | 0.279s | — | Pending R8 benchmark |
| Partitioned Parquet Read Time | 0.407s | — | Pending R8 benchmark |
