"""
src/app/data_loader.py
Fast cached data loaders for Streamlit app.
Crucial rule: MUST NOT start or import Spark per page load (T-A1).
Reads precomputed gold tables, metrics registry, logs, and config.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import yaml

from src.common.paths import project_root


def get_project_root() -> Path:
    return project_root()


@st.cache_data(show_spinner=False)
def load_scored_creators() -> pd.DataFrame:
    """Load precomputed gold scored creators table."""
    root = get_project_root()
    pq_path = root / "data" / "gold" / "scored_creators.parquet"
    csv_path = root / "data" / "gold" / "scored_creators.csv"

    if pq_path.exists():
        df = pd.read_parquet(pq_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        # Fallback to channel influencer profiles if scored creators not found
        fallback_path = root / "data" / "gold" / "channel_influencer_profiles"
        if fallback_path.exists():
            df = pd.read_parquet(fallback_path)
            if "promotion_potential_score" not in df.columns:
                df["promotion_potential_score"] = 50.0
            if "raw_score" not in df.columns:
                df["raw_score"] = 50.0
        else:
            return pd.DataFrame()

    if not df.empty:
        if "channel_name" not in df.columns:
            ch_pq = root / "data" / "silver" / "youniverse_channels"
            if ch_pq.exists():
                try:
                    ch_df = pd.read_parquet(ch_pq, columns=["channel_id", "channel_name", "subscribers"])
                    df = df.merge(ch_df, on="channel_id", how="left")
                except Exception:
                    pass
        if "channel_name" not in df.columns:
            df["channel_name"] = df["channel_id"]
        else:
            df["channel_name"] = df["channel_name"].fillna(df["channel_id"])

        if "size_tier" in df.columns:
            df["size_tier"] = df["size_tier"].astype(str).str.capitalize()
        if "partial_evidence" in df.columns:
            df["partial_evidence"] = df["partial_evidence"].fillna(False).astype(bool)
        if "promo_lift" in df.columns:
            df["promo_lift_display"] = df["promo_lift"].apply(
                lambda x: f"{x:.2f}x" if pd.notnull(x) and x > 0 else "N/A"
            )
        if "sponsored_rate" in df.columns:
            df["sponsored_pct"] = (df["sponsored_rate"] * 100).round(1)

    return df


@st.cache_data(show_spinner=False)
def load_model_registry(registry_path: Path | None = None) -> pd.DataFrame:
    """Load metrics/model_registry.csv without hardcoding any numbers (T-A4)."""
    if registry_path is None:
        registry_path = get_project_root() / "metrics" / "model_registry.csv"

    if not registry_path.exists():
        return pd.DataFrame()

    return pd.read_csv(registry_path)


@st.cache_data(show_spinner=False)
def load_backtest_results() -> pd.DataFrame:
    """Load metrics/backtest_results.csv."""
    path = get_project_root() / "metrics" / "backtest_results.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def load_influencer_ablation() -> pd.DataFrame:
    """Load metrics/influencer_ablation_results.csv."""
    path = get_project_root() / "metrics" / "influencer_ablation_results.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def load_confusion_matrix(run_id: str) -> pd.DataFrame | None:
    """Load confusion matrix CSV for a specific run ID."""
    cm_path = get_project_root() / "metrics" / "runs" / run_id / "confusion_matrix.csv"
    if cm_path.exists():
        return pd.read_csv(cm_path)
    return None


def load_run_metrics_json(run_id: str) -> dict[str, Any]:
    """Load metrics.json for a specific run ID."""
    p = get_project_root() / "metrics" / "runs" / run_id / "metrics.json"
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def load_quota_ledger() -> dict[str, Any]:
    """Load current quota ledger from state/quota_ledger.json."""
    p = get_project_root() / "state" / "quota_ledger.json"
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def load_api_call_logs(limit: int = 50) -> list[dict[str, Any]]:
    """Load recent API calls from logs/api_calls.jsonl."""
    p = get_project_root() / "logs" / "api_calls.jsonl"
    if not p.exists():
        return []
    logs = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        logs.append(json.loads(line))
                    except Exception:
                        continue
    except Exception:
        return []
    return logs[-limit:]


def load_rate_card() -> dict[str, dict[str, float]]:
    """
    Load benchmark CPM and fixed overhead rate card from config/rate_card.yaml.
    Returns:
      {
         'Nano': {'cpm': 15.0, 'overhead': 50.0},
         'Micro': {'cpm': 20.0, 'overhead': 100.0},
         'Mid': {'cpm': 22.5, 'overhead': 175.0},
         'Macro': {'cpm': 25.0, 'overhead': 250.0},
         'Mega': {'cpm': 35.0, 'overhead': 500.0},
      }
    """
    p = get_project_root() / "config" / "rate_card.yaml"
    rate_card: dict[str, dict[str, float]] = {
        "Nano": {"cpm": 15.0, "overhead": 50.0},
        "Micro": {"cpm": 20.0, "overhead": 100.0},
        "Mid": {"cpm": 22.5, "overhead": 175.0},
        "Macro": {"cpm": 25.0, "overhead": 250.0},
        "Mega": {"cpm": 35.0, "overhead": 500.0},
    }
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                tiers_data = data.get("tiers", {})
                for tier, spec in tiers_data.items():
                    name = tier.capitalize()
                    cpm = float(spec.get("cpm", spec.get("cpm_usd", 20.0)))
                    overhead = float(spec.get("fixed_overhead", spec.get("overhead", 100.0)))
                    rate_card[name] = {"cpm": cpm, "overhead": overhead}
        except Exception:
            pass

    return rate_card


def load_scoring_config() -> dict[str, Any]:
    """Load scoring configuration from config/scoring.yaml."""
    p = get_project_root() / "config" / "scoring.yaml"
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception:
            return {}
    return {}


def load_data_freshness() -> dict[str, Any]:
    """
    Inspect files on disk to report freshness timestamps and row counts
    WITHOUT starting Spark or loading unnecessary parquet partitions.
    """
    root = get_project_root()
    layers = {
        "gold_scored": {
            "path": root / "data" / "gold" / "scored_creators.parquet",
            "name": "Gold Scored Creators",
            "expected_layer": "Gold",
        },
        "silver_channels": {
            "path": root / "data" / "silver" / "youniverse_channels",
            "name": "Silver Channels",
            "expected_layer": "Silver",
        },
        "silver_metadata": {
            "path": root / "data" / "silver" / "youniverse_metadata",
            "name": "Silver Videos Metadata",
            "expected_layer": "Silver",
        },
    }

    freshness_info = []
    for key, spec in layers.items():
        path = spec["path"]
        exists = path.exists()
        mtime = None
        mtime_str = "n/a"
        size_mb = 0.0

        if exists:
            try:
                if path.is_file():
                    stat = path.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                    size_mb = round(stat.st_size / (1024 * 1024), 2)
                elif path.is_dir():
                    # Pick most recent parquet file in dir
                    files = list(path.rglob("*.parquet"))
                    if files:
                        latest = max(files, key=lambda f: f.stat().st_mtime)
                        stat = latest.stat()
                        mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                        size_mb = round(sum(f.stat().st_size for f in files) / (1024 * 1024), 2)
                    else:
                        stat = path.stat()
                        mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                if mtime:
                    mtime_str = mtime.strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                pass

        freshness_info.append({
            "key": key,
            "name": spec["name"],
            "layer": spec["expected_layer"],
            "exists": exists,
            "modified": mtime_str,
            "size_mb": size_mb,
            "path": str(path.relative_to(root)),
        })

    # Detect active storage mode from config without starting Spark
    cfg_path = root / "config" / "settings.yaml"
    storage_mode = "Local (file:///)"
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                sett = yaml.safe_load(f)
                scheme = sett.get("spark", {}).get("storage_scheme", "file:///")
                if "hdfs" in scheme.lower():
                    storage_mode = "HDFS Cluster (hdfs://)"
        except Exception:
            pass

    return {
        "tables": freshness_info,
        "storage_mode": storage_mode,
    }
