"""
src/discovery/query_builder.py
Multi-Domain Deterministic Query Builder for YouTube Creator Discovery.
Derives bounded, deterministic search queries from a product brief or topic query
across any domain (Beauty, Technology, Fitness, Gaming, Finance, Food, Travel, Education).
Zero LLM calls, zero network calls.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from src.common.config import project_root


STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "with",
    "by", "from", "up", "about", "into", "over", "after", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "my", "your", "his", "her", "its", "our", "their", "this", "that", "these", "those"
}


def load_domain_lexicon(domain: str = "beauty_personal_care") -> dict[str, Any]:
    """Load domain configuration and lexicon YAML."""
    cfg_path = project_root() / "config" / "domains" / f"{domain}.yaml"
    if not cfg_path.exists():
        cfg_path = project_root() / "config" / "domains" / "beauty_personal_care.yaml"

    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


def build_search_queries(
    product_brief: str,
    max_queries: int = 3,
    domain: str = "auto",
) -> list[str]:
    """
    Build deterministic YouTube search queries from a product brief across any domain.

    Parameters
    ----------
    product_brief : str
        Brand brief or search query text.
    max_queries : int
        Maximum number of queries to generate (bounded for quota safety).
    domain : str
        Target domain key (e.g. 'technology', 'fitness_health', 'beauty_personal_care')
        or 'auto' to auto-detect from brief text.

    Returns
    -------
    list[str]
        List of unique, deterministic search query strings.
    """
    if not product_brief or not product_brief.strip():
        if domain in ("auto", "beauty_personal_care"):
            return ["skincare routine beauty tutorial review"][:max_queries]
        return [f"{domain.replace('_', ' ')} review tutorial guide"][:max_queries]

    brief_clean = product_brief.strip().lower()

    # Determine domain
    target_domain = domain
    if target_domain == "auto":
        from src.app.domain_predictor import DomainPredictor
        pred = DomainPredictor().predict(brief_clean)
        target_domain = pred.get("domain", "beauty_personal_care")

    lexicon = load_domain_lexicon(target_domain)
    core_terms = [
        item["term"]
        for item in lexicon.get("keywords", {}).get("core", [])
        if isinstance(item, dict) and "term" in item
    ]

    tokens = re.findall(r"[a-z0-9_-]+", brief_clean)
    token_set = set(tokens)

    # 1. Match known domain terms in the brief
    matched_terms: list[str] = []
    for term in core_terms:
        term_clean = term.lower()
        if " " in term_clean:
            if term_clean in brief_clean:
                matched_terms.append(term_clean)
        else:
            if term_clean in token_set:
                matched_terms.append(term_clean)

    # 2. Extract significant user words (preserves user's actual keywords)
    significant_words = [
        w for w in tokens
        if len(w) >= 3 and w not in STOP_WORDS
    ]

    # Deduplicate while preserving deterministic order
    seen = set()
    unique_terms = []
    for t in (matched_terms + significant_words):
        if t not in seen:
            seen.add(t)
            unique_terms.append(t)

    # Fallback if no words found (e.g. odd symbols or pure numbers)
    if not unique_terms:
        if target_domain == "beauty_personal_care":
            unique_terms = ["beauty"]
        else:
            unique_terms = [target_domain.replace("_", " ")]

    # Domain intents
    intents = lexicon.get("intents", [])
    if not intents:
        if target_domain == "technology":
            intents = ["review", "unboxing", "benchmarks", "guide"]
        elif target_domain == "fitness_health":
            intents = ["workout", "routine", "review", "guide"]
        elif target_domain == "gaming_entertainment":
            intents = ["gameplay", "walkthrough", "review", "guide"]
        elif target_domain == "finance_investing":
            intents = ["investing", "guide", "analysis", "review"]
        elif target_domain == "food_cooking":
            intents = ["recipe", "tutorial", "cooking", "review"]
        else:
            intents = ["review", "routine", "tutorial", "guide"]

    queries: list[str] = []

    # If user provided a short, clean query (<= 6 words), include it directly
    if 2 <= len(tokens) <= 6:
        clean_user_q = " ".join(tokens)
        if clean_user_q not in queries:
            queries.append(clean_user_q)

    # Synthesize queries from top terms + domain intents
    primary_terms = " ".join(unique_terms[:3])
    for intent in intents:
        # Don't duplicate intent word if already in primary_terms
        if intent in primary_terms:
            q = primary_terms
        else:
            q = f"{primary_terms} {intent}".strip()

        if q not in queries:
            queries.append(q)
        if len(queries) >= max_queries:
            break

    return queries[:max_queries]
