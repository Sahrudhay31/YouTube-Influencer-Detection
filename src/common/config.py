"""
src/common/config.py
Load and validate YAML config files. Single source of truth for all settings.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    """Load key-value pairs from .env into os.environ if not already present."""
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val


load_env()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=None)
def get_settings() -> dict[str, Any]:
    """Load config/settings.yaml (cached)."""
    return _load_yaml(_PROJECT_ROOT / "config" / "settings.yaml")


@lru_cache(maxsize=None)
def get_quota_config() -> dict[str, Any]:
    """Load config/quota.yaml (cached)."""
    return _load_yaml(_PROJECT_ROOT / "config" / "quota.yaml")


@lru_cache(maxsize=None)
def get_quota_costs() -> dict[str, Any]:
    """Load config/quota_costs.yaml (cached)."""
    return _load_yaml(_PROJECT_ROOT / "config" / "quota_costs.yaml")


@lru_cache(maxsize=None)
def get_scoring_config() -> dict[str, Any]:
    """Load config/scoring.yaml and validate weights sum to 100."""
    cfg = _load_yaml(_PROJECT_ROOT / "config" / "scoring.yaml")
    weights = [v["weight"] for v in cfg.get("components", {}).values()]
    total = sum(weights)
    if abs(total - 100) > 0.01:
        raise ValueError(
            f"scoring.yaml component weights must sum to 100, got {total}"
        )
    return cfg


@lru_cache(maxsize=None)
def get_domain_taxonomy() -> dict[str, Any]:
    """Load config/domains/taxonomy.yaml (cached)."""
    return _load_yaml(_PROJECT_ROOT / "config" / "domains" / "taxonomy.yaml")


def get_domain_config(domain_name: str) -> dict[str, Any]:
    """Load the config for a specific domain (not cached — could change)."""
    path = _PROJECT_ROOT / "config" / "domains" / f"{domain_name}.yaml"
    return _load_yaml(path)


def get_hdfs_uri() -> str:
    """Return HDFS URI, preferring the HDFS_URI environment variable."""
    env_val = os.environ.get("HDFS_URI")
    if env_val:
        return env_val.rstrip("/")
    return get_settings()["hdfs"]["uri"].rstrip("/")


def project_root() -> Path:
    return _PROJECT_ROOT
