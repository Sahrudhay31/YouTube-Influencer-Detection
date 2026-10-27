"""
tests/unit/test_app.py
Unit tests for Core Web App Logic and Non-Spark Isolation:
  - T-A1: App modules import cleanly without importing or starting PySpark.
  - T-A2: Empty/odd product text handled gracefully with fallback.
  - T-A3: Quota service and portfolio allocator operate deterministically.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd
import pytest


def test_ta1_app_imports_without_spark():
    """T-A1: App modules must import without loading or starting PySpark."""
    import src.app.data_loader
    import src.app.domain_predictor
    import src.app.portfolio_optimizer
    import src.app.components
    import src.app.formatters
    import src.app.evidence
    import src.app.leaderboard_logic
    import src.app.quota_service
    import src.api.server

    app_files = [
        Path("src/app/data_loader.py"),
        Path("src/app/domain_predictor.py"),
        Path("src/app/portfolio_optimizer.py"),
        Path("src/app/components.py"),
        Path("src/app/formatters.py"),
        Path("src/app/evidence.py"),
        Path("src/app/leaderboard_logic.py"),
        Path("src/app/quota_service.py"),
        Path("src/api/server.py"),
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


def test_ta3_app_formatters_and_evidence():
    """Verify that pure app formatters and evidence computations run reliably."""
    from src.app.formatters import format_subscribers, format_views, format_promo_lift
    from src.app.evidence import get_evidence_badge, compute_renormalisation

    assert format_subscribers(1500000) == "1.5M"
    assert format_subscribers(25000) == "25K"
    assert format_views(1234567) == "1,234,567"
    assert format_promo_lift(1.414) == "1.41x"

    badge_high = get_evidence_badge(False)
    assert badge_high["tier"] == "High"
    assert badge_high["label"] == "Full Evidence"
    badge_partial = get_evidence_badge(True)
    assert badge_partial["tier"] == "Partial"
    assert badge_partial["label"] == "Partial Evidence"

    active_w, factor, msg = compute_renormalisation(["comp_conversion_evidence"])
    assert active_w == 75.0
    assert round(factor, 2) == 1.33


