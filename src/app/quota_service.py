"""
src/app/quota_service.py
Pure Pacific-day quota inspection, rollover calculation, and safety validation for YouTube API access.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python < 3.9 fallback, though python is 3.11+
    from dateutil.tz import gettz as ZoneInfo

from src.common.paths import project_root

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")
DAILY_UNIT_CAP = 8000
SEARCH_LIST_DAILY_CAP = 20
PER_RUN_MAX_UNITS = 1500


def get_pacific_now(now_dt: datetime | None = None) -> datetime:
    """Return datetime in America/Los_Angeles timezone, allowing clock injection."""
    if now_dt is None:
        return datetime.now(PACIFIC_TZ)
    if now_dt.tzinfo is None:
        # Assume UTC if naive
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    return now_dt.astimezone(PACIFIC_TZ)


def get_pacific_date_key(now_dt: datetime | None = None) -> str:
    """Return YYYY-MM-DD string for current Pacific date."""
    return get_pacific_now(now_dt).strftime("%Y-%m-%d")


def time_until_pacific_midnight(now_dt: datetime | None = None) -> tuple[int, int, str]:
    """
    Calculate hours and minutes until next Pacific midnight.
    Returns (hours, minutes, formatted_str).
    """
    pac_now = get_pacific_now(now_dt)
    # Next midnight in Pacific time
    pac_tomorrow = (pac_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    diff = pac_tomorrow - pac_now
    total_seconds = int(diff.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return hours, minutes, f"{hours}h {minutes:02d}m"


def inspect_quota_status(
    ledger: dict[str, Any] | None = None,
    now_dt: datetime | None = None,
    daily_cap: int = DAILY_UNIT_CAP,
    search_cap: int = SEARCH_LIST_DAILY_CAP,
    per_run_cap: int = PER_RUN_MAX_UNITS,
) -> dict[str, Any]:
    """
    Pure inspection of current quota ledger and caps.
    Handles Pacific midnight rollover automatically.
    """
    if ledger is None:
        p = project_root() / "state" / "quota_ledger.json"
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    ledger = json.load(f)
            except Exception:
                ledger = {}
        else:
            ledger = {}

    today_key = get_pacific_date_key(now_dt)
    today_entry = ledger.get(today_key, {"units_used": 0, "search_calls": 0, "exhausted": False})

    units_used = int(today_entry.get("units_used", 0))
    search_used = int(today_entry.get("search_calls", 0))
    is_exhausted = bool(today_entry.get("exhausted", False))

    remaining_units = max(0, daily_cap - units_used)
    remaining_searches = max(0, search_cap - search_used)

    hrs, mins, time_str = time_until_pacific_midnight(now_dt)

    return {
        "today_key": today_key,
        "daily_unit_cap": daily_cap,
        "search_list_cap": search_cap,
        "per_run_cap": per_run_cap,
        "units_used": units_used,
        "search_used": search_used,
        "remaining_units": remaining_units,
        "remaining_searches": remaining_searches,
        "is_exhausted": is_exhausted,
        "pct_used": round((units_used / max(1, daily_cap)) * 100, 1),
        "time_to_reset": time_str,
        "hours_to_reset": hrs,
        "minutes_to_reset": mins,
    }


def validate_api_action(
    mode: str,
    estimated_units: int,
    confirmed_live: bool,
    quota_status: dict[str, Any],
    requires_search: bool = True,
) -> tuple[bool, str]:
    """
    Determine whether the action is permitted.
    Returns (is_allowed, explanation).
    """
    mode_lower = mode.strip().lower()
    is_live = "live" in mode_lower

    if not is_live:
        return True, "Dry Run enabled: 0 quota units consumed. Simulation only."

    if not confirmed_live:
        return False, "Live mode requires explicit user confirmation before executing."

    if quota_status.get("is_exhausted", False):
        return False, "YouTube API daily quota is marked as exhausted by Google API servers (HTTP 403 quotaExceeded)."

    per_run_cap = quota_status.get("per_run_cap", PER_RUN_MAX_UNITS)
    if estimated_units > per_run_cap:
        return False, f"Estimated cost ({estimated_units} units) exceeds per-run safety limit of {per_run_cap} units."

    remaining_units = quota_status.get("remaining_units", 0)
    if estimated_units > remaining_units:
        return False, f"Estimated cost ({estimated_units} units) exceeds remaining daily budget ({remaining_units} units left)."

    if requires_search:
        remaining_searches = quota_status.get("remaining_searches", 0)
        if remaining_searches <= 0:
            return False, "Daily search.list call cap (20/day) has been reached for today."

    return True, f"Action permitted. Estimated consumption: {estimated_units} units."


def get_seven_day_quota_history(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract last 7 recorded days from ledger in chronological order.
    """
    if not ledger:
        return []
    sorted_dates = sorted([k for k in ledger.keys() if len(k) == 10 and k.count("-") == 2])
    recent_dates = sorted_dates[-7:]
    history = []
    for d in recent_dates:
        entry = ledger.get(d, {})
        history.append({
            "date": d,
            "units_used": int(entry.get("units_used", 0)),
            "search_calls": int(entry.get("search_calls", 0)),
            "exhausted": bool(entry.get("exhausted", False)),
        })
    return history
