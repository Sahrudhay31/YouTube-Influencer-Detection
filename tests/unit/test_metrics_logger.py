"""
tests/unit/test_metrics_logger.py
Smoke tests T-M1 through T-M4 for the metrics logger.
"""
from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.common import metrics_logger as ml


def _patched_logger(tmp_path: Path):
    """Context manager that patches metrics/ to a temp directory."""
    return patch.object(
        ml,
        "local",
        side_effect=lambda key, *parts: (
            tmp_path / "metrics" / Path(*parts) if parts else tmp_path / "metrics"
        ),
    )


# ── T-M1: logger writes every required key ────────────────────────────────────

def test_tm1_logger_writes_all_required_keys(tmp_path):
    """T-M1: log_model_run writes all REGISTRY_COLUMNS to the CSV."""
    with patch("src.common.metrics_logger.local") as mock_local:
        mock_local.return_value = tmp_path / "metrics"
        (tmp_path / "metrics" / "runs").mkdir(parents=True, exist_ok=True)
        run_id = ml.log_model_run(
            model_name="test_model",
            task="classification",
            algorithm="LogisticRegression",
            n_train=100,
            n_val=20,
            train_accuracy=0.85,
            val_accuracy=0.82,
        )

    registry = tmp_path / "metrics" / "model_registry.csv"
    assert registry.exists(), "model_registry.csv not created"
    with open(registry, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 1
    row = rows[0]
    # All required columns present
    for col in ml.REGISTRY_COLUMNS:
        assert col in row, f"Missing column: {col}"
    assert row["model_name"] == "test_model"
    assert row["run_id"] == run_id


# ── T-M2: logger rejects NaN / missing train or val accuracy ─────────────────

def test_tm2_logger_rejects_nan_accuracy():
    """T-M2: missing train_accuracy raises ValueError immediately."""
    import math
    with pytest.raises(ValueError, match="train_accuracy"):
        ml.log_model_run(
            model_name="bad_model",
            task="classification",
            algorithm="LR",
            n_train=50,
            n_val=10,
            train_accuracy=math.nan,
            val_accuracy=0.80,
        )

    with pytest.raises(ValueError, match="val_accuracy"):
        ml.log_model_run(
            model_name="bad_model",
            task="classification",
            algorithm="LR",
            n_train=50,
            n_val=10,
            train_accuracy=0.80,
            val_accuracy=None,  # type: ignore[arg-type]
        )


# ── T-M3: running logger twice appends two rows, never overwrites ─────────────

def test_tm3_two_runs_append_two_rows(tmp_path):
    """T-M3: calling log_model_run twice appends two rows to the CSV."""
    with patch("src.common.metrics_logger.local") as mock_local:
        mock_local.return_value = tmp_path / "metrics"
        (tmp_path / "metrics" / "runs").mkdir(parents=True, exist_ok=True)

        ml.log_model_run(
            model_name="model_a",
            task="classification",
            algorithm="LR",
            n_train=100,
            n_val=20,
            train_accuracy=0.85,
            val_accuracy=0.82,
        )
        ml.log_model_run(
            model_name="model_b",
            task="classification",
            algorithm="RF",
            n_train=100,
            n_val=20,
            train_accuracy=0.90,
            val_accuracy=0.88,
        )

    registry = tmp_path / "metrics" / "model_registry.csv"
    with open(registry, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
    names = {r["model_name"] for r in rows}
    assert "model_a" in names and "model_b" in names


# ── T-M4: README section is replaced, text outside markers unchanged ──────────

def test_tm4_readme_section_replaced(tmp_path):
    """T-M4: update_readme_metrics.py replaces only between the markers."""
    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        "# My Project\n"
        "Some intro text.\n"
        "<!-- MODEL_RESULTS_START -->\n"
        "OLD CONTENT\n"
        "<!-- MODEL_RESULTS_END -->\n"
        "## Other Section\n"
        "Footer text.\n",
        encoding="utf-8",
    )
    latest_md = tmp_path / "latest.md"
    latest_md.write_text("| new | table | row |\n", encoding="utf-8")

    import scripts.update_readme_metrics as urm
    with patch.object(urm, "README_PATH", readme_path):
        with patch.object(urm, "LATEST_MD_PATH", latest_md):
            urm.update_readme()

    result = readme_path.read_text(encoding="utf-8")
    assert "# My Project" in result
    assert "Some intro text." in result
    assert "Footer text." in result
    assert "OLD CONTENT" not in result
    assert "new | table | row" in result
    assert "<!-- MODEL_RESULTS_START -->" in result
    assert "<!-- MODEL_RESULTS_END -->" in result
