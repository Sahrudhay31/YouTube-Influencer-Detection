"""
src/ingestion/yt_client.py
ONLY file that imports googleapiclient. All YouTube API calls go through here.

Design (Section 5):
- Never prints or logs the API key.
- Reads key from YOUTUBE_API_KEY environment variable only.
- Dry-run by default; --live flag required for network calls.
- Exponential backoff with jitter for 429/5xx (not for quota errors).
- On quotaExceeded 403: marks day exhausted, raises QuotaServerExhausted.
- On commentsDisabled 403: skips the video and continues.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from src.common.config import get_quota_config, project_root
from src.common.logging_setup import setup_logging
from src.ingestion.quota_guard import QuotaGuard, QuotaBudgetExceeded, QuotaServerExhausted

logger = setup_logging(__name__)

_API_LOG_PATH = project_root() / "logs" / "api_calls.jsonl"


def _mask_key(key: str) -> str:
    """Return a non-reversible tag for the key — never the key itself."""
    return "key:" + hashlib.sha256(key.encode()).hexdigest()[:8]


def _param_hash(params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def _append_audit_log(
    method: str,
    units: int,
    params: dict,
    status: str,
    key_tag: str,
) -> None:
    """Append one entry to logs/api_calls.jsonl. Never logs the real key."""
    _API_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "units": units,
        "param_hash": _param_hash(params),
        "status": status,
        "key_tag": key_tag,  # hash of the key — not the key itself
    }
    with open(_API_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


class YouTubeClient:
    """
    Quota-guarded YouTube Data API v3 client.

    Parameters
    ----------
    live : bool
        If False (default), dry-run mode: no network calls are made.
    guard : QuotaGuard | None
        Injected guard for testing. Creates a default one if None.
    max_units : int | None
        Per-run unit ceiling (overrides config if set).
    """

    def __init__(
        self,
        live: bool = False,
        guard: QuotaGuard | None = None,
        max_units: int | None = None,
    ) -> None:
        self._live = live
        self._guard = guard or QuotaGuard()
        if max_units is not None:
            self._guard._per_run_cap = max_units

        self._key_tag = "dry_run"
        self._youtube: Any = None

        if live:
            key = os.environ.get("YOUTUBE_API_KEY", "")
            if not key:
                raise EnvironmentError(
                    "YOUTUBE_API_KEY environment variable is not set. "
                    "Set it in .env or export it before running with --live."
                )
            self._key_tag = _mask_key(key)
            # Defer actual import — this is the ONLY place googleapiclient is imported.
            try:
                from googleapiclient.discovery import build  # noqa: PLC0415
                self._youtube = build("youtube", "v3", developerKey=key)
                logger.info("YouTubeClient: live mode, key_tag=%s", self._key_tag)
            except ImportError:
                raise ImportError(
                    "google-api-python-client is not installed. "
                    "Run: pip install google-api-python-client"
                )
        else:
            logger.info("YouTubeClient: DRY-RUN mode (no network calls).")

    # ── Internal call helper ──────────────────────────────────────────────────

    def _call(
        self, method: str, units: int, params: dict, request_fn
    ) -> dict:
        """
        Reserve quota, execute the request with retry, and log the call.
        Never retries quota errors.
        """
        self._guard.reserve(method, units)
        _append_audit_log(method, units, params, "reserved", self._key_tag)

        if not self._live:
            logger.info("[DRY-RUN] Would call %s with params_hash=%s (%d units)",
                        method, _param_hash(params), units)
            _append_audit_log(method, units, params, "dry_run_skip", self._key_tag)
            return {}

        cfg = get_quota_config()["retry"]
        backoff = cfg["base_backoff_s"]
        for attempt in range(cfg["max_retries"] + 1):
            try:
                response = request_fn()
                _append_audit_log(method, units, params, "success", self._key_tag)
                return response
            except Exception as exc:
                http_code, reason = self._extract_http_error(exc)
                if http_code == 403:
                    cls = QuotaGuard.classify_403(reason)
                    if cls == "quota_exceeded":
                        self._guard.mark_server_exhausted()
                        _append_audit_log(method, units, params, "quota_exhausted", self._key_tag)
                        raise QuotaServerExhausted(
                            f"YouTube server returned quotaExceeded on {method}. "
                            "Day marked exhausted. Pipeline stopping."
                        ) from exc
                    elif cls == "comments_disabled":
                        _append_audit_log(method, units, params, "comments_disabled", self._key_tag)
                        logger.info("commentsDisabled for %s — skipping.", params.get("videoId", "?"))
                        return {"_comments_disabled": True}
                    else:
                        _append_audit_log(method, units, params, f"http_403_{reason}", self._key_tag)
                        raise

                if http_code in cfg["retryable_http_codes"] and attempt < cfg["max_retries"]:
                    jitter = random.uniform(0, backoff * 0.3) if cfg["jitter"] else 0
                    sleep_s = min(backoff + jitter, cfg["max_backoff_s"])
                    logger.warning(
                        "%s HTTP %d (attempt %d/%d). Retrying in %.1fs.",
                        method, http_code, attempt + 1, cfg["max_retries"], sleep_s
                    )
                    time.sleep(sleep_s)
                    backoff *= 2
                else:
                    _append_audit_log(method, units, params, f"error_http_{http_code}", self._key_tag)
                    raise

        raise RuntimeError(f"Exhausted retries for {method}")  # pragma: no cover

    @staticmethod
    def _extract_http_error(exc: Exception) -> tuple[int, str]:
        """Extract HTTP status and error reason from a googleapiclient HttpError."""
        try:
            status = exc.resp.status  # type: ignore[attr-defined]
            content = json.loads(exc.content)  # type: ignore[attr-defined]
            reason = (
                content.get("error", {})
                .get("errors", [{}])[0]
                .get("reason", "unknown")
            )
            return int(status), reason
        except Exception:
            return -1, "unknown"

    # ── Public API methods ────────────────────────────────────────────────────

    def channels_list(self, channel_ids: list[str], part: str = "snippet,statistics,contentDetails") -> list[dict]:
        """
        Fetch channel details for up to 50 IDs per call (batched automatically).
        Cost: 1 unit per call.
        """
        results: list[dict] = []
        for batch in self._guard.split_ids_into_batches(channel_ids, 50):
            params = {"id": ",".join(batch), "part": part}
            resp = self._call(
                "channels.list", 1, params,
                lambda p=params: self._youtube.channels().list(**p).execute(),
            )
            results.extend(resp.get("items", []))
        return results

    def videos_list(self, video_ids: list[str], part: str = "snippet,statistics,contentDetails") -> list[dict]:
        """
        Fetch video details for up to 50 IDs per call (batched automatically).
        Cost: 1 unit per call.
        """
        results: list[dict] = []
        for batch in self._guard.split_ids_into_batches(video_ids, 50):
            params = {"id": ",".join(batch), "part": part}
            resp = self._call(
                "videos.list", 1, params,
                lambda p=params: self._youtube.videos().list(**p).execute(),
            )
            results.extend(resp.get("items", []))
        return results

    def playlist_items(self, playlist_id: str, max_results: int = 50) -> list[dict]:
        """
        Fetch items from an uploads playlist. Cost: 1 unit per page.
        Use to get a channel's recent uploads without using search.list.
        """
        results: list[dict] = []
        page_token: str | None = None
        cfg = get_quota_config()
        max_pages = cfg.get("comments_max_pages_per_video", 2)  # reuse reasonable cap

        for _ in range(max_pages):
            params: dict = {
                "playlistId": playlist_id,
                "part": "contentDetails",
                "maxResults": min(max_results, 50),
            }
            if page_token:
                params["pageToken"] = page_token
            resp = self._call(
                "playlistItems.list", 1, params,
                lambda p=params: self._youtube.playlistItems().list(**p).execute(),
            )
            results.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return results

    def comment_threads(self, video_id: str) -> list[dict]:
        """
        Fetch top-level comment threads for a video.
        Cost: 1 unit per page; max_pages from config.
        Returns [] if comments are disabled.
        """
        cfg = get_quota_config()
        max_pages = cfg.get("comments_max_pages_per_video", 2)
        results: list[dict] = []
        page_token: str | None = None

        for _ in range(max_pages):
            params: dict = {
                "videoId": video_id,
                "part": "snippet",
                "maxResults": 100,
                "textFormat": "plainText",
                "order": "relevance",
            }
            if page_token:
                params["pageToken"] = page_token
            resp = self._call(
                "commentThreads.list", 1, params,
                lambda p=params: self._youtube.commentThreads().list(**p).execute(),
            )
            if resp.get("_comments_disabled"):
                return []
            results.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return results

    def search_videos(self, query: str, max_results: int = 10) -> list[str]:
        """
        Search for video IDs. Uses the search.list sub-cap.
        Cost: 100 units per call. Use sparingly.
        """
        params = {
            "q": query, "part": "id", "type": "video",
            "maxResults": min(max_results, 50),
        }
        resp = self._call(
            "search.list", 100, params,
            lambda p=params: self._youtube.search().list(**p).execute(),
        )
        return [
            item["id"]["videoId"]
            for item in resp.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
