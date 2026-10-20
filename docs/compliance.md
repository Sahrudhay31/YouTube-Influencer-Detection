# YouTube API Data Compliance & Privacy Governance

> **Policy Grounding:** [YouTube API Services Developer Policies](https://developers.google.com/youtube/terms/developer-policies) & [Derived Metrics Policy](https://developers.google.com/youtube/terms/derived-metrics-policy)  
> **Last Updated:** 2026-10-20  
> **Automated Retention Enforcement:** `src/maintenance/purge_api_data.py`

---

## 1. Compliance Architecture Overview

This project accesses YouTube public metadata strictly through authorized Google Cloud APIs and public academic datasets. It strictly enforces compliance with YouTube Developer Policies regarding caching, data storage, user privacy, and quota stewardship.

```
[ YouTube Data API v3 ]
        │  (Direct API Calls strictly restricted through QuotaGuard)
        ▼
[ Raw Zone: /bda/raw/api/dt=YYYY-MM-DD/ ]  <── MAX RETENTION: 30 DAYS
        │                                        (Enforced by purge_api_data.py)
        ▼
[ Feature Transformation & Aggregation ]
        │
        ▼
[ Derived Metrics: /bda/silver/ & /bda/gold/ ]
        ├── Promotion-Potential Score (Computed composite metric)
        ├── Influencer Classification (Binary prediction)
        └── Aggregated Domain Lift
```

---

## 2. Stored Data Catalog & Retention Limits

| Data Category | Target Location | Contents | Allowed Retention | Automated Enforcement |
| :--- | :--- | :--- | :--- | :--- |
| **API Raw Snapshots** | `/bda/raw/api/dt=YYYY-MM-DD/` | Raw JSON from `channels.list`, `playlistItems.list`, `videos.list`, `commentThreads.list` | **≤ 30 Days** (Policy III.E.4.a) | `src/maintenance/purge_api_data.py` runs daily, deleting partitions where `age > 30 days`. |
| **Academic Historical Data** | `/bda/raw/youniverse/` | YouNiverse Zenodo dataset (2019 snapshot, CC-BY 4.0) | Project duration | Academic open-science release; no live API refresh requirements. |
| **Commenter Identifiers** | In-memory / intermediate | Channel/User IDs of commenters | **Zero Raw Storage** | User IDs are hashed immediately with a 32-byte secret salt (`COMMENT_HASH_SALT`) for repeat-commenter loyalty analysis. Raw usernames/IDs are never persisted. |
| **Derived Models & Scores** | `/bda/gold/`, `/bda/models/` | Trained model weights, aggregated channel metrics, Promotion-Potential Scores | Indefinite (Derived statistical aggregations) | Complies with derived-metrics policy: no personal identifiable information (PII) or unaggregated comment bodies. |

---

## 3. Quota & Rate-Limit Protections

1. **Daily Unit Cap:** Hard capped in `config/quota.yaml` at 8,000 units/day (20% safety margin below standard 10,000 unit ceiling).
2. **Dedicated Search List Cap:** Max 20 calls/day for `search.list` (preserving independent search quota buckets).
3. **Pacific Midnight Ledger:** `state/quota_ledger.json` tracks consumption keyed to `America/Los_Angeles` midnight rollover.
4. **Pre-Flight Reserve:** All API calls must reserve quota via `QuotaGuard.reserve()` before network requests. If quota is insufficient, execution halts cleanly without data fabrication.
5. **Batch Efficiency:** Up to 50 IDs requested per single call to `videos.list` and `channels.list`.

---

## 4. Policy Clarifications & Unresolved Inquiries

Per YouTube Developer Policy section III.E ("Storage and Caching"):
- *API data must not be stored for more than 30 days unless refreshed or authorized under a derived-metrics agreement.*
- **Question to User:** Does your deployment model operate under:
  - (a) **Strict 30-Day TTL Refresh** (Recommended: automatic deletion of partitions older than 30 days), OR
  - (b) **Formal Derived Metrics Amendment** (Requires filing an exception with Google Cloud API Review team).
