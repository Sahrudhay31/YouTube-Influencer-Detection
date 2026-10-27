"""
tests/unit/test_api_server.py
Unit tests for FastAPI endpoints in CreatorPulse web application.
Direct function calls to avoid external testclient dependencies.
"""
import pytest
from src.api.server import (
    health_check,
    get_platform_stats,
    get_categories,
    list_creators,
    get_creator_detail,
    get_supported_domains,
    run_live_search,
    LiveSearchRequest,
)


def test_api_health():
    data = health_check()
    assert data["status"] == "healthy"
    assert "HDFS" in data["storage"]
    assert data["total_creators"] > 0


def test_api_stats():
    data = get_platform_stats()
    assert "total_creators" in data
    assert "exploding_creators" in data
    assert data["total_creators"] >= 2600


def test_api_categories():
    cats = get_categories()
    assert len(cats) > 0
    assert cats[0]["id"] == "all"


def test_api_creators_list():
    data = list_creators(limit=5)
    assert len(data["items"]) == 5
    assert "promotion_score" in data["items"][0]
    assert "sparkline" in data["items"][0]
    assert len(data["items"][0]["sparkline"]) == 12


def test_api_creators_search():
    data = list_creators(search="beauty", limit=3)
    assert "items" in data
    assert len(data["items"]) <= 3


def test_api_domains():
    data = get_supported_domains()
    assert "domains" in data
    assert len(data["domains"]) >= 8
    domain_ids = [d["id"] for d in data["domains"]]
    assert "technology" in domain_ids
    assert "gaming_entertainment" in domain_ids
    assert "fitness_health" in domain_ids
    assert "finance_investing" in domain_ids
    assert "beauty_personal_care" in domain_ids


def test_api_live_search_multidomain():
    req = LiveSearchRequest(query="M4 macbook pro apple silicon review", domain="technology", mode="dry_run")
    res = run_live_search(req)
    assert res["mode"] == "dry_run"
    assert res["detected_domain"] == "technology"
    assert len(res["planned_queries"]) > 0


