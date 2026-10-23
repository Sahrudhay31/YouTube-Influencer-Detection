"""
src/discovery/run.py
CLI runner for Phase R6 Beauty Creator Discovery.
Usage:
    python -m src.discovery.run --brief "hydrating hyaluronic acid serum" --mode dry_run
    python -m src.discovery.run --brief "vitamin c serum oily skin" --mode live --max-units 150
"""
from __future__ import annotations

import argparse
import sys

from src.discovery.candidate_discovery import run_discovery_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase R6 Beauty Creator Discovery")
    parser.add_argument("--brief", type=str, required=True, help="Product description or brief")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["dry_run", "live"],
        default="dry_run",
        help="Execution mode (default: dry_run, 0 API units)",
    )
    parser.add_argument(
        "--max-units",
        type=int,
        default=300,
        help="Maximum YouTube API units allowed for this run",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=15,
        help="Maximum candidate creators to return",
    )
    args = parser.parse_args()

    print("=" * 70)
    print(f"BEAUTY CREATOR DISCOVERY — MODE: {args.mode.upper()}")
    print(f"Product Brief: '{args.brief}'")
    print(f"Max Units Cap: {args.max_units}")
    print("=" * 70)

    res = run_discovery_pipeline(
        product_brief=args.brief,
        mode=args.mode,
        max_units=args.max_units,
        max_candidates=args.max_candidates,
    )

    offline_df = res["offline_candidates"]
    live_df = res["live_candidates"]

    print("\n--- OFFLINE CANDIDATES (YouNiverse 10% Cohort) ---")
    if not offline_df.empty:
        display_cols = ["channel_name", "subscribers", "size_tier", "promotion_potential_score", "median_views"]
        available_cols = [c for c in display_cols if c in offline_df.columns]
        print(offline_df[available_cols].head(args.max_candidates).to_string(index=False))
    else:
        print("No offline candidates found.")

    if args.mode == "live":
        print(f"\n--- LIVE YOUTUBE API CANDIDATES (Units Used: {res['units_used']}) ---")
        if not live_df.empty:
            live_cols = ["channel_name", "subscribers", "size_tier", "topical_focus", "promotion_potential_score"]
            available_cols = [c for c in live_cols if c in live_df.columns]
            print(live_df[available_cols].to_string(index=False))
        else:
            print("No live candidates discovered or quota exhausted.")
    else:
        print("\n[DRY RUN] Live API search skipped. Estimated quota: 101 units. To run live, use --mode live.")

    print("=" * 70)


if __name__ == "__main__":
    main()
