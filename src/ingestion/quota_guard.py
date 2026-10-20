"""
src/ingestion/quota_guard.py
YouTube API quota guard — the ONLY code that controls quota.

Design (Section 5 of project prompt):
- Ledger persisted to state/quota_ledger.json, keyed by America/Los_Angeles date.
- reserve(method, units) raises QuotaBudgetExceeded BEFORE any network call.
- HTTP 403 quotaExceeded marks the day exhausted; commentsDisabled does not.
- Clock is injectable for testing.
- The key NEVER appears in any log.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.common.config import get_quota_config, project_root
from src.common.logging_setup import setup_logging

logger = setup_logging(__name__)

# ── Exception types ───────────────────────────────────────────────────────────


class QuotaBudgetExceeded(Exception):
    """Raised when reserving quota would exceed a configured cap."""


class QuotaServerExhausted(Exception):
    """Raised when the YouTube server returns quotaExceeded (HTTP 403)."""


# ── Ledger file path ──────────────────────────────────────────────────────────
_LEDGER_PATH = project_root() / "state" / "quota_ledger.json"
_LOCK = threading.Lock()

# ── 403 error reason strings from the YouTube API ─────────────────────────────
# Source: https://developers.google.com/youtube/v3/docs/errors (verify before live use)
_QUOTA_EXCEEDED_REASONS = frozenset({"quotaExceeded", "dailyLimitExceeded"})
_COMMENTS_DISABLED_REASONS = frozenset({"commentsDisabled", "forbidden"})


# ── Internal helpers ──────────────────────────────────────────────────────────

def _pacific_date(clock: Callable[[], datetime] | None = None) -> str:
    """Return today's date in America/Los_Angeles as YYYY-MM-DD string."""
    try:
        from zoneinfo import ZoneInfo  # Python 3.9+
        tz = ZoneInfo("America/Los_Angeles")
    except ImportError:
        import datetime as _dt
        # Fallback: UTC-8 offset (ignores DST; acceptable for quota reset purposes)
        tz = timezone(timezone.utc.utcoffset(None) - _dt.timedelta(hours=8))  # type: ignore[arg-type]

    if clock is not None:
        try:
            now = clock(tz)
        except TypeError:
            now = clock()
    else:
        now = datetime.now(tz)
    if now.tzinfo is not None:
        now = now.astimezone(tz)
    return now.strftime("%Y-%m-%d")


def _load_ledger() -> dict:
    if not _LEDGER_PATH.exists():
        return {}
    try:
        with open(_LEDGER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.warning("Quota ledger corrupted; starting fresh.")
        return {}


def _save_ledger(ledger: dict) -> None:
    _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_LEDGER_PATH, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)


def _day_entry(ledger: dict, date_str: str) -> dict:
    return ledger.setdefault(date_str, {"units_used": 0, "search_calls": 0, "exhausted": False})


# ── QuotaGuard ────────────────────────────────────────────────────────────────


class QuotaGuard:
    """
    Thread-safe quota guard.

    Parameters
    ----------
    clock : callable | None
        Injected clock function returning a datetime for testing.
        Must return a timezone-aware datetime, or a naive datetime treated as Pacific.
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock
        self._cfg = get_quota_config()
        self._daily_cap: int = self._cfg["daily_unit_cap"]
        self._search_cap: int = self._cfg["search_list_daily_cap"]
        self._per_run_cap: int = self._cfg["per_run_max_units"]
        self._run_units: int = 0

    def _today(self) -> str:
        return _pacific_date(self._clock)

    def _cost(self, method: str) -> int:
        from src.common.config import get_quota_costs
        costs = get_quota_costs()
        return costs.get("methods", {}).get(method, {}).get("cost_per_call", 1)

    def reserve(self, method: str, units: int | None = None) -> None:
        """
        Reserve quota units BEFORE making a network call.

        Raises QuotaBudgetExceeded if any cap would be exceeded.
        Does NOT make a network call.

        Parameters
        ----------
        method : str
            YouTube API method name (e.g., 'channels.list').
        units : int | None
            Units to reserve. Defaults to the cost from quota_costs.yaml.
        """
        if units is None:
            units = self._cost(method)

        with _LOCK:
            ledger = _load_ledger()
            today = self._today()
            day = _day_entry(ledger, today)

            if day["exhausted"]:
                raise QuotaBudgetExceeded(
                    f"Quota already marked exhausted for {today} (server returned quotaExceeded). "
                    "Resets at midnight America/Los_Angeles."
                )

            if day["units_used"] + units > self._daily_cap:
                raise QuotaBudgetExceeded(
                    f"Reserving {units} units for {method} would exceed daily cap "
                    f"({day['units_used']} + {units} > {self._daily_cap})."
                )

            if method == "search.list":
                if day["search_calls"] + 1 > self._search_cap:
                    raise QuotaBudgetExceeded(
                        f"search.list daily cap of {self._search_cap} calls reached "
                        f"(used {day['search_calls']})."
                    )
                day["search_calls"] += 1

            if self._run_units + units > self._per_run_cap:
                raise QuotaBudgetExceeded(
                    f"Reserving {units} units for {method} would exceed per-run cap "
                    f"({self._run_units} + {units} > {self._per_run_cap})."
                )

            day["units_used"] += units
            self._run_units += units
            _save_ledger(ledger)
            logger.debug(
                "QuotaGuard reserved %d unit(s) for %s. Day total: %d/%d, run total: %d/%d",
                units, method, day["units_used"], self._daily_cap,
                self._run_units, self._per_run_cap,
            )

    def mark_server_exhausted(self) -> None:
        """Called when the YouTube server returns quotaExceeded."""
        with _LOCK:
            ledger = _load_ledger()
            today = self._today()
            day = _day_entry(ledger, today)
            day["exhausted"] = True
            _save_ledger(ledger)
        logger.error(
            "QuotaGuard: server returned quotaExceeded. "
            "Day %s marked exhausted. All further API calls are blocked. "
            "Quota resets at midnight America/Los_Angeles.", today
        )

    def is_exhausted(self) -> bool:
        with _LOCK:
            ledger = _load_ledger()
            today = self._today()
            return _day_entry(ledger, today).get("exhausted", False)

    def usage_today(self) -> dict:
        with _LOCK:
            ledger = _load_ledger()
            today = self._today()
            return dict(_day_entry(ledger, today))

    def split_ids_into_batches(self, ids: list[str], batch_size: int = 50) -> list[list[str]]:
        """Split a list of IDs into batches of at most batch_size."""
        return [ids[i:i + batch_size] for i in range(0, len(ids), batch_size)]

    @classmethod
    def classify_403(cls, reason: str) -> str:
        """
        Classify a 403 error reason.

        Returns
        -------
        'quota_exceeded' | 'comments_disabled' | 'other_forbidden'
        """
        if reason in _QUOTA_EXCEEDED_REASONS:
            return "quota_exceeded"
        if reason in _COMMENTS_DISABLED_REASONS:
            return "comments_disabled"
        return "other_forbidden"
