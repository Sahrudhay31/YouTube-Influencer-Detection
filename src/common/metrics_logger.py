"""
src/common/metrics_logger.py
Append-only model run logger. Every model training script must call log_model_run().

Rules (Section 7 of project prompt):
- Fails loudly if train or validation metrics are missing or NaN.
- Appends a row to metrics/model_registry.csv (never overwrites).
- Writes per-run detail files under metrics/runs/<run_id>/.
- Auto-generates metrics/latest.md with the latest run of each model.
"""
from __future__ import annotations

import csv
import json
import math
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.common.paths import local

# ── Registry CSV column order ──────────────────────────────────────────────────
REGISTRY_COLUMNS = [
    "run_id", "timestamp_utc", "git_commit", "model_name", "task",
    "algorithm", "hyperparameters_json", "dataset_version", "split_seed",
    "n_train", "n_val", "n_test",
    "class_distribution_train_json",
    "train_accuracy", "val_accuracy", "test_accuracy",
    "train_macro_f1", "val_macro_f1", "test_macro_f1",
    "val_pr_auc", "val_roc_auc",
    "train_rmse", "val_rmse", "test_rmse",
    "train_mae", "val_mae",
    "train_r2", "val_r2",
    "majority_baseline_accuracy",
    "overfit_gap_acc",
    "train_time_s",
    "spark_master",
    "notes",
]

# Required fields — log_model_run raises ValueError if any are NaN or absent.
_REQUIRED_FIELDS = {
    "model_name", "task", "algorithm",
    "n_train", "n_val",
    "train_accuracy", "val_accuracy",
}

_OVERFIT_THRESHOLD = 0.10  # warn if train_acc - val_acc > this


def _is_nan_or_none(v: Any) -> bool:
    if v is None:
        return True
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return False


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _python_info() -> dict[str, str]:
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "spark_version": _spark_version(),
        "java_version": _java_version(),
    }


def _spark_version() -> str:
    try:
        import pyspark
        return pyspark.__version__
    except ImportError:
        return "not_installed"


def _java_version() -> str:
    try:
        result = subprocess.run(
            ["java", "-version"], capture_output=True, text=True, timeout=5
        )
        # java -version writes to stderr
        return (result.stderr or result.stdout).splitlines()[0]
    except Exception:
        return "unknown"


def log_model_run(
    *,
    model_name: str,
    task: str,
    algorithm: str,
    hyperparameters: dict[str, Any] | None = None,
    dataset_version: str = "unknown",
    split_seed: int | None = None,
    n_train: int,
    n_val: int,
    n_test: int | None = None,
    class_distribution_train: dict[str, int] | None = None,
    train_accuracy: float | None = None,
    val_accuracy: float | None = None,
    test_accuracy: float | None = None,
    train_macro_f1: float | None = None,
    val_macro_f1: float | None = None,
    test_macro_f1: float | None = None,
    val_pr_auc: float | None = None,
    val_roc_auc: float | None = None,
    train_rmse: float | None = None,
    val_rmse: float | None = None,
    test_rmse: float | None = None,
    train_mae: float | None = None,
    val_mae: float | None = None,
    train_r2: float | None = None,
    val_r2: float | None = None,
    majority_baseline_accuracy: float | None = None,
    train_time_s: float | None = None,
    spark_master: str | None = None,
    per_class_report: list[dict[str, Any]] | None = None,
    confusion_matrix: list[list[int]] | None = None,
    feature_importance: list[dict[str, Any]] | None = None,
    notes: str = "",
    run_id: str | None = None,
) -> str:
    """
    Log a model run. Returns the run_id.

    Raises
    ------
    ValueError
        If any required metric is missing or NaN.
    """
    # ── Validation ────────────────────────────────────────────────────────────
    if task == "regression":
        for field in ("train_rmse", "val_rmse"):
            val = locals()[field]
            if _is_nan_or_none(val):
                raise ValueError(
                    f"metrics_logger: '{field}' is missing or NaN for model '{model_name}'. "
                    "Regression training must produce a real metric before logging."
                )
    else:
        for field in ("train_accuracy", "val_accuracy"):
            val = locals()[field]
            if _is_nan_or_none(val):
                raise ValueError(
                    f"metrics_logger: '{field}' is missing or NaN for model '{model_name}'. "
                    "Training must produce a real metric before logging."
                )

    # ── Overfit check ─────────────────────────────────────────────────────────
    overfit_gap: float | None = None
    overfit_warning = ""
    if train_accuracy is not None and val_accuracy is not None:
        gap = train_accuracy - val_accuracy
        if gap > _OVERFIT_THRESHOLD:
            overfit_gap = gap
            overfit_warning = (
                f"⚠️ OVERFIT WARNING: train_acc - val_acc = {gap:.4f} "
                f"(threshold {_OVERFIT_THRESHOLD})"
            )

    # ── Suspicious accuracy check ─────────────────────────────────────────────
    for metric_name, metric_val in [
        ("train_accuracy", train_accuracy),
        ("val_accuracy", val_accuracy),
    ]:
        if metric_val is not None and metric_val > 0.98:
            notes = (
                f"⚠️ SUSPICIOUS: {metric_name}={metric_val:.4f} > 0.98. "
                "Run leakage probes (duplicate texts, shuffled-label test, "
                "channel-name token removal) before reporting. " + notes
            )

    # ── Build run record ──────────────────────────────────────────────────────
    run_id = run_id or str(uuid.uuid4())[:12]
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    git_commit = _git_commit()

    row: dict[str, Any] = {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "git_commit": git_commit,
        "model_name": model_name,
        "task": task,
        "algorithm": algorithm,
        "hyperparameters_json": json.dumps(hyperparameters or {}),
        "dataset_version": dataset_version,
        "split_seed": split_seed,
        "n_train": n_train,
        "n_val": n_val,
        "n_test": n_test,
        "class_distribution_train_json": json.dumps(class_distribution_train or {}),
        "train_accuracy": train_accuracy,
        "val_accuracy": val_accuracy,
        "test_accuracy": test_accuracy,
        "train_macro_f1": train_macro_f1,
        "val_macro_f1": val_macro_f1,
        "test_macro_f1": test_macro_f1,
        "val_pr_auc": val_pr_auc,
        "val_roc_auc": val_roc_auc,
        "train_rmse": train_rmse,
        "val_rmse": val_rmse,
        "test_rmse": test_rmse,
        "train_mae": train_mae,
        "val_mae": val_mae,
        "train_r2": train_r2,
        "val_r2": val_r2,
        "majority_baseline_accuracy": majority_baseline_accuracy,
        "overfit_gap_acc": overfit_gap,
        "train_time_s": train_time_s,
        "spark_master": spark_master,
        "notes": (overfit_warning + " " + notes).strip(),
    }

    # ── Write to registry CSV ─────────────────────────────────────────────────
    metrics_dir = local("metrics")
    metrics_dir.mkdir(parents=True, exist_ok=True)
    registry_path = metrics_dir / "model_registry.csv"
    write_header = not registry_path.exists()

    with open(registry_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REGISTRY_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in REGISTRY_COLUMNS})

    # ── Write per-run detail files ────────────────────────────────────────────
    run_dir = metrics_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(
            {k: row[k] for k in [
                "run_id", "model_name", "task", "algorithm",
                "train_accuracy", "val_accuracy", "test_accuracy",
                "train_macro_f1", "val_macro_f1", "test_macro_f1",
                "val_pr_auc", "val_roc_auc",
                "train_rmse", "val_rmse", "test_rmse",
                "overfit_gap_acc", "majority_baseline_accuracy",
            ]},
            f, indent=2,
        )

    with open(run_dir / "params.json", "w", encoding="utf-8") as f:
        json.dump(
            {k: row[k] for k in [
                "hyperparameters_json", "dataset_version", "split_seed",
                "n_train", "n_val", "n_test", "class_distribution_train_json",
                "train_time_s", "spark_master",
            ]},
            f, indent=2,
        )

    with open(run_dir / "env.json", "w", encoding="utf-8") as f:
        json.dump(_python_info(), f, indent=2)

    if per_class_report:
        _write_csv(run_dir / "per_class_report.csv", per_class_report)

    if confusion_matrix:
        _write_confusion_matrix(run_dir, confusion_matrix)

    if feature_importance:
        _write_csv(run_dir / "feature_importance.csv", feature_importance)

    # ── Update metrics/latest.md ──────────────────────────────────────────────
    _update_latest_md(metrics_dir, registry_path)

    return run_id


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


def _write_confusion_matrix(run_dir: Path, matrix: list[list[int]]) -> None:
    n = len(matrix)
    with open(run_dir / "confusion_matrix.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([f"pred_{i}" for i in range(n)])
        for row in matrix:
            writer.writerow(row)


def _update_latest_md(metrics_dir: Path, registry_path: Path) -> None:
    """Regenerate metrics/latest.md from the registry CSV."""
    if not registry_path.exists():
        return

    latest: dict[str, dict[str, Any]] = {}
    with open(registry_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            latest[row["model_name"]] = row  # last row wins (append-only, newest last)

    lines = [
        "# Latest Model Results\n",
        "> Auto-generated by `src/common/metrics_logger.py`. Do not edit manually.\n\n",
        "| Model | Task | Algorithm | Train Acc | Val Acc | Test Acc | Val F1 | Val PR-AUC | Overfit | Notes |",
        "|-------|------|-----------|-----------|---------|----------|--------|------------|---------|-------|",
    ]

    for model_name, row in sorted(latest.items()):
        overfit = row.get("overfit_gap_acc", "")
        overfit_str = f"⚠️ {float(overfit):.3f}" if overfit else "✅"
        notes = row.get("notes", "")
        lines.append(
            f"| {model_name} | {row.get('task','')} | {row.get('algorithm','')} "
            f"| {row.get('train_accuracy','')} | {row.get('val_accuracy','')} "
            f"| {row.get('test_accuracy','')} | {row.get('val_macro_f1','')} "
            f"| {row.get('val_pr_auc','')} | {overfit_str} | {notes[:60]} |"
        )

    lines.append("")
    lines.append(f"\n_Last updated: {datetime.now(timezone.utc).isoformat()}_\n")

    with open(metrics_dir / "latest.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
