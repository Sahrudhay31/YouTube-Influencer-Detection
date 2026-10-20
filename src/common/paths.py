"""
src/common/paths.py
Centralised path helpers — no hardcoded paths anywhere else.
"""
from __future__ import annotations

from pathlib import Path

from src.common.config import get_settings, get_hdfs_uri, project_root


def hdfs(zone: str, *parts: str) -> str:
    """
    Return a full HDFS path for a named zone.

    Parameters
    ----------
    zone : str
        One of: raw_youniverse, raw_api, silver, gold, models.
    *parts : str
        Additional path components appended after the zone root.

    Example
    -------
    >>> hdfs("silver", "channels")
    'hdfs://namenode:8020/bda/silver/channels'
    """
    cfg = get_settings()["hdfs"]
    known_zones = {"raw_youniverse", "raw_api", "silver", "gold", "models"}
    if zone not in known_zones:
        raise ValueError(f"Unknown HDFS zone '{zone}'. Choose from {known_zones}.")
    base = cfg[zone].rstrip("/")
    uri = get_hdfs_uri()
    full = f"{uri}{base}"
    if parts:
        full = "/".join([full] + [p.strip("/") for p in parts])
    return full


def local(key: str, *parts: str) -> Path:
    """
    Return a local Path for a configured directory key.

    Parameters
    ----------
    key : str
        One of: labels, metrics, logs, state, docs.
    *parts : str
        Sub-path components.
    """
    cfg = get_settings()["paths"]
    if key not in cfg:
        raise ValueError(f"Unknown local path key '{key}'.")
    base = project_root() / cfg[key]
    if parts:
        return base.joinpath(*parts)
    return base
