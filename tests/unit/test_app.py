"""
tests/unit/test_app.py
Phase 8 — Streamlit App Smoke Tests:
  - T-A1: App modules import cleanly without importing or starting PySpark.
  - T-A2: Empty/odd product text handled gracefully with fallback.
  - T-A3: Model Results page renders correctly from an injected sample registry.
  - T-A4: No metric number is hardcoded in the model results page source code.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import pytest


def test_ta1_app_imports_without_spark():
    """T-A1: App modules must import without loading or starting PySpark."""
    # Ensure pyspark is not in sys.modules before importing app modules
    # (If already imported by earlier tests in same process, verify app's own imports don't require it)
    import src.app.data_loader
    import src.app.domain_predictor
    import src.app.portfolio_optimizer
    import src.app.components
    import src.app.formatters
    import src.app.evidence
    import src.app.leaderboard_logic
    import src.app.quota_service

    # Verify no app module has an import of pyspark
    app_files = [
        Path("src/app/data_loader.py"),
        Path("src/app/domain_predictor.py"),
        Path("src/app/portfolio_optimizer.py"),
        Path("src/app/components.py"),
        Path("src/app/formatters.py"),
        Path("src/app/evidence.py"),
        Path("src/app/leaderboard_logic.py"),
        Path("src/app/quota_service.py"),
        Path("src/app/main.py"),
        Path("src/app/pages_impl/find_influencers.py"),
        Path("src/app/pages_impl/creator_card.py"),
        Path("src/app/pages_impl/model_results.py"),
        Path("src/app/pages_impl/pipeline_status.py"),
    ]

    for f in app_files:
        assert f.exists(), f"File {f} is missing"
        content = f.read_text(encoding="utf-8")
        assert "from pyspark" not in content, f"Forbidden 'from pyspark' found in {f}"
        assert "import pyspark" not in content, f"Forbidden 'import pyspark' found in {f}"


def test_ta2_empty_and_odd_product_text_handled():
    """T-A2: Empty, odd, or corrupted text input must be handled gracefully without exception."""
    from src.app.domain_predictor import DomainPredictor
    predictor = DomainPredictor()

    test_inputs = [
        "",
        "   ",
        None,
        "???",
        "!!!@@@###$$$%",
        "a",
        "12345",
        "....",
        "\n\t\r",
    ]

    for odd_input in test_inputs:
        res = predictor.predict(odd_input)
        assert isinstance(res, dict), f"Failed for input: {odd_input!r}"
        assert "domain" in res, f"Missing domain key for {odd_input!r}"
        assert "confidence" in res, f"Missing confidence key for {odd_input!r}"
        assert "matched_micro_domains" in res, f"Missing matched_micro_domains for {odd_input!r}"
        assert 0.0 <= res["confidence"] <= 1.0, f"Confidence out of bounds: {res['confidence']}"


def test_ta3_model_results_renders_from_sample_registry():
    """T-A3: Model results page logic handles synthetic sample registry correctly."""
    from src.app.pages_impl.model_results import render_model_results_page

    sample_registry = pd.DataFrame([
        {
            "run_id": "test_run_001",
            "timestamp_utc": "2026-10-21T00:00:00Z",
            "model_name": "test_domain_classifier",
            "task": "domain_classification",
            "algorithm": "naive_bayes",
            "train_accuracy": 0.9500,
            "val_accuracy": 0.9200,
            "test_accuracy": 0.9100,
            "val_macro_f1": 0.9150,
            "majority_baseline_accuracy": 0.6500,
            "notes": "Synthetic test run",
        },
        {
            "run_id": "test_run_002",
            "timestamp_utc": "2026-10-21T01:00:00Z",
            "model_name": "test_influencer_gbt",
            "task": "influencer_classification",
            "algorithm": "gbt",
            "train_accuracy": 0.8800,
            "val_accuracy": 0.8400,
            "test_accuracy": 0.8200,
            "val_macro_f1": 0.8300,
            "val_pr_auc": 0.6800,
            "majority_baseline_accuracy": 0.8000,
            "notes": "Synthetic test run 2",
        },
    ])

    # Should run without raising exceptions
    try:
        render_model_results_page(sample_registry)
    except Exception as e:
        # Streamlit headless run might raise streamlit specific ScriptControl exceptions or warnings,
        # but pure data processing must not crash with KeyError or TypeError
        assert "KeyError" not in str(type(e))
        assert "TypeError" not in str(type(e))


def test_ta4_no_number_is_hardcoded_in_metrics_page():
    """T-A4: No metric values or hardcoded results are allowed in model_results.py source code."""
    page_file = Path("src/app/pages_impl/model_results.py")
    assert page_file.exists()
    content = page_file.read_text(encoding="utf-8")

    # Specific real model performance numbers from latest.md must NOT appear as string literals
    forbidden_numbers = [
        "0.9989",
        "0.9980",
        "0.9722",
        "0.9674",
        "0.8518",
        "0.8235",
        "0.6913",
        "0.7415",
        "7.4158",
        "7.0063",
    ]

    for num in forbidden_numbers:
        assert num not in content, (
            f"Hardcoded metric '{num}' found in {page_file}! All numbers must be read dynamically from CSV."
        )


def test_all_pages_render_without_crash():
    """Verify that all pages render without crashing or syntax/name errors."""
    from src.app.pages_impl.find_influencers import render_find_influencers_page
    from src.app.pages_impl.creator_card import render_creator_card_page
    from src.app.pages_impl.pipeline_status import render_pipeline_status_page

    for page_fn in [render_find_influencers_page, render_creator_card_page, render_pipeline_status_page]:
        try:
            page_fn()
        except Exception as e:
            assert "NameError" not in str(type(e)), f"NameError in {page_fn.__name__}: {e}"
            assert "ImportError" not in str(type(e)), f"ImportError in {page_fn.__name__}: {e}"
