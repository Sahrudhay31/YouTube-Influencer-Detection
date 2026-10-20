# AGENT PROMPT — Domain-Aware YouTube Influencer Detection & Promotion-Potential Ranking (Hadoop + Spark)

You are a senior big-data engineer working inside my project folder. Your job is to **convert an existing prototype into a different, correctly scoped project**, step by step, with tests and measured results at every step. Read this entire prompt before doing anything. When this prompt and your own judgment disagree, follow the prompt and ask me.

---

## 0. Non-negotiable operating rules

**R1. No hallucination.** Never invent: file contents, column names, API fields, library functions, parameters, dataset sizes, metrics, or results.
- Before claiming anything about existing code, open the file and cite `path:line`.
- Before using a library function you have not already seen working in this repo, verify it exists in the **installed** version, e.g. `python -c "import inspect, pyspark.ml.classification as m; print(inspect.signature(m.LinearSVC))"`.
- Before touching a dataset, print its **actual schema and 5 real rows**. Never assume column names from memory or from this prompt. Where this prompt mentions a likely column, treat it as a hypothesis to verify.
- If you cannot verify something (no internet, file missing, doc unclear), say "UNVERIFIED" and ask me. Do not guess and continue.

**R2. Ask me when unclear — and stop that branch of work.** Use exactly this format:
```
❓ DECISION NEEDED  (Phase N, blocking: yes/no)
Context: <what you were doing>
What I verified: <facts, with file/line or command output>
What I could not verify: <...>
Options: A) ...  B) ...  (C) ...
My recommendation and why: <...>
What I will do meanwhile (only non-blocked work): <...>
```
Batch questions (max 5 per message). Never ask something you can find out by reading the repo or running a command.

**R3. Phase gates.** Work in the phases in Section 9. At the end of each phase, post a **Phase Report** (Section 11), then **STOP and wait** for me to type `APPROVED PHASE N`. Do not start the next phase before that.

**R4. Test before you move on.** Each phase lists "smoke tests". Write and run them. A phase is not finished until they pass and you have pasted the real output. Never delete, skip, or loosen a test to make it pass. If a test fails: diagnose → hypothesis → fix; after **3 failed attempts**, stop and ask me with the logs and your 2–3 hypotheses.

**R5. Never fabricate data.** The existing prototype injects hardcoded fake comments when the API fails (see Section 2). That behavior is **forbidden** in the new project. If the API is unavailable or quota is exhausted, the pipeline must **stop cleanly and say so**. Synthetic data is allowed **only** inside `tests/fixtures/`, clearly named `synthetic_*`, and must never appear in any reported metric, leaderboard, or README number.

**R6. YouTube quota comes first.** Every API call goes through the quota guard (Section 5). No other file may call the YouTube API directly. Default mode is **dry-run**.

**R7. Metrics come only from real runs.** Every number in the README, dashboard, and reports must be read from files in `metrics/` produced by an actual run (Section 7). Never type a metric by hand.

**R8. Keep the docs alive.** Update `README.md` and `CHANGELOG.md` at the end of every phase and after any "major change" (defined in Section 10). Record decisions in `docs/DECISIONS.md`.

**R9. Secrets.** Never print, log, or commit API keys. Keys come from environment variables / `.env` only. `.env` stays in `.gitignore`; provide `.env.example` with placeholders.

**R10. Scope discipline.** Do only what is in this prompt. If you think something extra is worth doing, put it in `docs/OPEN_QUESTIONS.md` and ask me; do not build it.

**R11. Small, reversible steps.** Prefer moving files to `archive/` over deleting. If the workspace is a git repo, commit at the end of each phase with message `phase-N: <summary>` and tag `phase-N`. Never push without my explicit permission. Never commit `data/`, `models/`, `logs/`, `state/`, or `.env`.

---

## 1. Project goal (do not deviate)

**Purpose:** A company gives a **product description**. The system (1) decides which **domain** the product belongs to, (2) separates real **influencers** from ordinary YouTube creators in that domain, and (3) **ranks the creators** most likely to deliver a successful promotional video, so the company can choose whom to sponsor.

**Honest framing (must appear in README):** public YouTube data contains no sales figures. The system therefore outputs a **Promotion-Potential Score** (a predicted promotion performance), not measured sales or ROI. Never write "ROI" or "increases sales" as a measured result.

**Required capabilities**
1. **Video → domain classification** (Spark ML), rolled up to a channel domain with a domain-focus score.
2. **Influencer vs normal creator classification** (Spark ML).
3. **Sponsorship detection** (rules first, ML optional) → sponsor brands, sponsored rate, **promo lift**.
4. **Audience-quality signals** from sampled comments on a shortlist only: purchase intent, loyalty (repeat-commenter rate), authenticity checks.
5. **Promotion-Potential Score**, per domain and per size tier, with explanation and a time-split **backtest**.
6. **App**: enter product text → domain → ranked creators → creator card; plus a **Model Results** page.
7. **Measured accuracy** of every model (train / validation / test), stored and shown.

**Big-data tools (core):** HDFS, Spark (SQL + MLlib), Parquet; Hive optional. Kafka is **optional** (see Q-INFRA in Section 3).

**Non-goals (do NOT build):** comment sentiment polarity, aspect-based sentiment, "trust / sellout / scam" verdicts, GLiNER, DistilBERT sentiment, ClickHouse, PostgreSQL, a hard dependency on Power BI, a mobile app, any scraping of YouTube, any multi-domain deep pipeline beyond the first domain until I approve (Phase 9+).

**Domain strategy:** one **deep** domain first (proposed: *Beauty & Personal Care*; I will confirm in Phase 0). The domain classifier covers several macro domains from the start (cheap). Everything domain-specific lives in `config/domains/<domain>.yaml` so a second domain can be added by config only.

---

## 2. Audit of the existing prototype (verified by me — re-verify each item yourself in Phase 0)

The zip contains: `youtube_producer.py`, `spark_processor.py`, `dashboard.py`, `domain_config.yaml`, `docker-compose.yml`, `init_db.sql`, `requirements.txt`, `README.md`, `powerbi_export/*.csv`.

| # | Finding | Action |
|---|---|---|
| A1 | `youtube_producer.py` has a **hardcoded API key** as the default of `os.getenv(...)`. | Remove; read from env only; check git history for it (`git log -S"AIza"`); tell me to revoke it. Never print it. |
| A2 | `youtube_producer.py` contains `INFLUENCER_COMMENTS_MAP` and `publish_fallback_comments_for_query`: **hand-written fake comments** pushed into Kafka when search returns nothing. | **Delete this behavior.** Archive the file. |
| A3 | `powerbi_export/live_feed_summary.csv` has 792 rows and **every row has `video_id` starting `influencer_v_`** (the fake-fallback ID). So the existing leaderboard, KPIs, and aspect tables are computed from **synthetic text**. | Re-check with a command and report the count. Move `powerbi_export/` to `archive/legacy_sentiment_prototype/` with a README saying "synthetic, do not cite". |
| A4 | The producer loops 25 `search.list` queries every ~20 s with no quota tracking, no backoff, and a catch-all `except`. | Replace with the quota guard (Section 5). |
| A5 | `spark_processor.py` loads three HuggingFace models inside a per-row UDF, calls `toPandas()` inside `foreachBatch`, and **silently falls back to a local folder** when the HDFS write fails. | Archive. Do not reuse the NLP. HDFS failures must be loud (Section 6). |
| A6 | `requirements.txt` lists `clickhouse-connect`, `torch`, `transformers`, `gliner`; `init_db.sql` (ClickHouse) is unused. | Remove; keep only what the new code uses. |
| A7 | `docker-compose.yml` runs Zookeeper, Kafka, Hadoop namenode and datanode (`bde2020/hadoop-*:2.0.0-hadoop3.2.1-java8`). | Keep Hadoop; Kafka decision in Q-INFRA. Diagnose why the HDFS write likely failed (A5) — see Phase 2. |
| A8 | No tests, no metrics, no model training, no `.env.example`. | Add per this prompt. |
| A9 | `domain_config.yaml` mixes domain keywords with creator names and sentiment words (`sellout`, `overhyped`). | Do not reuse as-is. New config per Section 4. |
| A10 | `dashboard.py` (~38 KB) is Streamlit that reads exported CSVs and starts Spark. | Rewrite per Phase 8; reuse layout ideas only after reading it. |

**Keep:** the Hadoop part of `docker-compose.yml`, the Streamlit idea, `.gitignore` patterns.

---

## 3. Phase 0 questionnaire — ask me these BEFORE writing any code

Run read-only commands first to collect facts (OS, `java -version`, `python --version`, `pyspark --version` or `pip show pyspark`, `docker --version`, `docker compose version`, free disk, RAM, CPU cores). Paste the output. Then ask (batched, using the R2 format) only what you could not determine:

- **Q-ENV:** Operating system and whether Docker Desktop / WSL2 works. Spark 3.5.x needs a compatible Java and Python — report whether the installed versions are compatible and tell me exactly what to install if not.
- **Q-DATA:** Have I downloaded **YouNiverse** (the Zenodo dataset of English YouTube channel and video metadata)? Where is it? Which of its files do I have? How much free disk do I have? (If missing, give me the official download steps, and do NOT proceed with fake data.)
- **Q-LICENSE:** Confirm the dataset's terms on its Zenodo page allow my use (I will read and answer).
- **Q-DOMAIN:** Confirm the first deep domain (recommended: Beauty & Personal Care, micro-domains skincare / makeup / haircare), and the target market and language (English only for v1? If Indian/mixed-language comments matter, say how you would handle or exclude them).
- **Q-INFRA:** Keep **Kafka**? Recommendation: remove it from the core path because ingestion is quota-limited batch work; keep a commented compose service. I decide.
- **Q-KEY:** Do I already have a new, restricted API key in `.env`? (Restrict it to YouTube Data API v3.)
- **Q-LABELS:** Can I hand-label (a) ~500 videos for domain, (b) ~300 videos for sponsored / not sponsored, (c) ~1,500 comments for purchase intent? Where will I do it (CSV is fine)? Training of those models is **blocked** until I do.
- **Q-COMPLIANCE:** YouTube's Developer Policies limit how long API data (including titles, descriptions, comment text, public stats) may be stored (30 days, then refresh or delete), with a longer allowance for derived metrics only under a policy amendment. Read the **current** policy pages (`developers.google.com/youtube/terms/developer-policies` and `.../derived-metrics-policy`) and give me a one-page summary with quotes of **what you are unsure about**. Ask me whether I will (a) keep data ≤30 days, or (b) apply for the derived-metrics amendment. Do not decide for me.
- **Q-CLUSTER:** Single machine only, or do I have a multi-node cluster for the scalability test?

Output of Phase 0: `docs/AUDIT.md` (re-verified findings A1–A10 with `path:line`), `docs/OPEN_QUESTIONS.md`, and an **implementation plan**. Then stop.

---

## 4. Target architecture and repository layout

```
project/
├── README.md            CHANGELOG.md          .env.example   .gitignore
├── Makefile             (targets: setup, test, check, dev-sample, metrics-readme)
├── requirements.txt     requirements-dev.txt
├── docker-compose.yml   (Hadoop; Kafka optional/commented)
├── config/
│   ├── settings.yaml            # paths, HDFS URI, seeds, split ratios, dev_sample_fraction
│   ├── quota.yaml               # caps (Section 5)
│   ├── quota_costs.yaml         # per-method unit costs + verified_on + source_url
│   ├── scoring.yaml             # weights for the Promotion-Potential Score
│   └── domains/
│       ├── taxonomy.yaml        # macro → micro domains (human-approved)
│       └── beauty_personal_care.yaml   # lexicons; every term has source: human|agent_proposed
├── src/
│   ├── common/      (config.py, logging_setup.py, spark_session.py, metrics_logger.py, paths.py)
│   ├── ingestion/   (quota_guard.py, yt_client.py, plan.py, load_youniverse.py)
│   ├── maintenance/ (purge_api_data.py)
│   ├── features/    (text_clean.py, channel_features.py, sponsor_rules.py)
│   ├── models/      (domain_classifier.py, influencer_classifier.py, purchase_intent.py, promo_lift_regressor.py)
│   ├── ranking/     (fit_score.py, score.py, backtest.py)
│   └── app/         (streamlit_app.py)
├── scripts/         (update_readme_metrics.py, scalability_benchmark.py, check_all.sh)
├── tests/           (unit/, spark/, fixtures/)
├── metrics/         (model_registry.csv, runs/<run_id>/..., latest.md, scalability.csv)
├── labels/          (files I label by hand)
├── docs/            (AUDIT.md, DECISIONS.md, OPEN_QUESTIONS.md, data_dictionary.md, compliance.md)
├── state/           (quota_ledger.json — gitignored)
├── logs/            (api_calls.jsonl, run logs — gitignored)
├── data/            (gitignored; local mirrors only)
└── archive/legacy_sentiment_prototype/   (old files, with a README saying "synthetic data, do not cite")
```
HDFS zones (URI from `config/settings.yaml`, never hardcoded in code): `/bda/raw/youniverse/`, `/bda/raw/api/dt=YYYY-MM-DD/` (30-day retention applies), `/bda/silver/`, `/bda/gold/`, `/bda/models/<model_name>/<run_id>/`.

---

## 5. YouTube API rules and the quota guard

**Facts to verify yourself on the official pages before coding** (record the date and URLs in `config/quota_costs.yaml`; if you cannot open them, ask me):
- Default quota: 10,000 units/day per Cloud project for general endpoints, and as of June 2026 `search.list` has its **own** default bucket (about 100 calls/day). Quota resets at **midnight Pacific time**.
- Most `*.list` read methods cost 1 unit per call (each page counts). `channels.list` and `videos.list` accept up to **50 IDs** per call.
- More quota requires a compliance audit form (weeks to months, not guaranteed). I will not wait for it: design for the default quota.
- Scraping YouTube, or using scraped YouTube data, is prohibited. Do not add scrapers or third-party scraping services. Do not create multiple Cloud projects to bypass quota.

**Design (`src/ingestion/quota_guard.py` + `yt_client.py`):**
1. **Single entry point.** `YouTubeClient` is the only code that imports `googleapiclient`.
2. **Ledger.** Persist used units per method per day to `state/quota_ledger.json`, keyed by the **America/Los_Angeles** date. The clock must be injectable for tests.
3. **Caps in `config/quota.yaml`** (my defaults, you may propose changes): `daily_unit_cap: 8000` (margin below 10,000), `search_list_daily_cap: 20`, `per_run_max_units: 1500`, `comments_max_pages_per_video: 2`, `videos_per_channel_for_comments: 10`.
4. **Reserve before call.** `guard.reserve(method, units)` raises `QuotaBudgetExceeded` **before** any network request if the cap would be exceeded.
5. **Server-side exhaustion.** On HTTP 403 with reason `quotaExceeded` (or equivalent — verify the exact reason strings in the official error docs), mark the day as exhausted in the ledger, stop all calls, log a clear message, exit non-zero. **Never** substitute fake data. A `commentsDisabled` 403 is **not** a quota error: skip that video and continue.
6. **Retry policy.** For 429/5xx only: exponential backoff with jitter, max 5 retries, then fail the item and continue. Never retry quota errors.
7. **Cheap-method policy.** Discover channels offline from YouNiverse (zero units). Get recent uploads via the channel's *uploads playlist* with `playlistItems.list` (obtain the playlist ID from `channels.list` → `contentDetails.relatedPlaylists.uploads`; **verify this field name on the first real response**). Use batched `videos.list` for statistics. Use `search.list` only for rare, explicit discovery within its own cap.
8. **Request only what you need:** the minimal `part` and `fields`.
9. **Dry-run by default.** `--live` is required to call the network. In dry-run, print the planned calls and estimated units and make **zero** network calls. Add `python -m src.ingestion.plan --channels N --videos-per-channel V --comment-videos C` that prints the estimated unit cost.
10. **Staged rollout of live calls:** `--max-units 50` (1–2 channels) → `--max-units 300` (≈10 channels) → the normal run. Report the **actual** units used versus the estimate each time.
11. **Audit log.** Append every call to `logs/api_calls.jsonl`: timestamp, method, units, a hash of the params, status. Never log the key.
12. **Retention.** `src/maintenance/purge_api_data.py` deletes raw API partitions older than `retention_days` (30 by default; start refreshing at day 25) in HDFS and local mirrors, and writes a purge report. It must support `--dry-run`.
13. **Compliance note.** Maintain `docs/compliance.md` with what you stored, where, for how long, and my answer to Q-COMPLIANCE.

**Quota guard smoke tests (no network, use a mock client):**
- `T-Q1` reserve under cap succeeds and increments the ledger.
- `T-Q2` reserve over cap raises `QuotaBudgetExceeded` and the mock network function is **never called**.
- `T-Q3` ledger rolls over at Pacific midnight (inject the clock at 23:59 and 00:01 Pacific).
- `T-Q4` a simulated 403 `quotaExceeded` marks the day exhausted; the next call raises without network.
- `T-Q5` 120 IDs are split into exactly 3 batched calls (50, 50, 20).
- `T-Q6` `search.list` uses its own cap independent of the general cap.
- `T-Q7` dry-run makes zero network calls and prints an estimate.
- `T-Q8` `commentsDisabled` does not mark the day exhausted.
- `T-Q9` the key never appears in logs (grep the log for the dummy key).
- `T-Q10` the purge job removes a 31-day-old partition and keeps a 10-day-old one (use temp dirs).

---

## 6. Data rules (YouNiverse and everything else)

- **Never assume the schema.** First task on any file: print the schema + 5 rows + null counts, then write `docs/data_dictionary.md` from what you actually saw.
- **Dev sample first.** Add `dev_sample_fraction` (or a fixed row cap) to `config/settings.yaml`. All development and tests use the dev sample. Running on the full dataset requires my explicit approval and a disk/time estimate.
- **Gzip is not splittable in Spark.** Convert the raw `.gz` TSV/JSONL files **once** to partitioned Parquet (silver), then work from Parquet. Report the row counts of raw vs Parquet (they must match).
- **The data is from 2019.** Do not describe it as current. Fresh API snapshots are only for shortlisted channels.
- **Loud failures.** HDFS write/read failures raise an error. No silent fallback to local files. If you add a local mirror, it must be an explicit `--local` flag.
- **Determinism.** Fixed seeds from `config/settings.yaml`. Do not use Python's built-in `hash()` for IDs or splits (it is randomized between runs); use Spark `xxhash64`/`crc32` or hashlib.
- **Split rule (important):** train/validation/test splits are by **channel**, never by video, so videos from one channel can't appear in both train and validation (that inflates accuracy). Default 70/15/15, stored with the seed. A test asserts no channel appears in two splits.
- **Test set discipline:** hyperparameter tuning uses train/validation only. The test set is evaluated **once** per final model.

---

## 7. Model results tracking (required for every model)

Create `src/common/metrics_logger.py` with `log_model_run(...)`. Every model script must call it. It writes:
- Append-only `metrics/model_registry.csv` with columns: `run_id, timestamp_utc, git_commit, model_name, task, algorithm, hyperparameters_json, dataset_version, split_seed, n_train, n_val, n_test, class_distribution_train_json, train_accuracy, val_accuracy, test_accuracy, train_macro_f1, val_macro_f1, test_macro_f1, val_pr_auc, val_roc_auc, train_rmse, val_rmse, test_rmse, train_mae, val_mae, train_r2, val_r2, majority_baseline_accuracy, overfit_gap_acc, train_time_s, spark_master, notes`. Leave inapplicable cells empty (not 0).
- `metrics/runs/<run_id>/metrics.json`, `params.json`, `env.json` (Python, Spark, Java versions), `per_class_report.csv`, `confusion_matrix.csv` (+ a PNG), `feature_importance.csv` where available.
- `metrics/latest.md`: auto-generated human-readable table of the **latest run of each model**.

**Rules**
- **Classifiers** must report **train accuracy AND validation accuracy** (and test at the end), macro-F1, per-class precision/recall, confusion matrix, and the **majority-class baseline accuracy**. For the imbalanced influencer classifier also report PR-AUC and ROC-AUC (accuracy alone is misleading there).
- **Regressors** (promo-lift GBT): train/val/test RMSE, MAE, R².
- **Rankers:** precision@k, NDCG@k, Spearman vs baselines (Section 9, Phase 7).
- If `train_accuracy − val_accuracy > 0.10`, set `overfit_gap_acc` and add a WARNING in `latest.md`.
- If any accuracy is **> 0.98**, treat it as suspicious: automatically run the leakage probes (duplicate texts across splits, shuffled-label test must fall to near chance, remove channel-name tokens) and report the results before you celebrate. Ask me.
- `metrics_logger` must **fail loudly** if train or validation metrics are missing or NaN.
- Save trained Spark ML models to `hdfs:/bda/models/<model_name>/<run_id>/` (and say where).
- `scripts/update_readme_metrics.py` rewrites the section between `<!-- MODEL_RESULTS_START -->` and `<!-- MODEL_RESULTS_END -->` in `README.md` from `metrics/latest.md`. Run it at the end of every phase that trains a model.
- Report results honestly: do not tune against the test set; do not hide weak classes; include sample sizes.

**Smoke tests:** `T-M1` logger writes every required key; `T-M2` logger rejects NaN/missing train or val; `T-M3` running the logger twice appends two rows and never overwrites; `T-M4` README section is replaced and the text outside the markers is unchanged.

---

## 8. Testing strategy (applies to every phase)

- `pytest` unit tests for pure Python; **Spark smoke tests** using a local session (`local[2]`) on tiny hand-made fixtures in `tests/fixtures/` (named `synthetic_*`).
- `make check` (also `scripts/check_all.sh`) runs: unit tests, Spark smoke tests, a secrets scan (`grep -rn "AIza" .` must return nothing outside `archive/` history notes), a check that **no file other than `yt_client.py` imports `googleapiclient`**, and a lint/compile pass. It must pass before every phase report.
- Every job must be **idempotent**: running it twice gives the same output (test it).
- Every Spark job prints and logs: input row count, output row count, null rate of key columns, runtime.
- **Leakage tests** where labels are derived from features (Phase 5): assert the label-defining columns are not in the feature list.
- Never test against the live API. Live runs are manual, staged (Section 5.10), and logged.
- When something fails, show me the real error text, not a summary.

---

## 9. Phases

### Phase 0 — Read-only audit, environment check, questions, plan
Tasks: Section 3. No code changes. Deliver `docs/AUDIT.md`, `docs/OPEN_QUESTIONS.md`, a written implementation plan, and a list of what I must prepare (downloads, labels).
Gate: I answer your questions and type `APPROVED PHASE 0`.

### Phase 1 — Foundation, safety, quota guard
Tasks:
1. Move legacy files to `archive/legacy_sentiment_prototype/` + a README explaining they used synthetic fallback comments.
2. Create the layout (Section 4), `config/*.yaml`, `.env.example`, updated `.gitignore`, `requirements*.txt` (verify versions you pin by `pip show` after installing; pin `pyspark` to the installed/compatible version), `Makefile`, logging setup.
3. Implement `metrics_logger.py` and `quota_guard.py` / `yt_client.py` / `plan.py` / `purge_api_data.py` exactly per Sections 5 and 7.
4. Create `README.md` skeleton (purpose, honest framing, architecture, how to run, config, results markers, limitations) and `CHANGELOG.md`.
Smoke tests: `T-Q1…T-Q10`, `T-M1…T-M4`, secrets scan, single-import check.
Gate: all tests green, `make check` output pasted, I confirm the old key is revoked.

### Phase 2 — Infrastructure and data layer
Tasks:
1. Bring up Hadoop with docker compose. **Diagnose HDFS access from the host properly.** A common problem when Spark runs on the host and Hadoop runs in Docker is that the NameNode returns the DataNode's internal Docker hostname, so writes fail. Do not assume that is the cause: reproduce, read the exception, test `hdfs dfs -put/-cat` and a tiny Spark write/read, then propose a fix (e.g., client settings for DataNode hostnames, hostname mapping, or running Spark inside the Docker network). Ask me before large changes.
2. Load YouNiverse (dev sample) into `/bda/raw/youniverse/`, convert to partitioned Parquet in `/bda/silver/` (Section 6), write `docs/data_dictionary.md`.
3. Data-quality report (row counts, null rates, duplicate IDs, date ranges, language/category distributions) into `docs/data_quality_report.md`.
Smoke tests: `T-D1` HDFS write→read round trip equals the input; `T-D2` raw vs Parquet row count equal; `T-D3` no duplicate video IDs (or documented duplicates); `T-D4` dev sample ≤ configured cap; `T-D5` job re-run is idempotent; `T-D6` HDFS failure raises (no silent fallback) — test by pointing to a wrong URI.
Gate: pasted outputs, the data dictionary matches real schemas, I approve before any full-dataset run.

### Phase 3 — Domain taxonomy and video/channel domain classifier
Tasks:
1. Propose `config/domains/taxonomy.yaml` (macro → micro) and a mapping from YouNiverse / YouTube categories to macro domains. Mark every proposed item `source: agent_proposed`. **Wait for my review.**
2. Build the labelled set: weak labels from the approved category mapping; export a stratified 500-video sample to `labels/domain_to_label.csv` for me to correct. **Do not claim accuracy against weak labels as "true accuracy"**: report it as "agreement with weak labels", and report accuracy on my hand-labelled sample separately once I provide it.
3. Text preparation: lowercase, strip URLs/emoji, join title + tags + description (truncate description; strip sponsor boilerplate/links if they leak the label).
4. Spark ML `Pipeline`: Tokenizer → StopWordsRemover → CountVectorizer/HashingTF → IDF → classifier. Train and compare: Logistic Regression, Naive Bayes, LinearSVC (OneVsRest). Tune on train/validation only (`TrainValidationSplit` or `CrossValidator`), then evaluate test once.
5. Baselines: majority class and a keyword-rule classifier.
6. Channel roll-up: mean class probability across a channel's videos → channel domain + `domain_purity` (share of videos in the top domain).
7. Log every model with the Section 7 logger (train + val accuracy, macro-F1, confusion matrix).
Smoke tests: `T-C1` pipeline fits on a 20-row fixture and outputs probabilities summing to ≈1; `T-C2` no channel in two splits; `T-C3` model beats the majority baseline on validation (if not, STOP and ask); `T-C4` shuffled-label run drops to near chance; `T-C5` saved model reloads and gives identical predictions on 10 rows; `T-C6` roll-up purity ∈ [0,1].
Gate: `metrics/latest.md` shows real numbers, the confusion matrix is reviewed by me, README results section updated.

### Phase 4 — Sponsorship detection and promo lift
Tasks:
1. Rule features from video descriptions/titles: disclosure phrases, affiliate-link patterns, promo-code patterns, UTM parameters, known sponsor brands. All patterns in config; every term tagged `source`. Do not invent brand lists; propose, then wait for my review.
2. Output per video: `is_sponsored` (rule-based), evidence fields, extracted brand candidates.
3. Evaluate the rules against my hand-labelled ~300-video sample (`labels/sponsor_to_label.csv`): precision, recall, F1. If I have not labelled yet, report **"unvalidated"** and say so everywhere. No invented accuracy.
4. Optional ML text classifier for undisclosed ads (only after the rule baseline is validated; ask me).
5. Per channel: `sponsored_rate`, `distinct_brands`, `repeat_sponsor_count`, **`promo_lift`** = median performance of sponsored videos ÷ the channel's own non-sponsored baseline (define "performance" with views and engagement; document the exact formula; require a minimum number of videos on each side, else null — not 0).
Smoke tests: `T-S1` rules flag 10 handwritten positive and 10 negative fixture strings correctly; `T-S2` promo-lift = null when too few videos; `T-S3` promo-lift for a fixture channel equals a hand-computed value; `T-S4` no division by zero.
Gate: rule P/R/F1 on my labels (or "unvalidated"), 20 random flagged videos shown to me for review.

### Phase 5 — Channel features and influencer-vs-normal classifier
Tasks:
1. **Ask me to choose the label definition first (R2).** Options: (A) rank-based using the dataset's channel rank plus sponsorship activity; (B) threshold rule on reach + sponsorship; (C) clustering to discover tiers, then I name them. Recommend one, explain the circularity risk.
2. Features from silver data (verify availability): log subscribers, median views, views÷subscribers, engagement rate, comment rate, upload cadence, weekly growth and acceleration from the time series, view consistency (coefficient of variation), channel age, domain purity.
3. **Leakage guard:** features used for training must be disjoint from features used to define labels. Add the test.
4. Train Random Forest and GBT (and Logistic Regression baseline) with class weights; report class balance, PR-AUC, ROC-AUC, F1 for the positive class, train/val/test accuracy and the majority baseline.
5. Also assign size tiers (nano/micro/macro/mega) from **this dataset's** own quantiles; document the cut points. Do not hardcode tier thresholds from blogs.
Smoke tests: `T-I1` label-defining columns ∩ feature columns = ∅; `T-I2` tiers are exhaustive and mutually exclusive; `T-I3` model beats baseline PR-AUC; `T-I4` class weights applied (print the weight column summary); `T-I5` feature nulls handled (no silent drops — print counts).
Gate: metrics logged, feature importance reviewed by me, README updated.

### Phase 6 — Live enrichment funnel, comments, audience-quality signals
Funnel: offline filters (domain match + influencer classifier + fit/reach/engagement/momentum from YouNiverse) → shortlist of ~500 → fresh API metadata for the shortlist → ~200 → comment sampling → ~50 → my manual audit.
Tasks:
1. Implement the funnel stages with explicit row counts at each stage logged.
2. Fresh metadata via `YouTubeClient` only (Section 5), staged live rollout, actual-vs-estimated units reported. Write to `/bda/raw/api/dt=YYYY-MM-DD/`.
3. Comment sampling per the caps in `config/quota.yaml`. Record how many comments were English / dropped, and how many videos had comments disabled.
4. **Purchase-intent classifier:** first a transparent rule baseline (phrases such as "where to buy", "link?", "ordered", "used your code" — all from config, tagged `source`). Then a Spark ML classifier **only after** I provide `labels/purchase_intent_labelled.csv`. Export an unlabelled stratified sample for me; **BLOCKED until I label** (do not label it yourself). Apply Wilson-lower-bound (or Bayesian) smoothing to per-channel rates so tiny samples cannot look perfect.
5. **Loyalty proxy:** repeat-commenter rate across a creator's sampled videos using **hashed** author IDs (hash with a salt kept in `.env`); no raw usernames stored in derived tables.
6. **Authenticity checks:** duplicate-comment share, commenter concentration, sudden subscriber spikes from the time series. Output a penalty in [0,1].
7. Respect Q-COMPLIANCE: comment text and other raw API data follow the retention policy; derived numbers follow whatever I chose.
Smoke tests: `T-L1` funnel stage counts are non-increasing; `T-L2` smoothing makes 1-of-1 positive < 1-of-100 positive×… (assert smoothed(1,1) < smoothed(50,100)×1.0 for the chosen formula — document it); `T-L3` hashed IDs are stable across runs and not reversible by simple lookup (salt present); `T-L4` pipeline with the quota exhausted stops cleanly, writes partial results, and no fake rows exist; `T-L5` actual units ≤ cap.
Gate: actual API units used shown, shortlist table, labelling status.

### Phase 7 — Promotion-Potential Score, calibration, backtest
Tasks:
1. **Fit score:** TF-IDF cosine similarity between the product brief and each channel's text profile (same Spark ML TF-IDF stack; no external embedding service unless I approve).
2. **Score** in `config/scoring.yaml` (starting weights are hypotheses to be calibrated): fit 25, conversion evidence 25 (promo lift, smoothed purchase intent, promo-code/link usage, repeat sponsors), real reach 15 (median views on recent **non-sponsored** videos, views÷subscribers), engagement quality 15 (tier-adjusted, minus authenticity penalty), momentum 10, consistency 10; penalties for sponsor saturation and competitor-brand exposure. Normalise with percentile rank **within domain and tier**. Missing components: renormalise weights and flag the creator `partial_evidence=true`; never impute silently.
3. **Explainability:** store each component's contribution per creator.
4. **Calibration:** train a `GBTRegressor` to predict promo lift from the other features (log train/val/test RMSE, MAE, R²). Compare its ranking to the weighted score with Spearman.
5. **Backtest (time split):** pick a cutoff date T that leaves enough later sponsored videos (verify they exist; else ask me). Rank using data ≤ T; evaluate on videos after T: precision@k, NDCG@k, Spearman, versus baselines "rank by subscribers" and "rank by median views". Report honestly if the score does not beat baselines.
6. **Budget portfolio (simple):** given my budget and an optional rate card (I provide; no hardcoded prices), choose a mix of tiers by expected engagement per currency unit using a documented greedy method.
Smoke tests: `T-R1` weights sum to 100 and every component ∈ [0,1]; `T-R2` identical inputs → identical scores; `T-R3` a fixture creator with a missing component is flagged and weights renormalise; `T-R4` percentile normalisation is within domain/tier; `T-R5` backtest uses **no** data after T for ranking (assert max date ≤ T); `T-R6` NDCG on a hand-made ranking equals the hand-computed value.
Gate: backtest table, calibration metrics, README updated.

### Phase 8 — App and exports
Tasks: rewrite the Streamlit app to **read precomputed gold tables** (Parquet/CSV) — it must not start Spark per page load.
Pages: (1) **Find influencers** — product text → predicted domain with probability → ranked table with tier filter and component breakdown; (2) **Creator card** — score components, sponsor history, partial-evidence flag; (3) **Model Results** — reads `metrics/model_registry.csv`: train vs validation vs test accuracy per model, confusion matrices, overfit warnings; (4) **Pipeline status** — quota ledger usage today, last API run, retention status, data freshness date.
Add a clearly visible disclaimer: "Predicted promotion potential from public data; not measured sales."
Optional CSV export for Power BI (only if I ask).
Smoke tests: `T-A1` app imports without Spark; `T-A2` empty/odd product text handled; `T-A3` Model Results page renders from a sample registry; `T-A4` no number on the app is hardcoded (grep for literals in the metrics page).
Gate: I click through it; screenshots saved for my report.

### Phase 9 — Scalability benchmark, final documentation
Tasks: `scripts/scalability_benchmark.py` times a chosen heavy job (e.g., feature build + domain scoring) with `local[1]`, `local[2]`, `local[4]` (or executors if I have a cluster, Q-CLUSTER) and CSV vs Parquet vs Parquet-partitioned-by-domain; writes `metrics/scalability.csv`; plot saved. Finalise README (full architecture diagram in text, run instructions from a clean clone, metrics table, limitations, compliance notes), `docs/DECISIONS.md`, and a `docs/REPORT_NUMBERS.md` listing every number I may cite and the file it came from.
Smoke tests: clean-clone dry run of `make setup && make check` on the dev sample.
Gate: final review. Second-domain scaling is a **separate** task I will request.

---

## 10. README and CHANGELOG policy

Update `README.md` at the end of every phase and immediately after any **major change**: new/removed module, changed architecture or data flow, new/changed model or feature set, changed metrics definition, new dependency, new config key, quota or retention policy change, new run command, a decision that changes scope. Keep these sections current: Purpose and honest framing • Architecture (text diagram) • Repository layout • Setup (exact commands, versions) • How to run each stage • API quota and compliance rules • Data sources and their limits • **Model Results (auto-generated between markers)** • Known limitations • Roadmap.
`CHANGELOG.md`: dated entries, newest first: *Added / Changed / Removed / Fixed*, plus the phase tag and the metric run IDs produced. Never describe something in the README that does not exist or was not run.

---

## 11. Phase Report template (post at the end of every phase, then stop)

```
## Phase N report
1. What changed (files created/modified/moved, with paths)
2. Commands run and REAL output of: make check, the phase smoke tests
3. Metrics produced (run_ids; train/val/test accuracy etc. read from metrics/latest.md)
4. API units used today (from the ledger) vs the cap
5. Assumptions I made (each also in docs/DECISIONS.md)
6. Things I could not verify
7. Open questions for you (R2 format)
8. README/CHANGELOG sections updated
9. Proposed plan for Phase N+1
Waiting for: APPROVED PHASE N
```

---

## 12. Definition of done

- Old synthetic data and the exposed key are gone from the active code; the quota guard is the only API path; dry-run is the default.
- Every model has logged **train, validation and test** results in `metrics/model_registry.csv`, shown on the app and in the README.
- Domain classifier, influencer classifier, sponsorship detection, scoring, and backtest all run end to end on the dev sample, and on the full data only with my approval.
- `make check` passes from a clean clone.
- No number in any document lacks a source file under `metrics/` or `docs/`.
- Limitations are stated honestly: no sales data, 2019 base data, sampled comments, weak labels where used.

Start now with **Phase 0** only. Do not write or change any code until I type `APPROVED PHASE 0`.
