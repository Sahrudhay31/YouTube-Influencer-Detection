"""
src/ingestion/plan.py
Dry-run quota estimator: prints the planned API calls and estimated units
without making any network calls.

Usage:
    python -m src.ingestion.plan --channels 10 --videos-per-channel 20 --comment-videos 5
"""
from __future__ import annotations

import argparse
import sys

from src.common.config import get_quota_config, get_quota_costs


def estimate(
    n_channels: int,
    videos_per_channel: int,
    comment_videos: int,
    n_search: int = 0,
) -> dict[str, int]:
    """
    Estimate quota units for a pipeline run.

    Parameters
    ----------
    n_channels : int
        Number of channels to enrich via channels.list.
    videos_per_channel : int
        Recent uploads to fetch per channel via playlistItems.list.
    comment_videos : int
        Number of videos to fetch comments for.
    n_search : int
        Number of search.list calls (discouraged; uses sub-cap).
    """
    costs = get_quota_costs().get("methods", {})
    cfg = get_quota_config()

    channels_calls = -(-n_channels // 50)  # ceiling division
    channels_units = channels_calls * costs.get("channels.list", {}).get("cost_per_call", 1)

    # uploads playlist: 1 call per channel to get playlist ID (already included in
    # channels.list via contentDetails), then playlistItems.list pages
    upload_pages_per_channel = -(-videos_per_channel // 50)
    playlist_units = n_channels * upload_pages_per_channel * costs.get("playlistItems.list", {}).get("cost_per_call", 1)

    video_calls = -(-n_channels * videos_per_channel // 50)
    video_units = video_calls * costs.get("videos.list", {}).get("cost_per_call", 1)

    comment_pages = cfg.get("comments_max_pages_per_video", 2)
    comment_units = comment_videos * comment_pages * costs.get("commentThreads.list", {}).get("cost_per_call", 1)

    search_units = n_search * costs.get("search.list", {}).get("cost_per_call", 100)

    breakdown = {
        "channels.list": channels_units,
        "playlistItems.list": playlist_units,
        "videos.list": video_units,
        "commentThreads.list": comment_units,
        "search.list": search_units,
        "TOTAL": channels_units + playlist_units + video_units + comment_units + search_units,
    }
    return breakdown


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate YouTube API quota units for a pipeline run (dry-run only)."
    )
    parser.add_argument("--channels", type=int, required=True, help="Number of channels to enrich.")
    parser.add_argument("--videos-per-channel", type=int, default=20, help="Recent uploads per channel.")
    parser.add_argument("--comment-videos", type=int, default=0, help="Videos to sample comments for.")
    parser.add_argument("--search", type=int, default=0, help="search.list calls (use sparingly).")
    args = parser.parse_args()

    breakdown = estimate(
        n_channels=args.channels,
        videos_per_channel=args.videos_per_channel,
        comment_videos=args.comment_videos,
        n_search=args.search,
    )

    cfg = get_quota_config()
    daily_cap = cfg["daily_unit_cap"]
    per_run_cap = cfg["per_run_max_units"]

    print("\n=== Quota Estimate (DRY RUN) ===")
    print("=" * 45)
    for method, units in breakdown.items():
        if method == "TOTAL":
            print("-" * 45)
        print(f"  {method:<30} {units:>6} units")
    print("=" * 45)
    print(f"  Daily cap:         {daily_cap:>6} units")
    print(f"  Per-run cap:       {per_run_cap:>6} units")
    total = breakdown["TOTAL"]
    if total > per_run_cap:
        print(f"\n[WARNING] EXCEEDS per-run cap ({total} > {per_run_cap}). Reduce scope.")
        sys.exit(1)
    elif total > daily_cap:
        print(f"\n[WARNING] EXCEEDS daily cap ({total} > {daily_cap}). Reduce scope.")
        sys.exit(1)
    else:
        pct = 100 * total / daily_cap
        print(f"\n[OK] Within caps. Uses {pct:.1f}% of daily budget.")


if __name__ == "__main__":
    main()
