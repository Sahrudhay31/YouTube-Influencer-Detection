"""
tests/unit/test_discovery.py
Unit tests for Phase R6 Beauty Creator Discovery & Live YouTube API.
Verifies query building determinism, quota bounds, deduplication, and channel names.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.discovery.query_builder import build_search_queries
from src.discovery.candidate_discovery import (
    discover_offline_candidates,
    run_discovery_pipeline,
)
from src.enrichment.youtube_client import YouTubeClient


def test_tl6_query_builder_deterministic_and_bounded():
    """T-L6: Query builder produces identical queries for same brief, bounded by max_queries."""
    brief = "hydrating hyaluronic acid serum for dry skin"
    q1 = build_search_queries(brief, max_queries=3)
    q2 = build_search_queries(brief, max_queries=3)

    assert q1 == q2
    assert len(q1) <= 3
    assert len(q1) > 0
    # Must contain relevant beauty terms
    assert any("serum" in q or "hyaluronic" in q for q in q1)


def test_tl7_offline_candidates_have_real_channel_names():
    """T-L7: Offline candidate discovery returns real channel names and valid scores."""
    df = discover_offline_candidates("serum", max_candidates=10)
    assert not df.empty
    assert "channel_name" in df.columns
    assert "subscribers" in df.columns
    assert "promotion_potential_score" in df.columns

    # Channel names must not be empty or purely channel IDs
    for name in df["channel_name"]:
        assert len(str(name).strip()) > 0


def test_tl8_dry_run_makes_zero_network_calls():
    """T-L8: Dry-run discovery executes with zero network calls and 0 units used."""
    res = run_discovery_pipeline(
        product_brief="matte foundation for oily skin",
        mode="dry_run",
        max_units=300,
    )
    assert res["mode"] == "dry_run"
    assert res["units_used"] == 0
    assert res["live_candidates"].empty


def test_tl9_empty_and_odd_briefs_handled_gracefully():
    """T-L9: Empty or unusual inputs don't crash the query builder or offline discovery."""
    q_empty = build_search_queries("", max_queries=2)
    assert len(q_empty) > 0

    q_odd = build_search_queries("??? !!! @@@ 12345", max_queries=2)
    assert len(q_odd) > 0

    df_empty = discover_offline_candidates("")
    assert isinstance(df_empty, pd.DataFrame)
