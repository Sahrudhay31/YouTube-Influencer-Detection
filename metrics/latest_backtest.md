# Multi-Cutoff Time-Split Backtest Evaluation

> **Cutoffs Evaluated:** 2018-01-01, 2018-07-01, 2019-01-01  
> **Baselines:** Median Views, Activity, Random (1,000 draws)  
> **Relevance Definition:** Post-T sponsored video with post_promo_lift >= 1.0 (graded 0..3)  

| Cutoff Date | Method | Precision@5 | Precision@10 | NDCG@5 | NDCG@10 | Spearman rho |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `2018-01-01` | **PromotionPotentialScore** | 0.2000 | 0.1000 | 0.6309 | 0.6201 | -0.0615 |
| `2018-01-01` | **Baseline_MedianViews** | 0.0000 | 0.1000 | 0.5000 | 0.3701 | -0.1672 |
| `2018-01-01` | **Baseline_Activity** | 0.6000 | 0.4000 | 0.5807 | 0.5927 | 0.2183 |
| `2018-01-01` | **Baseline_Random** | 0.2182 | 0.2237 | 0.5899 | 0.5709 | 0.0000 |
| `2018-07-01` | **PromotionPotentialScore** | 0.4000 | 0.2000 | 0.6241 | 0.6221 | -0.0845 |
| `2018-07-01` | **Baseline_MedianViews** | 0.0000 | 0.2000 | 0.5000 | 0.3845 | -0.2636 |
| `2018-07-01` | **Baseline_Activity** | 0.6000 | 0.4000 | 0.6915 | 0.6873 | 0.1437 |
| `2018-07-01` | **Baseline_Random** | 0.3206 | 0.3187 | 0.6577 | 0.6289 | 0.0000 |
| `2019-01-01` | **PromotionPotentialScore** | 0.0000 | 0.1000 | 0.8503 | 0.4697 | -0.0408 |
| `2019-01-01` | **Baseline_MedianViews** | 0.0000 | 0.2000 | 0.6309 | 0.4126 | -0.2525 |
| `2019-01-01` | **Baseline_Activity** | 0.6000 | 0.3000 | 0.6915 | 0.6908 | 0.1201 |
| `2019-01-01` | **Baseline_Random** | 0.2366 | 0.2334 | 0.6275 | 0.5921 | 0.0000 |

## Paired Bootstrap 95% Confidence Intervals (Cutoff 2019-01-01, NDCG@10):

- **Score vs Baseline_MedianViews:** Diff = `+0.0748` (95% CI: `[-0.3759, +0.5024]`) -> *no statistically clear difference (CI includes 0)*
- **Score vs Baseline_Activity:** Diff = `-0.2034` (95% CI: `[-0.5667, +0.3759]`) -> *no statistically clear difference (CI includes 0)*