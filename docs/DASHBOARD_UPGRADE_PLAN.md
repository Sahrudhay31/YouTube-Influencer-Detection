# Dashboard Upgrade Plan (InfluencerAI v2)

## 1. Objectives & Scope
Upgrade the Streamlit dashboard ("InfluencerAI") for the BDA YouTube Influencer project to address all findings in the audit:
- Eliminate misleading ties and percentile rank confusion through explicit evidence badges, deterministic tie-breaking, and dual raw vs percentile score presentation.
- Enhance the Find Influencers leaderboard with modern formatting, custom `column_config`, channel name pinning, multi-select comparison radar, pagination, and robust filtering.
- Upgrade the product brief domain matcher with honest semantic scoring, lexicon term driver transparency, alternative domain probabilities, and out-of-domain guardrails.
- Implement rate-card configurable greedy portfolio allocation with tier overheads and realistic typical view projections.
- Secure the Live YouTube API Discovery tab with dry-run default, explicit two-step live confirmation, real-time quota guard telemetry, and non-mixing guarantees.
- Revamp the Creator Card with full 6-component radar + raw contribution waterfalls, honest sample requirements for promo lift, and a persistent shortlist drawer.
- Upgrade Model Results with model registry flags (overfit/suspicious accuracy), 3-cutoff backtest comparison charts, and empirical honest-findings generation.
- Upgrade Pipeline Status with Pacific midnight rollover gauge, 7-day history, 30-day retention countdown, data lake freshness timestamps, and dual-mode storage status.
- Rectify inaccurate claims in sidebars, headers, and tooltips regarding calibration, HDFS state, and backtest holdouts.
- Maintain 100% Spark-free runtime execution in the frontend and satisfy `python scripts/check_all.py`.

---

## 2. Architecture & Pure Logic Separation
To ensure clean unit testing without Streamlit runtime dependencies, all pure business logic will be modularized in `src/app/`:
- `src/app/formatters.py`: Formatting helpers for subscriber counts (`11.4K / 914K / 3.02M`), median views, engagement rates, and promo lift multipliers with edge cases (`None`, `0`, `NaN`).
- `src/app/evidence.py`: Evidence badge logic, missing component identification, and exact renormalisation factor text generation based on `config/scoring.yaml`.
- `src/app/leaderboard_logic.py`: Pure filtering, multi-tier selection, tie-breaking ("Rank full-evidence creators first" + secondary raw score sort), and pagination slicing.
- `src/app/quota_service.py`: Quota calculation, Pacific-midnight time until reset, per-run safety cap validation, and live confirmation gating.

---

## 3. Files to Touch / Create

### New Files:
1. `src/app/formatters.py` — Pure formatting utilities
2. `src/app/evidence.py` — Evidence flags & renormalisation explanation builder
3. `src/app/leaderboard_logic.py` — Filtering, sorting, tie-breaking, pagination
4. `src/app/quota_service.py` — Pacific-day quota inspection & guard utilities
5. `tests/unit/test_dashboard_v2.py` — Comprehensive unit test suite covering formatters, evidence, sorting, live guard, and quota rollover
6. `docs/DECISIONS.md` — ADR-017: Dashboard v2 Architecture & UX Remediation
7. `docs/screenshots/dashboard_v2/` — Visual proof screenshots at 1920px and 1366px

### Files to Modify:
1. `src/app/components.py` — Semantic styling, refined color palette (reduced red, emerald/amber/slate badges), custom header, metric tooltips, "About these numbers" drawer
2. `src/app/data_loader.py` — Add `st.cache_data`, fix `rate_card.yaml` parsing (`tiers` with `cpm` and `fixed_overhead`), load ablation results, multi-cutoff backtest data, file modified timestamps
3. `src/app/domain_predictor.py` — Return matched lexicon terms, alternative domains, out-of-domain detection
4. `src/app/portfolio_optimizer.py` — Support overhead per tier, user-editable rate card, typical view metrics
5. `src/app/pages_impl/find_influencers.py` — Complete UI overhaul (leaderboard column config, evidence badges, compare modal/expander, shortlist actions, presets, budget allocator)
6. `src/app/pages_impl/creator_card.py` — Waterfall contribution chart, exact renormalisation note, sponsorship rules, audience sampling diagnostics, shortlist button
7. `src/app/pages_impl/model_results.py` — Registry table with flags, Linear SVC / Naive Bayes / LogReg comparison, influencer ablation with CIs, 3-cutoff backtest chart & honest findings
8. `src/app/pages_impl/pipeline_status.py` — Pacific midnight gauge, 7-day history, 30-day retention partition table, storage mode indicator, data freshness
9. `src/app/main.py` — Accurate sidebar branding, shortlist drawer, "About these numbers" definitions, session state initialization
10. `CHANGELOG.md` — Document all v2 dashboard additions and fixes

---

## 4. Implementation Phases

- **Phase 1: Pure Logic Modules & Core Helpers**
  - Implement `formatters.py`, `evidence.py`, `leaderboard_logic.py`, `quota_service.py`.
  - Fix `data_loader.py` and `portfolio_optimizer.py`.
  - Add and run tests in `tests/unit/test_dashboard_v2.py`.

- **Phase 2: Global UI, Styling & Navigation (`src/app/main.py`, `components.py`)**
  - Fix sidebar claims (HDFS-ready Parquet, 3 cutoffs, TF-IDF + GBT).
  - Add "About these numbers" expander and Shortlist drawer in sidebar.
  - Refine CSS (dark theme with sky-blue accent, clean cards, semantic badges).

- **Phase 3: Page 1 — Find Influencers & Allocator (`find_influencers.py`, `domain_predictor.py`)**
  - Add presets, out-of-domain warning, driver lexicon keywords.
  - Upgrade leaderboard table: `st.dataframe` column_config, evidence badge, rank full-evidence first toggle, pagination, compare 2-4 creators side-by-side radar.
  - Upgrade budget allocator with user-editable rate card in expander, overhead calculation, typical views.
  - Secure Live Discovery tab: Dry-run default, confirmation checkbox, Pacific quota panel, query preview.

- **Phase 4: Page 2 — Creator Card (`creator_card.py`)**
  - Exact missing component & renormalisation note.
  - Dual score display (percentile rank vs raw score).
  - Radar chart + waterfall/bar contribution breakdown including penalties.
  - Sponsorship track record with >=3 sponsored/organic requirement.
  - Shortlist integration.

- **Phase 5: Page 3 — Model Results (`model_results.py`)**
  - Registry table with Suspicious / Overfit flags.
  - Domain classifier comparison against baselines.
  - Influencer ablation table with CIs and bar chart.
  - 3-cutoff backtest chart (NDCG@10) and full table.
  - Automated honest findings callout.

- **Phase 6: Page 4 — Pipeline Status (`pipeline_status.py`)**
  - Pacific midnight quota gauge & 7-day chart.
  - 30-day retention partition countdown.
  - Data freshness & dual-mode storage status.

- **Phase 7: Full System Verification & Documentation**
  - Run `python scripts/check_all.py`.
  - Launch Streamlit, run browser subagent to capture 1920px and 1366px screenshots of all 4 pages and tabs.
  - Update `CHANGELOG.md` and add ADR-017 to `docs/DECISIONS.md`.
