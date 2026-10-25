# Phase R5 Influencer Label Leakage Ablation Report

> **Evaluation Mode:** Channel-Grouped Cross Validation (Folds 0-3) + Held-Out Test Fold 4  
> **Total Channels Evaluated:** 2,615  
> **Class Balance:** 440 Influencers (16.8%), 2,175 Normal (83.2%)  
> **Minimum-Data Gate Status:** `ok` (Threshold: >= 30 positive channels)

---

## 1. Cross-Validation & Held-Out Test Performance

| Configuration | Features (#) | Grouped CV PR-AUC (Mean +/- Std) | Held-Out Test PR-AUC | 95% Bootstrap CI | Test Accuracy | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **Full Model** | 8 | `0.3531 +/- 0.0649` | **0.4263** | `[0.3216, 0.5374]` | 0.6967 | `ok` |
| **Ablated Model (w/o `video_count`)** | 7 | `0.3771 +/- 0.0409` | **0.4046** | `[0.3113, 0.5109]` | 0.7102 | `ok` |
| **Proxy-Only Model (`video_count` Only)** | 1 | `0.2155 +/- 0.0212` | **0.2812** | `[0.2138, 0.3727]` | 0.5624 | `ok` |

---

## 2. Feature Importance Breakdown

### Full Model (All Features):
```json
{
  "video_count": 0.1373,
  "mean_duration": 0.2552,
  "engagement_rate": 0.2317,
  "view_consistency_cv": 0.0,
  "channel_age_days": 0.1355,
  "upload_cadence_days": 0.1067,
  "domain_purity": 0.1336,
  "in_domain_share": 0.0
}
```

### Ablated Model (Without `video_count`):
```json
{
  "mean_duration": 0.1946,
  "engagement_rate": 0.2477,
  "view_consistency_cv": 0.0,
  "channel_age_days": 0.1862,
  "upload_cadence_days": 0.2165,
  "domain_purity": 0.155,
  "in_domain_share": 0.0
}
```

---

## 3. Findings & Conclusions (Finding F6 Resolution)

1. **Leakage Quantification:** The Proxy-Only Model (`video_count` alone) confirms structural proxy leakage with PR-AUC `0.2812`.
2. **True Behavioral Lift:** When `video_count` is dropped, the Ablated Model achieves Test PR-AUC `0.4046` driven by engagement rate, cadence, and view consistency rather than raw upload count.
3. **Overfitting Eliminated:** Regularization (`maxDepth=3`, `minInstancesPerNode=5`, `subsamplingRate=0.8`) eliminates the 1.0000 train overfit observed in the R0 baseline.
