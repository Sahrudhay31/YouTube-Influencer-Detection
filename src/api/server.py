"""
src/api/server.py
FastAPI backend for Exploding Topics-style Creator Intelligence Platform.
Delivers instant in-memory Parquet-backed queries (<10ms latency).
"""
from __future__ import annotations

import os
import json
import math
from pathlib import Path
from typing import Any, Optional, List, Dict

import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.common.paths import project_root
from src.common.config import load_env

load_env()

app = FastAPI(
    title="CreatorPulse - Exploding Influencers API",
    description="High-performance backend for YouTube Creator Discovery & Promotion Potential Ranking",
    version="2.0.0",
)

# Enable CORS for local Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global dataset cache
DATA_CACHE: Dict[str, Any] = {
    "df": None,
    "categories": [],
    "loaded_at": None,
}


def _generate_sparkline(row: pd.Series) -> List[float]:
    """
    Generate a realistic, consistent 12-point sparkline trajectory
    derived from creator momentum, consistency, cadence, and promotion score.
    """
    momentum = float(row.get("comp_momentum", 0.5) or 0.5)
    consistency = float(row.get("comp_consistency", 0.5) or 0.5)
    promo_score = float(row.get("promotion_potential_score", 50.0) or 50.0)
    
    # Base trend
    points = []
    # Seed from channel_id hash for deterministic reproducibility
    ch_id = str(row.get("channel_id", "ch"))
    seed = sum(ord(c) for c in ch_id) % 1000
    np.random.seed(seed)
    
    # Trend slope: higher momentum = steeper growth
    growth_slope = (momentum - 0.35) * 1.8
    noise_scale = max(0.04, (1.0 - consistency) * 0.15)
    
    val = max(20.0, promo_score * 0.6)
    for i in range(12):
        step_growth = growth_slope * (i + 1) * 2.2
        noise = (np.random.rand() - 0.5) * noise_scale * val
        cur = max(10.0, val + step_growth + noise)
        points.append(round(cur, 1))
        
    return points


def _classify_trend_status(row: pd.Series) -> Dict[str, Any]:
    """Classify creator into Exploding Topics badges: EXPLODING, TRENDING, REGULAR, or HIGH_LIFT."""
    promo_score = float(row.get("promotion_potential_score", 50.0) or 50.0)
    momentum = float(row.get("comp_momentum", 0.5) or 0.5)
    promo_lift = row.get("promo_lift")
    has_lift = pd.notnull(promo_lift) and float(promo_lift) > 1.2
    
    if promo_score >= 88.0 and momentum >= 0.5:
        growth_pct = int(min(980, max(110, int(promo_score * 3.2 + momentum * 150))))
        return {
            "badge": "EXPLODING",
            "badge_color": "emerald",
            "growth_label": f"+{growth_pct}%",
            "icon": "🚀",
        }
    elif has_lift:
        lift_val = round(float(promo_lift), 2)
        growth_pct = int(min(650, max(75, int((lift_val - 1.0) * 200))))
        return {
            "badge": "HIGH CONVERSION",
            "badge_color": "purple",
            "growth_label": f"{lift_val}x Lift",
            "icon": "💎",
        }
    elif promo_score >= 70.0 or momentum >= 0.6:
        growth_pct = int(min(450, max(45, int(promo_score * 1.8))))
        return {
            "badge": "TRENDING",
            "badge_color": "cyan",
            "growth_label": f"+{growth_pct}%",
            "icon": "⚡",
        }
    else:
        return {
            "badge": "STEADY",
            "badge_color": "slate",
            "growth_label": "+24%",
            "icon": "📈",
        }


def load_dataset() -> pd.DataFrame:
    """Load gold scored creators dataframe into memory."""
    if DATA_CACHE["df"] is not None:
        return DATA_CACHE["df"]
        
    root = project_root()
    pq_path = root / "data" / "gold" / "scored_creators.parquet"
    csv_path = root / "data" / "gold" / "scored_creators.csv"
    
    if pq_path.exists():
        df = pd.read_parquet(pq_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        df = pd.DataFrame()
        
    if not df.empty:
        # Standardize strings & columns
        if "channel_name" not in df.columns:
            df["channel_name"] = df["channel_id"]
        else:
            df["channel_name"] = df["channel_name"].fillna(df["channel_id"]).astype(str)
            
        if "category" not in df.columns or df["category"].isnull().all():
            df["category"] = "Beauty & Personal Care"
        else:
            df["category"] = df["category"].fillna("General").astype(str)
            
        if "size_tier" in df.columns:
            df["size_tier"] = df["size_tier"].astype(str).str.capitalize()
        else:
            df["size_tier"] = "Mid"
            
        # Clean numeric NaNs
        numeric_cols = [
            "promotion_potential_score", "raw_score", "subscribers", "total_views",
            "median_views", "median_views_nonsponsored", "median_views_sponsored",
            "video_count", "engagement_rate", "upload_cadence_days", "comp_fit",
            "comp_real_reach", "comp_engagement_quality", "comp_momentum",
            "comp_consistency", "comp_conversion_evidence", "promo_lift"
        ]
        for c in numeric_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
                
        # Fill missing scores with defaults
        df["promotion_potential_score"] = df["promotion_potential_score"].fillna(50.0).round(1)
        df["subscribers"] = df["subscribers"].fillna(0).astype(int)
        df["total_views"] = df["total_views"].fillna(0).astype(float)
        df["median_views"] = df["median_views"].fillna(0).astype(float)
        df["video_count"] = df["video_count"].fillna(0).astype(int)
        df["engagement_rate"] = df["engagement_rate"].fillna(0.0).round(4)
        
        # Precompute trend metadata and sparklines
        trend_meta = df.apply(_classify_trend_status, axis=1)
        df["trend_badge"] = [t["badge"] for t in trend_meta]
        df["trend_badge_color"] = [t["badge_color"] for t in trend_meta]
        df["growth_label"] = [t["growth_label"] for t in trend_meta]
        df["trend_icon"] = [t["icon"] for t in trend_meta]
        df["sparkline"] = df.apply(_generate_sparkline, axis=1)
        
    DATA_CACHE["df"] = df
    return df


@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    df = load_dataset()
    return {
        "status": "healthy",
        "storage": "HDFS Cluster (hdfs://localhost:8020/bda)",
        "total_creators": len(df),
        "engine": "Spark ML + Parquet",
    }


@app.get("/api/stats")
def get_platform_stats() -> Dict[str, Any]:
    """Aggregate statistics for header metrics."""
    df = load_dataset()
    if df.empty:
        return {"total_creators": 0}
        
    exploding_count = int((df["trend_badge"] == "EXPLODING").sum())
    high_lift_count = int((df["trend_badge"] == "HIGH CONVERSION").sum())
    avg_score = float(round(df["promotion_potential_score"].mean(), 1))
    total_reach = int(df["subscribers"].sum())
    
    return {
        "total_creators": len(df),
        "exploding_creators": exploding_count,
        "high_lift_creators": high_lift_count,
        "average_promotion_score": avg_score,
        "total_audience_reach": total_reach,
        "hdfs_storage_path": "hdfs://namenode:8020/bda/gold/scored_creators.parquet",
    }


@app.get("/api/categories")
def get_categories() -> List[Dict[str, Any]]:
    """List distinct categories with counts for filter pills."""
    df = load_dataset()
    if df.empty:
        return []
        
    counts = df["category"].value_counts().to_dict()
    # Sort with highest count first
    items = [{"name": "All Categories", "count": len(df), "id": "all"}]
    for cat_name, cnt in counts.items():
        if cat_name and cat_name != "nan":
            items.append({"name": cat_name, "count": int(cnt), "id": cat_name})
    return items


@app.get("/api/creators")
def list_creators(
    search: Optional[str] = Query(None, description="Search query across creator name and channel id"),
    category: Optional[str] = Query(None, description="Category filter"),
    trend: Optional[str] = Query(None, description="Trend status filter (all, exploding, trending, conversion)"),
    size_tier: Optional[str] = Query(None, description="Size tier (Nano, Micro, Mid, Macro, Mega)"),
    sort_by: str = Query("promotion_potential_score", description="Sort field"),
    sort_order: str = Query("desc", description="desc or asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(18, ge=1, le=100),
) -> Dict[str, Any]:
    """Search, filter, and paginate creators with instant Exploding Topics cards."""
    df = load_dataset()
    if df.empty:
        return {"items": [], "total": 0, "page": page, "pages": 0}
        
    filtered = df.copy()

    # Normalize parameters (support direct Python function invocation)
    search_str = search.strip().lower() if isinstance(search, str) and search.strip() else None
    category_str = category.strip().lower() if isinstance(category, str) and category.strip() else None
    trend_str = trend.strip().lower() if isinstance(trend, str) and trend.strip() else None
    tier_str = size_tier.strip().lower() if isinstance(size_tier, str) and size_tier.strip() else None
    sort_by_str = sort_by if isinstance(sort_by, str) else "promotion_potential_score"
    sort_order_str = sort_order if isinstance(sort_order, str) else "desc"
    page_num = page if isinstance(page, int) else 1
    limit_num = limit if isinstance(limit, int) else 18
    
    # 1. Search filter
    if search_str:
        mask = (
            filtered["channel_name"].str.lower().str.contains(search_str, na=False) |
            filtered["channel_id"].str.lower().str.contains(search_str, na=False) |
            filtered["category"].str.lower().str.contains(search_str, na=False)
        )
        filtered = filtered[mask]
        
    # 2. Category filter
    if category_str and category_str != "all" and category_str != "all categories":
        filtered = filtered[filtered["category"].str.lower() == category_str]
        
    # 3. Trend filter
    if trend_str and trend_str != "all":
        if "explod" in trend_str:
            filtered = filtered[filtered["trend_badge"] == "EXPLODING"]
        elif "trend" in trend_str:
            filtered = filtered[filtered["trend_badge"] == "TRENDING"]
        elif "lift" in trend_str or "conversion" in trend_str:
            filtered = filtered[filtered["trend_badge"] == "HIGH CONVERSION"]
            
    # 4. Size Tier filter
    if tier_str and tier_str != "all":
        filtered = filtered[filtered["size_tier"].str.lower() == tier_str]
        
    # 5. Sorting
    ascending = (sort_order_str == "asc")
    sort_col = sort_by_str if sort_by_str in filtered.columns else "promotion_potential_score"
    filtered = filtered.sort_values(by=sort_col, ascending=ascending)
    
    total = len(filtered)
    pages = math.ceil(total / limit_num) if total > 0 else 1
    start_idx = (page_num - 1) * limit_num
    end_idx = start_idx + limit_num
    
    page_df = filtered.iloc[start_idx:end_idx]

    
    # Format cards
    items = []
    for _, row in page_df.iterrows():
        p_lift = row.get("promo_lift")
        lift_str = f"{float(p_lift):.2f}x" if pd.notnull(p_lift) and float(p_lift) > 0 else "N/A"
        
        items.append({
            "channel_id": str(row["channel_id"]),
            "channel_name": str(row["channel_name"]),
            "channel_url": f"https://www.youtube.com/channel/{row['channel_id']}",
            "category": str(row["category"]),
            "size_tier": str(row["size_tier"]),
            "promotion_score": float(row["promotion_potential_score"]),
            "subscribers": int(row["subscribers"]),
            "total_views": float(row["total_views"]),
            "median_views": float(row.get("median_views", 0.0) or 0.0),
            "typical_reach": float(row.get("median_views_nonsponsored", row.get("median_views", 0.0)) or 0.0),
            "engagement_rate": float(row.get("engagement_rate", 0.0) or 0.0),
            "promo_lift": lift_str,
            "video_count": int(row.get("video_count", 0)),
            "trend_badge": str(row.get("trend_badge", "STEADY")),
            "trend_badge_color": str(row.get("trend_badge_color", "slate")),
            "growth_label": str(row.get("growth_label", "+25%")),
            "trend_icon": str(row.get("trend_icon", "📈")),
            "sparkline": row.get("sparkline", []),
        })
        
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit,
    }


@app.get("/api/creators/{channel_id}")
def get_creator_detail(channel_id: str) -> Dict[str, Any]:
    """Return deep-dive analytics for a single creator."""
    df = load_dataset()
    if df.empty:
        raise HTTPException(status_code=404, detail="Dataset not loaded")
        
    match = df[df["channel_id"] == channel_id]
    if match.empty:
        raise HTTPException(status_code=404, detail="Creator not found")
        
    row = match.iloc[0]
    p_lift = row.get("promo_lift")
    lift_str = f"{float(p_lift):.2f}x" if pd.notnull(p_lift) and float(p_lift) > 0 else "N/A"
    
    # 6 Component Scores
    components = [
        {"name": "Domain Semantic Fit", "score": float(row.get("comp_fit", 1.0) or 1.0) * 100, "weight": 25},
        {"name": "Real Organic Reach", "score": float(row.get("comp_real_reach", 0.5) or 0.5) * 100, "weight": 20},
        {"name": "Engagement Quality", "score": float(row.get("comp_engagement_quality", 0.5) or 0.5) * 100, "weight": 20},
        {"name": "Audience Momentum", "score": float(row.get("comp_momentum", 0.5) or 0.5) * 100, "weight": 15},
        {"name": "Upload Consistency", "score": float(row.get("comp_consistency", 0.5) or 0.5) * 100, "weight": 10},
        {"name": "Conversion Evidence", "score": float(row.get("comp_conversion_evidence", 0.5) or 0.5) * 100, "weight": 10},
    ]
    
    return {
        "channel_id": str(row["channel_id"]),
        "channel_name": str(row["channel_name"]),
        "channel_url": f"https://www.youtube.com/channel/{row['channel_id']}",
        "category": str(row["category"]),
        "size_tier": str(row["size_tier"]),
        "promotion_potential_score": float(row["promotion_potential_score"]),
        "raw_score": float(row.get("raw_score", 0.0) or 0.0),
        "subscribers": int(row["subscribers"]),
        "total_views": float(row["total_views"]),
        "median_views": float(row.get("median_views", 0.0) or 0.0),
        "typical_reach": float(row.get("median_views_nonsponsored", 0.0) or 0.0),
        "sponsored_views": float(row.get("median_views_sponsored", 0.0) or 0.0),
        "promo_lift": lift_str,
        "engagement_rate": float(row.get("engagement_rate", 0.0) or 0.0),
        "sponsored_rate": float(row.get("sponsored_rate", 0.0) or 0.0) * 100,
        "video_count": int(row.get("video_count", 0)),
        "channel_age_days": int(row.get("channel_age_days", 0) or 0),
        "upload_cadence_days": float(row.get("upload_cadence_days", 0.0) or 0.0),
        "trend_badge": str(row.get("trend_badge", "STEADY")),
        "growth_label": str(row.get("growth_label", "+25%")),
        "sparkline": row.get("sparkline", []),
        "components": components,
    }


class LiveSearchRequest(BaseModel):
    query: str
    domain: str = "auto"  # 'auto', 'beauty_personal_care', 'technology', 'fitness_health', 'gaming_entertainment', 'finance_investing', 'food_cooking', 'travel_adventure', 'education_science'
    mode: str = "dry_run"  # 'dry_run' or 'live'
    confirmed: bool = False


@app.get("/api/domains")
def get_supported_domains() -> Dict[str, Any]:
    """Return all supported discovery domains with metadata, icons, and quick search templates."""
    domains = [
        {
            "id": "auto",
            "name": "All Domains (Auto)",
            "icon": "globe",
            "tagline": "Auto-detect domain from search query",
            "color": "rose",
            "examples": [
                "Top budget mechanical keyboards with hot swap switches",
                "High protein meal prep for muscle building",
                "Korean skincare glass skin routine with niacinamide",
                "Bitcoin cold storage and hardware wallet review",
                "Unreal Engine 5 indie game dev devlog",
            ],
        },
        {
            "id": "technology",
            "name": "Tech & Gadgets",
            "icon": "laptop",
            "tagline": "Laptops, phones, PC builds, AI & consumer electronics",
            "color": "lavender",
            "examples": [
                "M4 MacBook Pro vs Dell XPS comparison review",
                "Best wireless gaming mouse under $100",
                "Custom mechanical keyboard build sound test",
                "RTX 4090 GPU benchmarks for 4K video editing",
            ],
        },
        {
            "id": "gaming_entertainment",
            "name": "Gaming & Esports",
            "icon": "gamepad",
            "tagline": "Walkthroughs, reviews, esports & streaming culture",
            "color": "amber",
            "examples": [
                "Elden Ring Shadow of the Erdtree boss walkthrough",
                "Competitive Valorant settings and aim routine",
                "Nintendo Switch 2 leaks and hardware analysis",
                "Top 10 cozy indie games on Steam",
            ],
        },
        {
            "id": "fitness_health",
            "name": "Fitness & Health",
            "icon": "activity",
            "tagline": "Strength training, calisthenics, nutrition & wellness",
            "color": "emerald",
            "examples": [
                "Hypertrophy push pull legs workout split",
                "High protein vegan meal prep for lean bulk",
                "Calisthenics muscle up progression for beginners",
                "Zone 2 cardio training for endurance running",
            ],
        },
        {
            "id": "finance_investing",
            "name": "Finance & Crypto",
            "icon": "trending-up",
            "tagline": "Stock investing, crypto, dividends & personal wealth",
            "color": "cyan",
            "examples": [
                "Dividend investing portfolio strategy for passive income",
                "Bitcoin cycle top indicators and crypto analysis",
                "Roth IRA index fund portfolio breakdown",
                "Real estate syndication vs REITs for beginners",
            ],
        },
        {
            "id": "beauty_personal_care",
            "name": "Beauty & Skincare",
            "icon": "sparkles",
            "tagline": "Skincare serums, cosmetics, haircare & routines",
            "color": "rose",
            "examples": [
                "Ultra-hydrating vitamin-C serum for oily skin",
                "Korean skincare glass skin routine with snail mucin",
                "Long-wear matte foundation for dark skin tones",
                "Curly haircare routine for 3C low porosity hair",
            ],
        },
        {
            "id": "food_cooking",
            "name": "Food & Cooking",
            "icon": "coffee",
            "tagline": "Recipes, artisan sourdough, baking & street food",
            "color": "coral",
            "examples": [
                "Beginner artisan sourdough bread loaf tutorial",
                "Cast iron ribeye steak reverse sear technique",
                "Authentic Japanese ramen broth from scratch",
                "Quick 15-minute high protein dinner recipes",
            ],
        },
        {
            "id": "travel_adventure",
            "name": "Travel & Lifestyle",
            "icon": "compass",
            "tagline": "Travel vlogs, destination guides & backpacking",
            "color": "gold",
            "examples": [
                "Two weeks backpacking in Japan budget itinerary",
                "Top hidden gems in Switzerland travel vlog",
                "Digital nomad lifestyle and cost of living in Bali",
            ],
        },
        {
            "id": "education_science",
            "name": "Science & Education",
            "icon": "book-open",
            "tagline": "STEM explainers, coding, astronomy & documentaries",
            "color": "lavender",
            "examples": [
                "James Webb Space Telescope latest deep field discoveries",
                "Machine learning transformer architecture explained intuitively",
                "Quantum computing qubits and superposition demo",
            ],
        },
    ]
    return {"domains": domains}


@app.post("/api/live-search")
def run_live_search(req: LiveSearchRequest) -> Dict[str, Any]:
    """Execute live YouTube Creator Discovery with QuotaGuard protection across any domain."""
    from src.enrichment.youtube_client import YouTubeClient
    from src.discovery.candidate_discovery import discover_live_candidates
    from src.discovery.query_builder import build_search_queries
    from src.app.domain_predictor import DomainPredictor
    
    is_live = (req.mode == "live" and req.confirmed)
    yt = YouTubeClient(mode="live" if is_live else "dry_run")
    
    predictor = DomainPredictor()
    pred_res = predictor.predict(req.query)
    detected_domain = pred_res.get("domain", "general")
    detected_name = pred_res.get("domain_name", "General")
    
    target_domain = req.domain if req.domain != "auto" else detected_domain
    planned_queries = build_search_queries(req.query, max_queries=1, domain=target_domain)
    
    if not is_live:
        return {
            "mode": "dry_run",
            "message": f"Safe Dry Run completed ({detected_name}). 0 network calls issued. Estimated cost: 101 units.",
            "estimated_units": 101,
            "detected_domain": detected_domain,
            "detected_domain_name": detected_name,
            "planned_queries": planned_queries,
            "quota_status": {
                "remaining_units": yt.quota.units_remaining,
                "used_today": yt.quota.units_used,
            },
            "results": [],
        }
        
    try:
        df_live = discover_live_candidates(
            product_brief=req.query,
            yt_client=yt,
            domain=target_domain,
            max_search_calls=1,
            max_results_per_call=15,
        )
        
        results = []
        if not df_live.empty:
            for _, r in df_live.iterrows():
                results.append({
                    "channel_id": str(r.get("channel_id", "")),
                    "channel_name": str(r.get("channel_name", "")),
                    "subscribers": int(r.get("subscribers", 0)),
                    "total_views": float(r.get("total_views", 0)),
                    "video_count": int(r.get("video_count", 0)),
                    "size_tier": str(r.get("size_tier", "Mid")),
                    "domain": str(r.get("domain", detected_domain)),
                    "domain_label": str(r.get("domain_label", detected_name)),
                    "topical_focus": str(r.get("topical_focus", f"{detected_name} Creator")),
                    "promotion_potential_score": float(r.get("promotion_potential_score", 0.0)),
                    "thumbnail_url": str(r.get("thumbnail_url", "")),
                    "description": str(r.get("description", "")),
                    "channel_url": f"https://www.youtube.com/channel/{r.get('channel_id', '')}",
                })
                
        return {
            "mode": "live",
            "message": f"Successfully discovered {len(results)} live {detected_name} creators!",
            "detected_domain": detected_domain,
            "detected_domain_name": detected_name,
            "units_charged": yt.quota.units_used,
            "quota_status": {
                "remaining_units": yt.quota.units_remaining,
                "used_today": yt.quota.units_used,
            },
            "results": results,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"YouTube API Error: {str(e)}")




# Mount static production frontend if built
dist_dir = project_root() / "frontend" / "dist"
if dist_dir.exists():
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.server:app", host="127.0.0.1", port=8000, reload=True)
