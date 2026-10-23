"""
src/discovery/query_builder.py
Phase R6 — Deterministic Query Builder for Beauty Creator Discovery.
Derives bounded, deterministic search queries from a brand product brief
and the verified domain lexicon in config/domains/beauty_personal_care.yaml.
Zero LLM calls, zero network calls.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from src.common.config import project_root


def load_domain_lexicon() -> dict[str, Any]:
    """Load the Beauty & Personal Care domain lexicon configuration."""
    cfg_path = project_root() / "config" / "domains" / "beauty_personal_care.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_search_queries(
    product_brief: str,
    max_queries: int = 3,
) -> list[str]:
    """
    Build deterministic YouTube search queries from a product brief.

    Extracts matched micro-domain keywords (skincare, makeup, haircare)
    and pairs them with high-intent creator discovery intents:
      - 'review'
      - 'routine'
      - 'tutorial'

    Parameters
    ----------
    product_brief : str
        Brand input text (e.g. "hydrating vitamin C serum for oily skin").
    max_queries : int
        Maximum number of queries to generate (bounded for quota safety).

    Returns
    -------
    list[str]
        List of unique, deterministic search query strings.
    """
    if not product_brief or not product_brief.strip():
        return ["skincare routine beauty tutorial review"]

    lexicon = load_domain_lexicon()
    core_terms = [
        item["term"]
        for item in lexicon.get("keywords", {}).get("core", [])
        if isinstance(item, dict) and "term" in item
    ]

    brief_clean = product_brief.lower()
    tokens = set(re.findall(r"[a-z0-9_-]+", brief_clean))

    # Identify matching domain terms in the brief
    matched_terms: list[str] = []
    for term in core_terms:
        term_clean = term.lower()
        if " " in term_clean:
            if term_clean in brief_clean:
                matched_terms.append(term_clean)
        else:
            if term_clean in tokens:
                matched_terms.append(term_clean)

    if not matched_terms:
        # Generic beauty intent if no specific keyword matched
        matched_terms = ["beauty"]

    # Deduplicate while preserving deterministic order
    seen = set()
    unique_terms = []
    for t in matched_terms:
        if t not in seen:
            seen.add(t)
            unique_terms.append(t)

    # Intent suffixes for creator discovery
    intents = ["review", "routine", "tutorial"]

    queries: list[str] = []
    # Primary query: most specific matched terms + intent
    primary_terms = " ".join(unique_terms[:3])
    for intent in intents:
        q = f"{primary_terms} {intent}".strip()
        if q not in queries:
            queries.append(q)
        if len(queries) >= max_queries:
            break

    return queries[:max_queries]
