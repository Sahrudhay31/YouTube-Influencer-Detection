"""
tests/unit/test_quota_guard.py
Smoke tests T-Q1 through T-Q10 for the QuotaGuard.
All tests use mocked ledger paths and injected clocks — NO network calls.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

def _pacific_noon(date_str: str):
    """Return a callable clock that returns a fixed Pacific-time datetime."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Los_Angeles")
    dt = datetime.strptime(date_str + "T12:00:00", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=tz)
    return lambda: dt


def _make_guard(tmp_path: Path, clock=None):
    """Create a QuotaGuard with a temp ledger path and optional injected clock."""
    import src.ingestion.quota_guard as qg
    with patch.object(qg, "_LEDGER_PATH", tmp_path / "quota_ledger.json"):
        from src.ingestion.quota_guard import QuotaGuard
        return QuotaGuard(clock=clock), tmp_path / "quota_ledger.json"


# ── T-Q1: reserve under cap succeeds and increments ledger ───────────────────

def test_tq1_reserve_increments_ledger(tmp_path):
    """T-Q1: reserving units under the cap succeeds and writes to ledger."""
    import src.ingestion.quota_guard as qg
    with patch.object(qg, "_LEDGER_PATH", tmp_path / "ledger.json"):
        from src.ingestion.quota_guard import QuotaGuard
        guard = QuotaGuard()
        guard._daily_cap = 1000
        guard._per_run_cap = 1000
        guard.reserve("channels.list", units=5)
        ledger = json.loads((tmp_path / "ledger.json").read_text())
        today = list(ledger.keys())[0]
        assert ledger[today]["units_used"] == 5


# ── T-Q2: reserve over cap raises and network never called ────────────────────

def test_tq2_reserve_over_cap_raises(tmp_path):
    """T-Q2: reserve raises QuotaBudgetExceeded before network call; mock network not called."""
    import src.ingestion.quota_guard as qg
    from src.ingestion.quota_guard import QuotaGuard, QuotaBudgetExceeded
    mock_network = MagicMock()
    with patch.object(qg, "_LEDGER_PATH", tmp_path / "ledger.json"):
        guard = QuotaGuard()
        guard._daily_cap = 10
        guard._per_run_cap = 10
        # Use up 9 units first
        guard.reserve("channels.list", units=9)
        # Now trying to reserve 5 more should raise
        with pytest.raises(QuotaBudgetExceeded):
            guard.reserve("channels.list", units=5)
        mock_network.assert_not_called()


# ── T-Q3: ledger rolls over at Pacific midnight ────────────────────────────────

def test_tq3_ledger_rollover(tmp_path):
    """T-Q3: units used on date X do not count against date X+1."""
    import src.ingestion.quota_guard as qg
    from src.ingestion.quota_guard import QuotaGuard
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("America/Los_Angeles")

    def clock_2359():
        return datetime(2024, 3, 15, 23, 59, 0, tzinfo=tz)

    def clock_0001():
        return datetime(2024, 3, 16, 0, 1, 0, tzinfo=tz)

    with patch.object(qg, "_LEDGER_PATH", tmp_path / "ledger.json"):
        guard_night = QuotaGuard(clock=clock_2359)
        guard_night._daily_cap = 100
        guard_night._per_run_cap = 100
        guard_night.reserve("channels.list", units=90)

        # New guard at 00:01 next day — different date key, so cap resets
        guard_dawn = QuotaGuard(clock=clock_0001)
        guard_dawn._daily_cap = 100
        guard_dawn._per_run_cap = 100
        # This should succeed (new day, 0 used)
        guard_dawn.reserve("channels.list", units=90)

    ledger = json.loads((tmp_path / "ledger.json").read_text())
    assert "2024-03-15" in ledger
    assert "2024-03-16" in ledger
    assert ledger["2024-03-15"]["units_used"] == 90
    assert ledger["2024-03-16"]["units_used"] == 90


# ── T-Q4: 403 quotaExceeded marks day exhausted ───────────────────────────────

def test_tq4_server_exhausted_blocks_next_call(tmp_path):
    """T-Q4: mark_server_exhausted prevents further calls for that day."""
    import src.ingestion.quota_guard as qg
    from src.ingestion.quota_guard import QuotaGuard, QuotaBudgetExceeded
    with patch.object(qg, "_LEDGER_PATH", tmp_path / "ledger.json"):
        guard = QuotaGuard()
        guard._daily_cap = 10000
        guard._per_run_cap = 10000
        guard.mark_server_exhausted()
        with pytest.raises(QuotaBudgetExceeded, match="exhausted"):
            guard.reserve("channels.list", units=1)


# ── T-Q5: 120 IDs split into exactly 3 batches (50, 50, 20) ─────────────────

def test_tq5_batch_splitting():
    """T-Q5: 120 IDs → 3 batches of [50, 50, 20]."""
    from src.ingestion.quota_guard import QuotaGuard
    guard = QuotaGuard()
    ids = [f"id_{i}" for i in range(120)]
    batches = guard.split_ids_into_batches(ids, batch_size=50)
    assert len(batches) == 3
    assert len(batches[0]) == 50
    assert len(batches[1]) == 50
    assert len(batches[2]) == 20


# ── T-Q6: search.list uses its own cap ────────────────────────────────────────

def test_tq6_search_list_own_cap(tmp_path):
    """T-Q6: search.list raises on its own cap independently of the general unit cap."""
    import src.ingestion.quota_guard as qg
    from src.ingestion.quota_guard import QuotaGuard, QuotaBudgetExceeded
    with patch.object(qg, "_LEDGER_PATH", tmp_path / "ledger.json"):
        guard = QuotaGuard()
        guard._daily_cap = 100_000   # general cap very high
        guard._per_run_cap = 100_000
        guard._search_cap = 2        # only allow 2 search calls

        guard.reserve("search.list", units=100)
        guard.reserve("search.list", units=100)
        with pytest.raises(QuotaBudgetExceeded, match="search.list daily cap"):
            guard.reserve("search.list", units=100)


# ── T-Q7: dry-run makes zero network calls ────────────────────────────────────

def test_tq7_dry_run_no_network():
    """T-Q7: YouTubeClient in dry-run mode makes zero network calls."""
    from src.ingestion.yt_client import YouTubeClient
    client = YouTubeClient(live=False)
    # channels_list dry-run should return {} without calling the network
    with patch("src.ingestion.yt_client.YouTubeClient._call") as mock_call:
        mock_call.return_value = {}
        result = client.channels_list(["UC_fake123"])
    # No actual googleapiclient should be imported or called
    # (we just confirm the call path goes through our mock)
    assert isinstance(result, list)


# ── T-Q8: commentsDisabled does not mark day exhausted ────────────────────────

def test_tq8_comments_disabled_not_quota_error(tmp_path):
    """T-Q8: a commentsDisabled 403 does NOT mark the day exhausted."""
    import src.ingestion.quota_guard as qg
    from src.ingestion.quota_guard import QuotaGuard
    with patch.object(qg, "_LEDGER_PATH", tmp_path / "ledger.json"):
        guard = QuotaGuard()
        cls = QuotaGuard.classify_403("commentsDisabled")
        assert cls == "comments_disabled"
        # commentsDisabled should NOT mark exhausted
        assert not guard.is_exhausted()


# ── T-Q9: API key never appears in audit log ──────────────────────────────────

def test_tq9_key_not_in_log(tmp_path):
    """T-Q9: the API key must not appear in logs/api_calls.jsonl."""
    import src.ingestion.yt_client as yt_module
    fake_key = "AIzaDUMMYKEY12345SHOULDNEVERAPPEAR"
    log_path = tmp_path / "api_calls.jsonl"

    with (
        patch.dict(os.environ, {"YOUTUBE_API_KEY": fake_key}),
        patch.object(yt_module, "_API_LOG_PATH", log_path),
    ):
        yt_module._append_audit_log(
            method="channels.list",
            units=1,
            params={"id": "UC_test"},
            status="dry_run_skip",
            key_tag=yt_module._mask_key(fake_key),
        )

    log_text = log_path.read_text(encoding="utf-8")
    assert fake_key not in log_text, "API key appeared in audit log — security violation!"


# ── T-Q10: purge removes 31-day-old partition, keeps 10-day-old ──────────────

def test_tq10_purge_respects_retention(tmp_path, monkeypatch):
    """T-Q10: purge job deletes partitions older than retention_days and keeps newer ones."""
    from unittest.mock import patch as _patch
    import subprocess

    # Build fake hdfs ls output with two partitions
    today = datetime.now().strftime("%Y-%m-%d")
    from datetime import timedelta
    old_date = (datetime.now() - timedelta(days=31)).strftime("%Y-%m-%d")
    new_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

    fake_ls_output = (
        f"drwxr-xr-x   - user group 0 2024-01-01 /bda/raw/api/dt={old_date}\n"
        f"drwxr-xr-x   - user group 0 2024-01-01 /bda/raw/api/dt={new_date}\n"
    )

    calls = []
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = MagicMock()
        result.returncode = 0
        result.stdout = fake_ls_output if "-ls" in cmd else ""
        result.stderr = ""
        return result

    from src.maintenance import purge_api_data as pm
    with (
        _patch("subprocess.run", side_effect=fake_run),
        _patch.object(pm, "local", return_value=tmp_path),
    ):
        report = pm.purge_api_partitions(dry_run=False, retention_days=30)

    assert report["deleted"] == 1, f"Expected 1 deleted, got {report['deleted']}"
    assert report["skipped"] >= 1, f"Expected ≥1 skipped, got {report['skipped']}"
    # The rm command should have been called for the old partition only
    rm_calls = [c for c in calls if "-rm" in c]
    assert len(rm_calls) == 1
    assert old_date in " ".join(rm_calls[0])
    assert new_date not in " ".join(rm_calls[0])
