# REMEDIATION PROMPT — Make the Beauty-Domain YouTube Influencer Project Better (not different, not worse)

> **For the human (delete this box before pasting):**
> - Paste everything below `=== PROMPT START ===` into Antigravity, with the project folder as the workspace. The repo already contains `antigravity_agent_prompt.md`; this prompt **adds to it** and does not replace it.
> - Keep the agent in the mode that shows a plan and asks before running terminal commands. Type `APPROVED R<n>` to release each phase.
> - Things only YOU can do (the agent will remind you): (1) revoke the old YouTube API key in Google Cloud, (2) put a new key and a fresh salt in a private `.env`, (3) hand-label the CSVs in `labels/`, (4) download the extra YouNiverse files if you want subscribers/growth, (5) install Docker if you want real HDFS.

=== PROMPT START ===

You are a senior big-data / ML engineer. The workspace contains a working but flawed project: **Domain-Aware YouTube Influencer Detection & Promotion-Potential Ranking** (PySpark + Parquet, Streamlit, quota-guarded YouTube API client). Your job is to **fix the problems listed below and add the missing capability, while making sure nothing gets worse.** Read the entire prompt first.

**Product goal (unchanged, do not deviate):** a company enters a **beauty product description** (e.g., "new vitamin-C serum for oily skin"). The system finds YouTube creators who mainly make beauty content, have strong reach and audience engagement, and a record of promotion that performed well — and ranks them so the company can decide whom to approach for a promotional video. The output is a **Promotion-Potential Score** (predicted promotion performance from public data). It is **not** measured sales or ROI; never claim otherwise.

**Domain:** **Beauty & Personal Care only** (micro-domains: skincare, makeup, haircare). Do NOT switch to technology or any other domain. Any technology/smartphone wording you see in earlier discussion was only an illustration.

---

## 1. Operating rules (these extend R1–R11 in `antigravity_agent_prompt.md`; restated compactly)

**R1 No hallucination.** Never invent file contents, column names, API fields/parts, library functions, parameters, dataset sizes, licences, or results. Before claiming anything about existing code, open it and cite `path:line`. Before using a library function not already used in this repo, verify it in the *installed* version (`inspect.signature`, `help`). Print real schemas and 5 real rows before touching any data. If you cannot verify, write "UNVERIFIED" and ask.

**R2 Ask, don't guess.** When something is unclear or a decision belongs to the human, stop that branch and post exactly:
```
❓ DECISION NEEDED (Phase R<n>, blocking: yes/no)
Context: ...
What I verified (with path:line or command output): ...
What I could not verify: ...
Options: A) ...  B) ...  (C) ...
My recommendation and why: ...
What I will do meanwhile (non-blocked work only): ...
```
Batch questions (max 5 per message). Never ask what you can learn by reading the repo or running a command.

**R3 Phase gates.** Work in phases R0–R9 (Section 6). End each with a Phase Report (Section 9), then STOP until I type `APPROVED R<n>`.

**R4 Test before moving on.** Write and run the smoke tests listed per phase and paste the REAL output. Never delete, skip, or loosen a test to make it pass. After 3 failed fix attempts, stop and ask me with logs and 2–3 hypotheses.

**R5 No fabricated data, ever.** Synthetic data lives only in `tests/fixtures/` (files named `synthetic_*`) and never appears in a reported metric, leaderboard, or README number. If the API is unavailable or quota is exhausted, the pipeline stops cleanly and says so.

**R6 Quota first.** Every YouTube API call goes through the existing quota guard and `YouTubeClient`. Default mode stays **dry-run**. Live runs are staged (`--max-units 50`, then `300`, then normal) and actual-vs-estimated units are reported each time.

**R7 Metrics only from real runs**, read from `metrics/` files via the existing logger. Never type a number by hand into README/docs/app. Generated sections between markers only.

**R8 Docs stay alive.** Update `README.md`, `CHANGELOG.md`, `docs/DECISIONS.md` at the end of every phase and after any major change (new/removed module, changed data flow, changed model/feature set, changed metric definition, new dependency/config key, quota/retention change, scope decision).

**R9 Secrets.** Never print, log, commit, or echo any API key, salt, or personal path. Keys/salts come from `.env` only.

**R10 Scope discipline.** Do only what this prompt lists. Extra ideas go to `docs/OPEN_QUESTIONS.md`; ask first.

**R11 Git hygiene.** If a git repo: commit per phase (`R<n>: <summary>`), tag `R<n>`, never push without my permission, never commit `data/`, `models/`, `logs/`, `state/`, `.env`. Prefer moving files to `archive/` over deleting.

---

## 2. NON-REGRESSION CONTRACT (this is what "better, not worse" means)

1. **Freeze a baseline first (Phase R0):** git tag `pre-remediation`; run the full test suite and record pass/fail counts; copy `metrics/` to `metrics/baseline_pre_remediation/`; snapshot `config/` to `docs/baseline_config/`; write `docs/BASELINE.md`. If tests cannot run on this machine, say exactly why and ask me — do not claim they pass.
2. **Additive first.** Put new behaviour in new modules or behind config flags. Keep old code paths until the new path passes its tests and I approve removal. Do not rewrite modules that work. Keep public function signatures; if you must change one, update every caller and test in the same commit.
3. **Existing tests must keep passing.** You may add tests; you may not delete, skip, `xfail`, or weaken existing ones. If an existing test encodes a wrong assumption, show me the test and ask before changing it.
4. **Before/after table every phase.** For every metric that exists in the baseline (accuracy, macro-F1, PR-AUC, RMSE, NDCG, runtime, etc.) record before and after in `docs/REMEDIATION_COMPARISON.md`.
5. **How to read a lower number.**
   - Lower because you removed leakage, circular labels, a biased sample, or a measurement artifact = an **honesty correction**. Label it as such with the reason. This is *expected* and *good*.
   - Lower with no methodological reason = a **regression**. Stop, diagnose, and ask me before continuing.
   - Never hide, round away, or re-run until a number looks good. Never tune on the test set.
6. **Do not weaken safety:** quota caps may only become stricter; dry-run stays the default; retention (30 days) stays enforced; the single-import rule for `googleapiclient` stays enforced; the secrets scan may only become broader.
7. **No heavy new dependencies** (no torch/transformers/sentence-transformers/Airflow/Kafka) without my approval. Prefer PySpark built-ins, pandas, scipy, scikit-learn (evaluation only) — verify what is already in `requirements.txt` first.
8. **Protect what is good** (do not "improve" these away): quota guard design (Pacific-time ledger, reserve-before-call, dry-run default, audit log), metrics logger with overfit/suspicious flags, config-driven domain packs, honest-framing section, the pre-T feature rebuild in the backtest, the Spark-free Streamlit app, `scripts/check_all.py`.

---

## 3. Verified findings to fix (re-verify EACH yourself in Phase R0 with a command and `path:line`; do not trust this list blindly)

| ID | Finding (as I observed it in the uploaded zip) |
|---|---|
| F1 | `archive/legacy_sentiment_prototype/youtube_producer.py:12` still contains a real-looking API key in plaintext; `scripts/check_all.py` skips `archive/`, so the scan cannot see it. |
| F2 | `.env.example` contains a real-looking 64-hex `COMMENT_HASH_SALT` value instead of a placeholder. |
| F3 | `scripts/extract_dev_sample.py` hardcodes a personal Windows path (`C:\Users\<full name>\Downloads\...`); `docs/DECISIONS.md` ADR-004 repeats it. |
| F4 | `scripts/extract_dev_sample.py` copies the **first N lines** of the gz file (head-of-file), not a random sample; `data.dev_sample_fraction` in `config/settings.yaml` is unused. Result: only ~127 channels feed every model. |
| F5 | `labels/domain_to_label.csv` (500 rows) and `labels/sponsor_to_label.csv` (300 rows) have **zero** human labels; reported "accuracy" is agreement with keyword/rule weak labels. Keyword baseline acc (0.949) ≥ logistic regression val (0.913) and LinearSVC val (0.921); majority baseline 0.897. Domain task is binary (beauty vs out_of_domain). |
| F6 | Influencer label = `median_views ≥ 10000 AND sponsored_count ≥ 1` (`config/influencer.yaml`), where sponsorship comes from unvalidated rules. `video_count` (a feature) structurally predicts "has ≥1 detected sponsored video"; the leakage guard only compares column names. ADR-006 describes a *different* definition (≥1,000 views, sponsorship OR top-20% engagement). Only 127 channels (83/27/17 split). GBT train accuracy = 1.0. |
| F7 | `promo_lift_regressor_gbt`: n = 26/12/3 channels, train R² 0.9995 but **val R² −1.95**, val RMSE 4.82 vs train 0.058; `latest.md` hides regression columns; README presents it as "calibration" using a circular Spearman (0.4585) against the composite score that itself contains promo lift. |
| F8 | README says the score "outperforms both baselines"; `metrics/backtest_results.csv` shows P@10 tied (0.3), score Spearman 0.0246 (p=0.797) vs Activity baseline 0.2617 (p=0.005), 112 channels. ADR-008 says the score was "verified by backtesting (ρ=0.4585)" — that number is not the backtest result. |
| F9 | `metrics/scalability.csv`: `local[1]` 10.106 s vs `local[2]` 0.807 s (12.5× on 2 cores, "parallel efficiency" 6.26). No warm-up in `scripts/scalability_benchmark.py`; README claims "12.99× speedup from Catalyst multi-threading". |
| F10 | Backtest: pre-T videos keep **crawl-time (late-2019) view counts**, which include post-T growth; post-T videos are younger. Both distort sponsored-vs-organic lift. Also `engagement_rate` is likes+dislikes in the classifier but likes-only in the backtest. |
| F11 | HDFS appears unused: `spark_session.py` falls back to `file:///`; classifier reads `local("silver", …)`; Docker was not installed at Phase 0. README still says "Hadoop HDFS". |
| F12 | Only video metadata is loaded: no subscriber counts, no weekly time series → no real size tiers, no momentum signal. |
| F13 | `config/quota_costs.yaml` is marked UNVERIFIED and models `search.list` as 100 units per call; current Google docs give `search.list` its own separate daily bucket (~100 calls/day). The live API path has never been run (no `state/` or `logs/`). |
| F14 | `metrics/model_registry.csv` has duplicate rows (each domain model logged twice with identical numbers); `latest.md` shows only accuracy-style columns. |

---

## 4. Reference repositories — REUSE BEFORE YOU BUILD

**Reuse order:** (1) existing code in this repo → (2) the references below → (3) PySpark / pandas / scipy / scikit-learn built-ins → (4) new code. If a reference covers a need, open it, say which file you are adapting, and keep the adaptation small.

**Third-party code protocol (mandatory):**
- Before copying anything, open the repo's `LICENSE` and confirm the licence *today*. Permissive (Apache-2.0, MIT, BSD) → you may adapt small portions with an attribution comment header (`# Adapted from <url> @ <commit>, <licence>`). **No licence found → study only, copy nothing.** Copyleft or non-commercial (e.g., CC BY-NC-SA) → do not copy code, data, or derived models into this repo without my explicit approval.
- Record every use in `docs/THIRD_PARTY.md`: URL, commit hash, licence, files used, what you changed.
- Check the reference still exists and still says what I describe; if the page is unreachable, say so and ask.
- Verify adapted code runs on our pinned versions (Python 3.11, PySpark as pinned) — references are often old.

| # | Reference | Use it for | Notes / cautions |
|---|---|---|---|
| 1 | https://github.com/epfl-dlab/YouNiverse | Exact file names and schemas of the dataset (channels, time series, video metadata, comments); paper's sampling/processing notes. | Confirm file names on the Zenodo record before asking me to download. Data licence: confirm on Zenodo (I will answer Q-LICENSE). |
| 2 | https://github.com/youtube/api-samples/tree/master/python (`my_uploads.py`, `comment_threads.py`) | The canonical pattern: `channels.list` → `contentDetails.relatedPlaylists.uploads` → paginated `playlistItems.list`; `commentThreads.list` usage. | Samples use OAuth; we use an **API key** (`build("youtube","v3",developerKey=...)`). Do **not** copy the OAuth flow. Only adapt inside `yt_client.py`. Confirm licence. |
| 3 | https://github.com/apache/spark → `examples/src/main/python/ml/` (`tf_idf_example.py`, `tokenizer_example.py`, `stopwords_remover_example.py`, `linearsvc.py`, `one_vs_rest_example.py`, `naive_bayes_example.py`, `gradient_boosted_tree_classifier_example.py`, `gradient_boosted_tree_regressor_example.py`, `random_forest_*`, `train_validation_split.py`) | Correct MLlib pipeline idioms (Tokenizer→StopWords→HashingTF/CountVectorizer→IDF→classifier, OneVsRest for multi-class, TrainValidationSplit). | Apache-2.0 (header seen on `tf_idf_example.py`). Prefer the `pyspark.ml` (DataFrame) examples, not the old `pyspark.mllib` RDD ones. |
| 4 | https://github.com/big-data-europe/docker-hadoop (issues #98, #124; PR #137; `docker-compose-v3.yml`, `hadoop.env`) | Making HDFS reachable from a host-side Spark: the known DataNode-hostname problem; settings such as `dfs.client.use.datanode.hostname=true`, `dfs.datanode.use.datanode.hostname=true`, namenode bind-host properties, and mapping the `datanode` hostname to `127.0.0.1`. | Our compose already uses `bde2020/*` images. **Reproduce the failure first**, then apply the smallest fix that works; one issue reports the hostname setting alone did not work in their setup. Verify DataNode ports for Hadoop 3.2.1 from the image docs before exposing them. |
| 5 | https://github.com/nikals99/sponsorblock-net | Methodology only: **splitting by channel** to avoid leakage, bag-of-words + Naive Bayes/Logistic baselines, precision/recall/F1 reported across thresholds. | Transcript-based (we use descriptions/titles) → little code to reuse. Check licence. |
| 6 | https://github.com/xenova/sponsorblock-ml | Methodology for evaluating sponsor detection. **Optional / low priority.** | Its training data is SponsorBlock (**CC BY-NC-SA 4.0**) → do not import its data or models; transformers are out of scope. |
| 7 | https://github.com/dibseal/influencer-matching | Design ideas: weighted matching engine, per-dimension **score breakdown/explanations**, a ranking-evaluation module; "filters vs ranking" separation. | Built on *synthetic* data; no licence verified → **study only unless a LICENSE permits copying.** |
| 8 | https://github.com/shauvar/dissertation | Feature ideas for YouTube engagement (e.g., recent-activity rate) and tier analysis structure. | Tiny sample (n=45 YouTube channels); do **not** cite its numbers. Study only unless licence permits. |
| 9 | https://github.com/sureshtr715-dot/-YouTube-Trending-Analytics-Real-Time-Data-Engineering-Pipeline (MIT) and https://github.com/Rubayet19/Youtube-Trending-ETL | Layering idea only (bronze/silver/gold; a gold `channel_performance` table) and dashboard layout. | Both ingest YouTube's *trending* list — wrong population for creator discovery. **Do NOT adopt Kafka, Airflow, Delta Lake, Azure, or Looker** (ADR-001 stays). Rubayet19 has no licence shown → study only. |
| 10 | Libraries, not repos: `scipy.stats.spearmanr`, `scikit-learn` `ndcg_score`, `numpy` bootstrap | Evaluation code (on small result tables only). | Check they are installed; add to `requirements-dev.txt` only if missing, then tell me. |

**FORBIDDEN sources:** any "no API key" scraper/Apify actor (e.g., the `logiover/*` influencer-audit or discovery scrapers) or any tool that scrapes YouTube. YouTube's Developer Policies prohibit scraping and using scraped data. Also do not use marketing-style repos with unverifiable claims (e.g., `Crynge/InfluencerHub`) as a source of methods or numbers.

---

## 5. Cross-cutting specs

### 5.1 Metrics logging upgrades (extend `src/common/metrics_logger.py`; keep old columns)
- Add columns: `eval_target` (`weak_labels` | `human_labels` | `time_split_outcome`), `eval_n`, `ci95_low`, `ci95_high` (bootstrap, where applicable), `cv_mean`, `cv_std`, `usable_in_score` (true/false), `status` (`ok` | `insufficient_data` | `failed_validity_check`), `sample_version`.
- `metrics/latest.md` must show **train, val, test accuracy AND macro-F1, PR-AUC, and for regressors train/val/test RMSE, MAE, R²**, plus the baseline value and any WARNING (overfit gap > 0.10; accuracy > 0.98 "suspicious"; **val R² ≤ 0 → "worse than predicting the mean"**).
- Show the latest run per model only in `latest.md`; keep `model_registry.csv` append-only, but add a `run_group` column and a `--no-log` flag for debugging so re-runs don't pollute it. De-duplicate the existing duplicate rows by marking older ones `superseded=true` (do not delete rows).
- `scripts/update_readme_metrics.py` also fills a **Backtest** section (between `<!-- BACKTEST_START -->` / `<!-- BACKTEST_END -->`) and a **Scalability** section (between `<!-- SCALE_START -->` / `<!-- SCALE_END -->`) directly from the CSVs.
- **No-overclaim rule in the generator:** the text "outperforms" / "better than" may be generated only if the paired-bootstrap 95% CI of the difference excludes 0; otherwise generate "no statistically clear difference".

### 5.2 Quota (stricter, not looser)
- Re-read the *current* official pages: `https://developers.google.com/youtube/v3/determine_quota_cost` and the quota/compliance page. Update `config/quota_costs.yaml` with `verified_on` (today's date) and real findings. If you cannot open them, ask me.
- Model `search.list` as a **separate bucket** in the ledger (own counter, own cap `search_list_daily_cap`, default 20 calls/day, I may raise it). Confirm from the docs whether a search call also consumes units from the general 10,000 pool; if the docs are ambiguous, ask me.
- Keep `daily_unit_cap: 8000`, `per_run_max_units: 1500`. Add `max_search_calls_per_run` (default 10).
- Retention: 30-day purge for raw API partitions stays; add a purge test for the new discovery partitions.

### 5.3 Testing conventions
- `pytest` unit tests; Spark smoke tests on `local[2]` with tiny `synthetic_*` fixtures; `python scripts/check_all.py` must pass before every Phase Report. Extend it: secrets scan covers `archive/`, `docs/`, `config/`, `.env.example`; also flags 64-hex strings in `.env.example` and absolute personal paths (`C:\Users\`, `/home/<name>`) in tracked files.
- Every job: idempotent (run twice → same output), logs input rows, output rows, key null rates, runtime.
- Never test against the live API.
- Show real error text, not summaries.

---

## 6. Phases

### R0 — Baseline freeze, verification, questions (NO code changes)
1. Do Section 2.1 (tag, test run, metrics snapshot, `docs/BASELINE.md`).
2. Verify F1–F14 by command; write `docs/REMEDIATION_AUDIT.md` (finding → evidence → status CONFIRMED / NOT CONFIRMED / PARTLY). If any finding is wrong, say so plainly.
3. Environment facts (Python/Java/Spark versions, Docker present?, free disk, RAM) — paste real output.
4. Ask me (R2 format, batched): **Q-KEY** (old key revoked? new key + fresh salt in private `.env`?); **Q-DOCKER** (can I install Docker/WSL2 for real HDFS, or stay local?); **Q-DATA2** (will I download YouNiverse channel + time-series files? disk budget? — give me the exact file names from the YouNiverse repo/Zenodo page); **Q-SAMPLE** (channel sample percentage: propose 3%, 5%, 10% with estimated disk and runtime after measuring the first 1M lines); **Q-LABELS** (when will I label the 500 domain rows and 300 sponsor rows? Add a `human_micro_label` column to the domain CSV with allowed values `skincare|makeup|haircare|other_beauty|not_beauty`); **Q-GIT** (may you rewrite git history to purge the old key? default: no — I will just revoke it); **Q-MARKET** (target market/language for the live path, e.g., India + English).
5. Deliver `docs/BASELINE.md`, `docs/REMEDIATION_AUDIT.md`, an implementation plan. STOP.

### R1 — Security and hygiene (F1, F2, F3)
- Redact the key in the archived file (`REDACTED`), keep a note in the archive README. Replace the salt in `.env.example` with an empty placeholder + generation instruction. Replace the hardcoded path with env var `YOUNIVERSE_SOURCE_PATH` (and a CLI arg); remove personal path text from docs (use `<your-downloads-path>`).
- Broaden `scripts/check_all.py` per 5.3. Remind me to revoke the key and generate a new salt; **never print either**.
- Tests: `T-H1` scan finds a planted fake key in a temp `archive/` dir and in a temp `docs/` file; `T-H2` `.env.example` has no 64-hex value; `T-H3` no `C:\Users\` in tracked files; `T-H4` extraction script reads `YOUNIVERSE_SOURCE_PATH`; `T-H5` pipeline refuses to start comment hashing when `COMMENT_HASH_SALT` is empty or equals the old leaked value (store only its SHA-256 fingerprint to compare — never the value).
- Gate: `check_all.py` green; before/after table updated.

### R2 — Representative data sample + richer data (F4, F12)
- New `src/ingestion/sample_youniverse.py` (reuse the gzip streaming approach from the old script; reference #1 for schema): stream the gz **line by line** (never decompress to disk), read `channel_id` from each record (verify the field name on real rows), keep the line iff `zlib.crc32((salt + channel_id).encode()) % 10000 < sample_basis_points`. **Whole channels** are kept or dropped together. Do NOT use Python `hash()`.
- Config: `data.sample_basis_points`, `data.sample_salt`, `data.sample_version` (e.g., `chash_v1_5pct`). Support `--resume` using a line-offset checkpoint and `--max-lines` for dry runs. Measure throughput on the first 1M lines, extrapolate total runtime and output size, **tell me, and wait for approval before the full pass.**
- Keep the old head-of-file sample, renamed `data/raw/youniverse_head50k/` with `sample_version: head50k_legacy`, so before/after comparisons are possible. All downstream outputs record `sample_version`.
- Validation report `docs/sample_report.md`: #channels, #videos, videos-per-channel percentiles, category distribution, beauty share (by current keyword rule), and the same stats for a second independent hash bucket (different salt) to show the sample is stable.
- If I download the channel and time-series files: extend `load_youniverse.py` (it already references a timeseries output) to build `silver/channels` (subscribers) and weekly growth; verify schemas from real rows; update `docs/data_dictionary.md`. Derive size tiers from **subscriber quantiles of the new sample**, stored in config with the `sample_version`. Add `momentum` (recent weekly subscriber/view growth) as a *new* feature/score component only after verifying the data supports it.
- Re-run silver conversion and downstream jobs on the new sample **only after I approve**; keep legacy outputs under `data/silver_legacy/` for comparison.
- Tests: `T-D7` same input + salt → identical kept-channel set; `T-D8` a fixture with 3 channels keeps/drops each channel's lines as a block; `T-D9` different salt → different but similarly sized set; `T-D10` output size ≤ configured cap; `T-D11` resume gives the same output as an uninterrupted run (fixture).
- Gate: sample report, channel count ≥ several thousand (state the real number), runtime/disk actuals.

### R3 — Make HDFS real, or state clearly that it is not (F11)
- Ask me to choose: **A (recommended)** real HDFS via Docker; **B** local-mode, with honest docs.
- If A: start from the existing compose (`bde2020/hadoop-*`); use reference #4. **Reproduce** a host-Spark write failure first and paste the exception; then apply the smallest working fix (client settings for DataNode hostnames, hostname mapping, correct exposed ports, or run Spark inside the Docker network). Move silver/gold/model outputs to HDFS paths through `src/common/paths.py` (one switch in config; local mode remains available via explicit flag only). HDFS failures must raise — no silent fallback.
- If B: edit README/ADRs to say "local filesystem mode; HDFS compose is provided but not used", and remove HDFS claims from architecture text.
- Tests (A): `T-HDFS1` `hdfs dfs -put/-cat` round trip; `T-HDFS2` Spark Parquet write→read to HDFS with equal row counts; `T-HDFS3` wrong URI raises; `T-HDFS4` purge job lists and deletes a test partition in HDFS.
- Paste `hdfs dfs -ls -R /bda | head` output into `docs/hdfs_verification.md`.

### R4 — Honest evaluation with human labels (F5, F14)
- **BLOCKED until I label** `labels/domain_to_label.csv` and `labels/sponsor_to_label.csv`. Do not label them yourself. Until then, mark all domain/sponsor metrics `eval_target=weak_labels` and add "unvalidated against human labels" to README and the app.
- When labels arrive: add `scripts/score_with_human_labels.py` → for the 500 domain rows compute accuracy, per-class P/R/F1, confusion matrix, and Cohen's kappa (weak vs human) for: keyword baseline, each trained model. Evaluate **by channel-grouped hold-out**. For sponsor rules: precision, recall, F1 against the 300 human labels. Log with `eval_target=human_labels`.
- Domain classifier upgrade (only if `human_micro_label` is filled): add a multi-class variant `beauty/skincare/makeup/haircare/other_beauty/not_beauty` trained on weak labels and **evaluated on human labels**; adapt reference #3 (`one_vs_rest_example.py`, `tf_idf_example.py`). Keep the existing binary model untouched. Report whether either model beats the keyword baseline; if not, say so in README.
- Fix F14 (logger/registry/latest.md per 5.1).
- Tests: `T-E1` metrics from a hand-made 10-row fixture equal hand-computed values; `T-E2` kappa = 1 for identical labelers, ≈ 0 for shuffled; `T-E3` grouped split has no channel overlap; `T-E4` registry de-dup marks older duplicates `superseded` without deleting; `T-E5` `latest.md` includes train/val/test + R² columns and warnings.
- Gate: before/after table; I review confusion matrices.

### R5 — Influencer vs normal creator: remove circularity; fix the regressor (F6, F7)
- **Ask me to choose the definition (R2 format)**; present updated options (use real subscribers if R2 delivered them):
  - **A. Transparent rule, no ML claim** (recommended for the "influencer" flag): reach + activity thresholds from the sample's own quantiles.
  - **B. Current Option B, repaired:** keep definition, but add leakage ablations (below) and report honestly.
  - **C. Clustering tiers** (KMeans/GMM on reach, engagement, cadence), clusters named by me.
  - **D. Behaviour target (recommended for ML):** predict "promotion success" = post-sponsorship lift ≥ 1.0, which is closer to the business goal and not defined from the features.
- Whatever I pick, add: (1) **ablation runs** — without `video_count`; permutation importance; a "label-from-proxies-only" model (train on `video_count` alone) to expose structural leakage; (2) **channel-grouped k-fold CV** (k=5) reporting mean±std; (3) **bootstrap 95% CI** for held-out metrics; (4) a **minimum-data gate**: if positives in test < 30 (or total channels < configured minimum), do not headline test accuracy — headline CV and mark `status=insufficient_data` where needed; (5) regularised trees (`maxDepth ≤ 3`, `minInstancesPerNode ≥ 5`, `subsamplingRate < 1`) selected by CV on **train only**; test evaluated once.
- Regressor (promo lift): **gate** — train only if ≥ 200 channels have non-null lift (config); otherwise write a registry row with `status=insufficient_data` and exclude the model from scoring. Use log/winsorised target; compare with baselines (predict train median; ridge); report train/val/test RMSE/MAE/R². If val R² ≤ 0 set `usable_in_score=false`. **Delete the circular Spearman "calibration" claim**; validate against held-out promo lift directly.
- Unify engagement definition in one function used by classifier, score and backtest; document it in `docs/data_dictionary.md`. Do not silently change the meaning — record the change in CHANGELOG.
- Tests: `T-I6` CV folds share no channels; `T-I7` bootstrap CI brackets the point estimate on a fixture; `T-I8` gate blocks training below minimum n; `T-I9` ablation script runs and logs; `T-I10` the original leakage guard still passes; `T-I11` single engagement function is the only implementation (grep test).
- Gate: ablation table (does `video_count` carry the model?), CV mean±std, before/after table with honesty-correction labels.

### R6 — Beauty creator discovery and live enrichment path (new capability, API-safe)
Goal: from a product brief, produce a candidate list of beauty creators **within quota**, reusing `src/enrichment/*` and `YouTubeClient`.
- `src/discovery/query_builder.py`: deterministic queries from the brief + `config/domains/beauty_personal_care.yaml` lexicon (product types, concerns, "review", "routine", "tutorial"). Every lexicon term has `source: human|agent_proposed`; wait for my review of agent-proposed terms. No LLM calls.
- `src/discovery/candidate_discovery.py`: (a) **offline candidates** — beauty-leaning channels from the new sample (zero units); (b) **live candidates** — `search.list` (`type=video`, `maxResults=50`, recent window, language/region from Q-MARKET) bounded by the separate search bucket and `max_search_calls_per_run`; dedupe channel IDs; keep `source` (`offline`/`search`) and the query that found it. Partition raw API data under `/bda/raw/api/dt=YYYY-MM-DD/` (30-day TTL).
- Enrichment via the existing pipeline: batched `channels.list` (≤50 IDs; statistics, uploads-playlist ID — verify field names from real responses and reference #2), `playlistItems.list` for the last N uploads (default 20), batched `videos.list` for stats/tags/description. Respect `commentsDisabled` handling already in the guard.
- **Topical focus** (new feature): share of the creator's last N videos predicted beauty by the trained domain model (reuse `src/app/domain_predictor.py` if suitable — read it first; do not duplicate), plus micro-domain match to the brief. Output `topical_focus ∈ [0,1]` and `micro_domain_match`.
- **Hard filters (config, shown to the user):** active within last X days, minimum recent median views, language heuristic from verified metadata fields. Filters are separate from ranking (reference #7 idea).
- CLI: `python -m src.discovery.run --brief "<text>" --mode dry_run|live --max-units N`. Dry-run prints the planned calls and estimated units; no network.
- Quota fix per 5.2; `docs/API_RUNS.md` logs each live stage (date, planned vs actual units, number of channels, no keys).
- Tests: `T-L6` query builder deterministic and bounded; `T-L7` dedupe across offline+live; `T-L8` search cap stops further calls (mock client); `T-L9` dry-run makes zero network calls; `T-L10` filters remove a stale and a low-reach fixture channel; `T-L11` topical_focus within [0,1] and monotonic with beauty share; `T-L12` exhausted quota → clean stop, partial results saved, **no fabricated rows**; `T-L13` purge removes a 31-day-old discovery partition.
- Gate: dry-run estimate shown; I approve each live stage; actual units reported.

### R7 — Score, backtest and claims (F8, F10)
- Add `topical_focus` (and `momentum` if R2 supports it) to `config/scoring.yaml`; propose new weights (ask me); keep dynamic renormalisation and `partial_evidence` flag; the app must show how many components were available per creator. If the regressor is `usable_in_score=false`, it must not influence the score.
- Backtest fixes: (1) report **age-normalised** performance (views per day since upload at crawl) and, if time-series data exists, views as of T; show both; (2) unify engagement definition; (3) baselines: median views, activity, subscribers (if available), and **random** (seeded, averaged over ≥ 1,000 draws); (4) **paired bootstrap 95% CIs** for the difference in NDCG@k / precision@k vs each baseline; (5) run at ≥ 3 cutoffs (e.g., 2018-01-01, 2018-07-01, 2019-01-01) and show consistency; (6) record n channels and the relevance definition in the output.
- README/ADR text for backtest comes only from the generator (5.1). **Remove** "outperforms" and "verified by backtesting ρ=0.4585" unless the CI supports them. Add correction ADRs (ADR-011 *Backtest findings & corrections*, ADR-012 *Influencer label redesign*) and mark ADR-006/008 as **Superseded** instead of silently rewriting them.
- Tests: `T-R7` age-normalisation unit test with hand values; `T-R8` random baseline mean ≈ analytic expectation on a fixture; `T-R9` bootstrap deterministic under a seed; `T-R10` README generator never emits "outperforms" when the CI includes 0; `T-R11` backtest asserts no post-T upload dates in ranking features (kept) and documents the crawl-time view caveat; `T-R12` existing T-R1…T-R6 still pass.
- Gate: backtest table with CIs at 3 cutoffs; before/after comparison; honest summary sentence proposed for README (I approve).

### R8 — Benchmark you can defend (F9)
- Fix `scripts/scalability_benchmark.py`: discard a warm-up run per configuration inside the same session; **≥ 5 timed repeats**; report median and IQR; separate "cold" (first run) from "warm" numbers; use a larger input (the new sample, millions of rows if disk allows — ask me); compute speedup = median(local[1]) / median(local[n]) and efficiency = speedup / n. If efficiency > 1.2, flag `superlinear_suspect` and do **not** publish it as a speedup — investigate (JIT/IO cache/skew).
- Storage benchmark: supply the schema for CSV (no `inferSchema`), same data in all formats, measure (a) full scan, (b) column-pruned aggregation, (c) a `domain = 'beauty'` filter query (where partitioning should help).
- State the limitation honestly: `local[n]` threads on one JVM are not a cluster; if Docker/HDFS is available you may add a standalone-cluster run only after asking me.
- Tests: `T-B1` the script marks a fabricated 12× result on 2 cores as `superlinear_suspect`; `T-B2` output CSV has median/IQR/repeats columns; `T-B3` README scalability section is generated from the CSV only.

### R9 — Docs, app honesty, final comparison
- Regenerate README results/backtest/scalability sections from files; rewrite prose claims to match; add "Known limitations" (public data has no sales; 2019 base data; weak labels where still used; sampled/limited comments; English only).
- App: banners for `unvalidated` / `insufficient_data` / `partial_evidence`; Model Results page shows train/val/test accuracy and R², warnings, `eval_target`, `sample_version`; add the **brief → ranked beauty creators** flow using the new discovery output (cached gold tables; the app must still import without Spark). Show per-component contributions for each creator (reference #7 idea).
- Finish `docs/REMEDIATION_COMPARISON.md` (every baseline metric: before, after, verdict = improved / honesty-correction / regression-with-reason), `docs/THIRD_PARTY.md`, `docs/DECISIONS.md`, `CHANGELOG.md`.
- Clean-clone check: `make setup && python scripts/check_all.py` on the sample; paste output.
- Gate: final review. Multi-domain expansion is a separate task I will request.

---

## 7. What "done" looks like
- No secrets, salts, or personal paths in any tracked file; broadened scan passes.
- Models are trained and evaluated on a **channel-hash sample with thousands of channels**; every model has train/val/test (or CV) results with CIs where relevant; domain and sponsor accuracy are reported against **my human labels**; unvalidated things are labelled as such.
- The influencer flag is no longer circular; the regressor is either valid or excluded; no claim in the README exceeds the evidence.
- A brief goes in → beauty candidates are discovered within quota → filtered → scored → ranked with explanations.
- HDFS is real (or the docs say it isn't); the benchmark is fair; `check_all.py` passes; every phase has a before/after table and nothing silently got worse.

## 8. Things you must NOT do
Switch domains; add Kafka/Airflow/Delta/Azure; use scrapers or "no API key" tools; copy code without a verified permissive licence and an attribution entry; run live API calls without my approval of the stage; label my data for me; hand-type any metric; delete tests; rewrite working modules wholesale; push to a remote.

## 9. Phase Report template (post at the end of every phase, then stop)
```
## Phase R<n> report
1. What changed (paths; new / modified / moved)
2. REAL output: python scripts/check_all.py and the phase smoke tests
3. Before/after table for affected baseline metrics (with verdict labels)
4. Metrics produced (run_ids; read from metrics/latest.md)
5. API units used today vs cap (from the ledger); live stages run
6. References used (docs/THIRD_PARTY.md entries) and licences checked
7. Assumptions made (also in docs/DECISIONS.md)
8. Things I could not verify
9. Open questions (R2 format)
10. README / CHANGELOG sections updated
11. Plan for the next phase
Waiting for: APPROVED R<n>
```

**Start now with Phase R0 only. Make no code changes until I type `APPROVED R0`.**
