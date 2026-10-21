"""
src/app/data_loader.py
Phase 8 — Fast cached data loaders for Streamlit app.
Crucial rule: MUST NOT start or import Spark per page load (T-A1).
Reads precomputed gold tables, metrics registry, logs, and config.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.common.paths import project_root


def get_project_root() -> Path:
    return project_root()


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
            # Fill default score columns if missing
            if "promotion_potential_score" not in df.columns:
                df["promotion_potential_score"] = 50.0
            if "raw_score" not in df.columns:
                df["raw_score"] = 50.0
        else:
            df = pd.DataFrame()

    # Clean display columns
    if not df.empty:
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


def load_model_registry(registry_path: Path | None = None) -> pd.DataFrame:
    """Load metrics/model_registry.csv without hardcoding any numbers (T-A4)."""
    if registry_path is None:
        registry_path = get_project_root() / "metrics" / "model_registry.csv"

    if not registry_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(registry_path)
    return df


def load_backtest_results() -> pd.DataFrame:
    """Load metrics/backtest_results.csv."""
    path = get_project_root() / "metrics" / "backtest_results.csv"
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


def load_rate_card() -> dict[str, float]:
    """Load benchmark CPM rate card from config/rate_card.yaml."""
    p = get_project_root() / "config" / "rate_card.yaml"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return {
                tier.capitalize(): float(spec.get("cpm_usd", 20.0))
                for tier, spec in data.get("rate_card", {}).items()
            }
    return {"Nano": 15.0, "Micro": 20.0, "Macro": 25.0, "Mega": 35.0}


def load_scoring_config() -> dict[str, Any]:
    """Load scoring configuration from config/scoring.yaml."""
    p = get_project_root() / "config" / "scoring.yaml"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}
