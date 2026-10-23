"""
src/enrichment/youtube_client.py
Phase 6 — YouTube Data API v3 client with QuotaGuard.

Design principles:
  - Dry-run by default.  The --live flag (or YT_MODE=live env var) is required
    before any network call is made.
  - Every API call is gated through QuotaGuard which tracks daily and per-run
    quota consumption against config/quota.yaml thresholds.
  - All API calls are logged to logs/api_calls.jsonl for auditability.
  - Exponential back-off with jitter is applied on retryable HTTP errors.

Quota costs (from config/quota_costs.yaml):
  channels.list    : 1 unit
  videos.list      : 1 unit
  commentThreads.list : 1 unit
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

import requests
import yaml

from src.common.logging_setup import setup_logging
from src.common.paths import local

logger = setup_logging(__name__)

_QUOTA_CFG_PATH = Path(__file__).resolve().parents[2] / "config" / "quota.yaml"
_QUOTA_COSTS_PATH = Path(__file__).resolve().parents[2] / "config" / "quota_costs.yaml"
_API_BASE = "https://www.googleapis.com/youtube/v3"


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ─────────────────────────────────────────────────────────────────────────────
# QuotaGuard
# ─────────────────────────────────────────────────────────────────────────────

class QuotaExceededError(RuntimeError):
    """Raised when a quota limit would be breached."""


class QuotaGuard:
    """
    Thread-safe (single-process) quota tracker.

    Tracks units consumed in the current run and validates against:
      - per_run_max_units
      - daily_unit_cap  (informational; actual enforcement relies on Google)
    """

    def __init__(self, per_run_max: int | None = None) -> None:
        cfg = _load_yaml(_QUOTA_CFG_PATH)
        self._per_run_max = per_run_max if per_run_max is not None else cfg["per_run_max_units"]
        self._daily_cap = cfg["daily_unit_cap"]
        self._costs = _load_yaml(_QUOTA_COSTS_PATH)
        self._used: int = 0
        self._retry_cfg = cfg.get("retry", {})

    def cost_of(self, endpoint: str) -> int:
        """Return quota units for the given endpoint key (e.g. 'channels.list')."""
        return int(self._costs.get(endpoint, {}).get("units", 1))

    def check_and_consume(self, endpoint: str, n_calls: int = 1) -> None:
        """
        Raise QuotaExceededError if consuming n_calls × cost(endpoint) would
        exceed per_run_max_units; otherwise debit the units.
        """
        units = self.cost_of(endpoint) * n_calls
        if self._used + units > self._per_run_max:
            raise QuotaExceededError(
                f"QuotaGuard: consuming {units} units for '{endpoint}' would exceed "
                f"per-run cap ({self._used}/{self._per_run_max}). Aborting."
            )
        self._used += units
        logger.debug(
            "[QuotaGuard] consumed %d units for %s (total=%d/%d)",
            units, endpoint, self._used, self._per_run_max,
        )

    @property
    def units_used(self) -> int:
        return self._used

    @property
    def units_remaining(self) -> int:
        return max(0, self._per_run_max - self._used)

    def can_afford(self, endpoint: str, n_calls: int = 1) -> bool:
        units = self.cost_of(endpoint) * n_calls
        return self._used + units <= self._per_run_max


# ─────────────────────────────────────────────────────────────────────────────
# API call logger
# ─────────────────────────────────────────────────────────────────────────────

def _log_api_call(endpoint: str, params: dict, status: int, units: int, error: str | None = None) -> None:
    log_path = local("logs") / "api_calls.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "params": {k: v for k, v in params.items() if k != "key"},  # never log API key
        "status_code": status,
        "units_charged": units,
        "error": error,
    }
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Retry decorator
# ─────────────────────────────────────────────────────────────────────────────

def _with_retry(fn, retry_cfg: dict):
    """Call fn() with exponential back-off + jitter on retryable HTTP errors."""
    max_retries = retry_cfg.get("max_retries", 5)
    base = retry_cfg.get("base_backoff_s", 1.0)
    cap = retry_cfg.get("max_backoff_s", 60.0)
    jitter = retry_cfg.get("jitter", True)
    retryable = set(retry_cfg.get("retryable_http_codes", [429, 500, 502, 503, 504]))

    for attempt in range(max_retries + 1):
        try:
            return fn()
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if attempt == max_retries or code not in retryable:
                raise
            delay = min(base * (2 ** attempt), cap)
            if jitter:
                delay *= random.uniform(0.75, 1.25)
            logger.warning(
                "[Retry] HTTP %d on attempt %d/%d. Sleeping %.1fs …",
                code, attempt + 1, max_retries, delay,
            )
            time.sleep(delay)


# ─────────────────────────────────────────────────────────────────────────────
# YouTubeClient
# ─────────────────────────────────────────────────────────────────────────────

class YouTubeClient:
    """
    Thin wrapper around the YouTube Data API v3.

    Instantiate with mode='dry_run' (default) to prevent any network calls.
    Switch to mode='live' only for bounded, quota-approved runs.

    Parameters
    ----------
    mode          : 'dry_run' | 'live'
    per_run_max   : override per-run quota cap (default from quota.yaml)
    api_key       : explicit key override (default: YOUTUBE_API_KEY env var)
    """

    def __init__(
        self,
        mode: str = "dry_run",
        per_run_max: int | None = None,
        api_key: str | None = None,
    ) -> None:
        self.mode = mode
        self._key = api_key or os.environ.get("YOUTUBE_API_KEY", "")
        self._quota = QuotaGuard(per_run_max=per_run_max)
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

        if self.mode == "live" and not self._key:
            raise EnvironmentError(
                "YOUTUBE_API_KEY env var is not set. "
                "Set it before switching to live mode."
            )
        if self.mode == "live":
            logger.info(
                "[YouTubeClient] LIVE mode — quota cap %d units/run.",
                self._quota._per_run_max,
            )
        else:
            logger.info("[YouTubeClient] DRY-RUN mode — no network calls will be made.")

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get(self, resource: str, params: dict) -> dict:
        """
        Execute a GET against the YouTube API, charging quota via QuotaGuard.
        In dry-run mode, returns an empty stub immediately.
        """
        endpoint_key = resource  # e.g. "channels.list"
        units = self._quota.cost_of(endpoint_key)
        self._quota.check_and_consume(endpoint_key)

        if self.mode == "dry_run":
            _log_api_call(endpoint_key, params, status=0, units=units, error="DRY_RUN")
            return {"items": [], "_dry_run": True}

        # YouTube Data API v3 REST endpoint is the resource name (e.g. search, channels, videos)
        endpoint_path = resource.split(".")[0]
        url = f"{_API_BASE}/{endpoint_path}"
        req_params = {**params, "key": self._key}

        def _do_request():
            resp = self._session.get(url, params=req_params, timeout=15)
            resp.raise_for_status()
            return resp.json()

        retry_cfg = _load_yaml(_QUOTA_CFG_PATH).get("retry", {})
        try:
            data = _with_retry(_do_request, retry_cfg)
            _log_api_call(endpoint_key, params, status=200, units=units)
            return data
        except requests.HTTPError as exc:
            # Sanitize any API key from exception text to enforce R9 secrets rule
            sanitized_err = re.sub(r'key=[^&\s]+', 'key=REDACTED', str(exc))
            code = exc.response.status_code if exc.response is not None else 0
            _log_api_call(endpoint_key, params, status=code, units=units, error=sanitized_err)
            raise requests.HTTPError(sanitized_err, response=exc.response) from None

    # ── Public API methods ────────────────────────────────────────────────────

    def get_channel_stats(self, channel_ids: list[str]) -> list[dict]:
        """
        Fetch live subscriber/view/video counts for up to 50 channel IDs.
        Returns a list of channel items (empty in dry-run).

        Cost: 1 unit per call (up to 50 IDs per call).
        """
        if not channel_ids:
            return []
        # YouTube allows up to 50 IDs per request
        chunks = [channel_ids[i:i + 50] for i in range(0, len(channel_ids), 50)]
        results = []
        for chunk in chunks:
            params = {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(chunk),
                "maxResults": 50,
            }
            data = self._get("channels.list", params)
            results.extend(data.get("items", []))
        logger.info("[YT] get_channel_stats: fetched %d channel records.", len(results))
        return results

    def get_top_videos(self, channel_id: str, max_results: int = 10) -> list[dict]:
        """
        Fetch top N videos for a channel ordered by view count.
        Cost: 1 unit per call.
        """
        params = {
            "part": "snippet,statistics",
            "channelId": channel_id,
            "order": "viewCount",
            "type": "video",
            "maxResults": min(max_results, 50),
        }
        data = self._get("search.list", params)
        items = data.get("items", [])
        logger.debug("[YT] get_top_videos(%s): %d videos", channel_id, len(items))
        return items

    def search_creators(
        self,
        query: str,
        max_results: int = 25,
        language: str = "en",
        region_code: str = "US",
    ) -> list[dict]:
        """
        Discover creator channels for a search query using search.list (type=video).
        Returns video items with channelId and channelTitle (real channel name).
        Cost: 100 quota units per call.
        """
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "relevanceLanguage": language,
            "regionCode": region_code,
        }
        data = self._get("search.list", params)
        items = data.get("items", [])
        logger.info("[YT] search_creators('%s'): found %d video items.", query, len(items))
        return items


    def iter_comment_threads(
        self,
        video_id: str,
        max_pages: int = 2,
    ) -> Generator[dict, None, None]:
        """
        Yield comment thread items for a video, up to max_pages pages.
        Each page = 1 quota unit.

        In dry-run mode, yields nothing.
        """
        page_token: str | None = None
        for page_num in range(max_pages):
            if not self._quota.can_afford("commentThreads.list"):
                logger.warning("[YT] Quota insufficient for commentThreads.list. Stopping.")
                break
            params: dict[str, Any] = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": 100,
                "order": "relevance",
                "textFormat": "plainText",
            }
            if page_token:
                params["pageToken"] = page_token
            data = self._get("commentThreads.list", params)

            for item in data.get("items", []):
                yield item

            page_token = data.get("nextPageToken")
            if not page_token:
                break
            logger.debug("[YT] comment page %d/%d for video %s", page_num + 2, max_pages, video_id)

    @property
    def quota(self) -> QuotaGuard:
        return self._quota
