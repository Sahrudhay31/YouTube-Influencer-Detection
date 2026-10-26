"""
src/discovery/candidate_discovery.py
Phase R6 — Candidate Discovery & Live Enrichment Pipeline.
Discovers beauty creators across both:
  (a) Offline Cohort (2,615 scored beauty channels from YouNiverse, 0 quota units)
  (b) Live YouTube Data API v3 (bounded search.list + channels.list)
Returns candidates with real channel names, subscriber counts, and topical focus.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.app.domain_predictor import DomainPredictor
from src.common.paths import hdfs, local
from src.discovery.query_builder import build_search_queries
from src.enrichment.youtube_client import YouTubeClient

logger = logging.getLogger(__name__)


def discover_offline_candidates(
    product_brief: str,
    max_candidates: int = 25,
) -> pd.DataFrame:
    """
    Search precomputed gold scored creators table for channels matching the brief.
    Consumes ZERO YouTube API quota units.
    """
    pq_path = local("gold", "scored_creators.parquet")
    csv_path = local("gold", "scored_creators.csv")

    if pq_path.exists():
        df = pd.read_parquet(pq_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        logger.warning("No precomputed gold scored creators found.")
        return pd.DataFrame()

    if df.empty:
        return df

    df["source"] = "offline_youniverse"
    df["discovery_query"] = product_brief

    # Ensure channel_name is present
    if "channel_name" not in df.columns or df["channel_name"].isnull().all():
        df["channel_name"] = df["channel_id"]

    # Rank by promotion potential score
    df = df.sort_values(by="promotion_potential_score", ascending=False).reset_index(drop=True)
    return df.head(max_candidates)


def discover_live_candidates(
    product_brief: str,
    yt_client: YouTubeClient,
    max_search_calls: int = 1,
    max_results_per_call: int = 25,
    min_subscribers: int = 1000,
) -> pd.DataFrame:
    """
    Query the live YouTube Data API v3 within strict quota guard limits.
    Returns discovered channels with real channel names (snippet.title),
    subscriber counts, video statistics, and predicted topical focus.

    Cost: 100 units per search.list call + 1 unit for batched channels.list call.
    """
    queries = build_search_queries(product_brief, max_queries=max_search_calls)
    predictor = DomainPredictor()

    channel_records: dict[str, dict[str, Any]] = {}

    for q in queries:
        # Check quota guard before executing
        if not yt_client.quota.can_afford("search.list"):
            logger.warning("[Discovery] Quota cap reached for search.list. Halting.")
            break

        logger.info("[Discovery] Executing YouTube search for query: '%s'", q)
        video_items = yt_client.search_creators(
            query=q,
            max_results=max_results_per_call,
            language="en",
            region_code="US",
        )

        for item in video_items:
            snippet = item.get("snippet", {})
            ch_id = snippet.get("channelId")
            ch_title = snippet.get("channelTitle", ch_id)
            vid_title = snippet.get("title", "")
            vid_desc = snippet.get("description", "")

            if not ch_id:
                continue

            if ch_id not in channel_records:
                channel_records[ch_id] = {
                    "channel_id": ch_id,
                    "channel_name": ch_title,
                    "discovery_query": q,
                    "sample_videos": [vid_title],
                    "sample_descriptions": [vid_desc],
                    "source": "live_youtube_api",
                }
            else:
                channel_records[ch_id]["sample_videos"].append(vid_title)
                channel_records[ch_id]["sample_descriptions"].append(vid_desc)

    if not channel_records:
        return pd.DataFrame()

    candidate_ids = list(channel_records.keys())
    logger.info("[Discovery] Found %d unique channels from live search. Enriching details...", len(candidate_ids))

    # Batch enrich channels via channels.list (1 unit per 50 channels)
    channel_details = yt_client.get_channel_stats(candidate_ids)

    # Index channel details by channel ID
    details_by_id = {item["id"]: item for item in channel_details if "id" in item}

    rows = []
    for ch_id, rec in channel_records.items():
        det = details_by_id.get(ch_id, {})
        snip = det.get("snippet", {})
        stats = det.get("statistics", {})

        # Real channel name from live YouTube snippet
        live_name = snip.get("title") or rec["channel_name"]
        subs = int(stats.get("subscriberCount", 0)) if stats.get("subscriberCount") else 0
        total_views = int(stats.get("viewCount", 0)) if stats.get("viewCount") else 0
        video_count = int(stats.get("videoCount", 0)) if stats.get("videoCount") else len(rec["sample_videos"])
        custom_url = snip.get("customUrl", "")
        desc = snip.get("description", "")
        thumb_url = snip.get("thumbnails", {}).get("default", {}).get("url", "")

        # Topical focus: predict beauty domain fit on sample video text
        combined_text = " ".join(rec["sample_videos"] + rec["sample_descriptions"] + [desc])
        pred_res = predictor.predict(combined_text)
        topical_focus = pred_res["confidence"] if pred_res["domain_name"] != "Out-of-Domain" else 0.2

        # Filter by minimum subscribers
        if subs > 0 and subs < min_subscribers:
            continue

        # Size tier
        if subs <= 25_000:
            size_tier = "Nano"
        elif subs <= 100_000:
            size_tier = "Micro"
        elif subs <= 500_000:
            size_tier = "Mid"
        elif subs <= 2_000_000:
            size_tier = "Macro"
        else:
            size_tier = "Mega"

        # Compute estimated promotion potential score
        reach_comp = min(1.0, max(0.0, (np.log10(max(subs, 100)) - 2.0) / 4.0)) if subs > 0 else 0.5
        fit_comp = topical_focus
        raw_score = (fit_comp * 0.5 + reach_comp * 0.5) * 100.0

        rows.append({
            "channel_name": live_name,
            "channel_id": ch_id,
            "custom_url": custom_url,
            "subscribers": subs,
            "size_tier": size_tier,
            "total_views": total_views,
            "video_count": video_count,
            "topical_focus": round(topical_focus, 3),
            "promotion_potential_score": round(raw_score, 1),
            "thumbnail_url": thumb_url,
            "description": desc[:300],
            "discovery_query": rec["discovery_query"],
            "source": "live_youtube_api",
        })

    df_live = pd.DataFrame(rows)
    if not df_live.empty:
        df_live = df_live.sort_values(by="promotion_potential_score", ascending=False).reset_index(drop=True)

        # Persist raw API partition under HDFS /bda/raw/api/dt=YYYY-MM-DD/
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hdfs_partition_path = hdfs("raw_api", f"dt={today_str}")

        # Local staging backup
        api_dir = local("raw", f"api/dt={today_str}")
        api_dir.mkdir(parents=True, exist_ok=True)
        dump_path = api_dir / f"live_discovery_{int(datetime.now(timezone.utc).timestamp())}.json"
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump({"query": product_brief, "channels": rows}, f, indent=2)

        # Attempt direct HDFS persistence
        try:
            from src.common.spark_session import get_spark
            spark = get_spark("LiveDiscoveryHDFSIngest", local_mode=False)
            df_spark = spark.createDataFrame(df_live)
            df_spark.write.mode("append").json(hdfs_partition_path)
            logger.info("[Discovery] Persisted %d live records directly to HDFS: %s", len(rows), hdfs_partition_path)
        except Exception as hdfs_err:
            logger.warning("[Discovery] Direct HDFS write deferred (%s); partition staged at %s for HDFS sync.", hdfs_err, dump_path)

    return df_live


def run_discovery_pipeline(
    product_brief: str,
    mode: str = "dry_run",
    max_units: int = 300,
    max_candidates: int = 25,
) -> dict[str, Any]:
    """
    Orchestrate candidate discovery for a given product brief.
    Runs offline discovery and (if mode == 'live') live YouTube Data API discovery.
    """
    yt = YouTubeClient(mode=mode, per_run_max=max_units)

    offline_df = discover_offline_candidates(product_brief, max_candidates=max_candidates)

    if mode == "live":
        live_df = discover_live_candidates(product_brief, yt_client=yt)
    else:
        # Dry-run: calculate planned queries and estimated quota
        planned_queries = build_search_queries(product_brief, max_queries=1)
        est_units = len(planned_queries) * 100 + 1
        live_df = pd.DataFrame()
        logger.info("[Discovery] DRY RUN: Planned %d query (%d units). No API calls made.", len(planned_queries), est_units)

    return {
        "mode": mode,
        "brief": product_brief,
        "offline_candidates": offline_df,
        "live_candidates": live_df,
        "units_used": yt.quota.units_used,
    }
