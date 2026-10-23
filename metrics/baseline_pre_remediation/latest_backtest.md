# Time-Split Backtest Evaluation (Cutoff T = 2019-01-01)

- **Evaluation Period**: Videos with `upload_date > 2019-01-01`
- **Historical Training**: Videos with `upload_date <= 2019-01-01` (43,851 videos)
- **Post-T Test Videos**: 6,149 videos (778 sponsored)
- **Active Channels Evaluated**: 112

| Ranking Method | Precision@5 | Precision@10 | NDCG@5 | NDCG@10 | Spearman rho | p-value |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **PromotionPotentialScore** | 0.6000 | 0.3000 | 0.6005 | 0.6200 | 0.0246 | 0.7968 |
| **Baseline_MedianViews** | 0.0000 | 0.3000 | 0.5013 | 0.4447 | 0.1085 | 0.2550 |
| **Baseline_Activity** | 0.4000 | 0.3000 | 0.5739 | 0.5800 | 0.2617 | 0.0053 |
