"""
src/common/logging_setup.py
Centralised logging configuration for the project.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.common.config import get_settings, project_root


def setup_logging(name: str = "bda", level: str | None = None) -> logging.Logger:
    """
    Configure and return a logger with a stream handler.

    Parameters
    ----------
    name : str
        Logger name (e.g., module ``__name__``).
    level : str | None
        Override the level from config/settings.yaml.
    """
    cfg = get_settings()
    log_level_str = (level or cfg.get("logging", {}).get("level", "INFO")).upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger(name)
    if logger.handlers:
        # Already configured — don't add duplicate handlers.
        logger.setLevel(log_level)
        return logger

    logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Also log to a file in logs/ (best effort — do not crash if logs/ missing)
    logs_dir = project_root() / "logs"
    try:
        logs_dir.mkdir(exist_ok=True)
        fh = logging.FileHandler(logs_dir / "pipeline.log", encoding="utf-8")
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except OSError:
        pass  # Non-fatal; console logging continues.

    return logger
