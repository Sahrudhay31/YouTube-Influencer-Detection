"""
src/sponsorship/detector.py
Rule-based sponsorship detection on video titles, descriptions, and tags.
Extracts disclosure flags, affiliate link patterns, promo codes, UTM params, and brand candidates.
"""
from __future__ import annotations

import re
import yaml
from pathlib import Path
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import BooleanType, ArrayType, StringType


def load_sponsorship_config(config_path: str = "config/sponsorship.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def detect_sponsorship_in_text(
    text: str,
    cfg: dict,
) -> dict:
    """
    Pure Python helper for single text verification (used in smoke tests).
    """
    text_lower = (text or "").lower()

    # Disclosures
    disclosures = [p["pattern"].lower() for p in cfg.get("disclosure_phrases", [])]
    has_disc = any(bool(re.search(p, text_lower)) for p in disclosures)

    # Affiliate links
    affiliates = [p["pattern"].lower() for p in cfg.get("affiliate_link_patterns", [])]
    has_aff = any(bool(re.search(p, text_lower)) for p in affiliates)

    # Promo codes
    promo_patterns = [p["pattern"].lower() for p in cfg.get("promo_code_patterns", [])]
    has_promo = any(bool(re.search(p, text_lower)) for p in promo_patterns)

    # UTM params
    utms = [p["pattern"].lower() for p in cfg.get("utm_parameters", [])]
    has_utm = any(bool(re.search(p, text_lower)) for p in utms)

    # Matched brands
    brands = [b["brand"].lower() for b in cfg.get("candidate_brands", [])]
    matched = [b for b in brands if re.search(rf"\b{re.escape(b)}\b", text_lower)]

    is_spon = has_disc or has_aff or has_promo or has_utm

    return {
        "is_sponsored": is_spon,
        "has_disclosure": has_disc,
        "has_affiliate_link": has_aff,
        "has_promo_code": has_promo,
        "has_utm": has_utm,
        "matched_brands": matched,
    }


def add_sponsorship_features(
    df: DataFrame,
    config_path: str = "config/sponsorship.yaml",
) -> DataFrame:
    """
    Adds is_sponsored and evidence columns to DataFrame using native PySpark SQL regex functions.
    """
    cfg = load_sponsorship_config(config_path)

    # Combine title and description (lowercased)
    full_text = F.lower(
        F.concat_ws(" ", F.coalesce(F.col("title"), F.lit("")), F.coalesce(F.col("description"), F.lit("")))
    )

    # 1. Disclosures regex pattern
    disc_patterns = [p["pattern"] for p in cfg.get("disclosure_phrases", [])]
    disc_regex = "|".join([p for p in disc_patterns])

    # 2. Affiliate regex pattern
    aff_patterns = [p["pattern"] for p in cfg.get("affiliate_link_patterns", [])]
    aff_regex = "|".join([p for p in aff_patterns])

    # 3. Promo code regex pattern
    promo_patterns = [p["pattern"] for p in cfg.get("promo_code_patterns", [])]
    promo_regex = "|".join([p for p in promo_patterns])

    # 4. UTM regex pattern
    utm_patterns = [p["pattern"] for p in cfg.get("utm_parameters", [])]
    utm_regex = "|".join([p for p in utm_patterns])

    df_out = (
        df.withColumn("_full_text", full_text)
        .withColumn("has_disclosure", F.col("_full_text").rlike(disc_regex))
        .withColumn("has_affiliate_link", F.col("_full_text").rlike(aff_regex))
        .withColumn("has_promo_code", F.col("_full_text").rlike(promo_regex))
        .withColumn("has_utm", F.col("_full_text").rlike(utm_regex))
        .withColumn(
            "is_sponsored",
            F.col("has_disclosure") | F.col("has_affiliate_link") | F.col("has_promo_code") | F.col("has_utm"),
        )
        .drop("_full_text")
    )

    return df_out
