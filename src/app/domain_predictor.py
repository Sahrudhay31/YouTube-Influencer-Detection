"""
src/app/domain_predictor.py
Fast in-app domain prediction and product brief semantic matcher.
Operates 100% in pure Python without invoking Spark (T-A1).
Handles empty, blank, or odd/corrupted input text gracefully (T-A2).
Supports multi-domain classification: Beauty, Tech, Fitness, Gaming, Finance, Food, Travel, Education.
"""
from __future__ import annotations

import re
from typing import Any
import yaml

from src.common.paths import project_root


class DomainPredictor:
    """Predicts product domain, micro-domains, and semantic keywords from input text."""

    DOMAIN_DISPLAY_NAMES = {
        "beauty_personal_care": "Beauty & Personal Care",
        "technology": "Technology & Gadgets",
        "fitness_health": "Fitness & Health",
        "gaming_entertainment": "Gaming & Esports",
        "finance_investing": "Finance & Investing",
        "food_cooking": "Food & Culinary",
        "travel_adventure": "Travel & Lifestyle",
        "education_science": "Science & Education",
    }

    def __init__(self) -> None:
        self.root = project_root()
        self.taxonomy = self._load_taxonomy()
        self.domain_keywords = self._load_all_domain_keywords()
        self.bpc_keywords = self.domain_keywords.get("beauty_personal_care", [])

    def _load_taxonomy(self) -> dict[str, Any]:
        tax_path = self.root / "config" / "domains" / "taxonomy.yaml"
        if tax_path.exists():
            try:
                with open(tax_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    return data.get("macro_domains", {})
            except Exception:
                pass
        return {
            "beauty_personal_care": {
                "micro_domains": ["skincare", "makeup", "haircare", "nail_art", "fragrance", "personal_hygiene"]
            },
            "technology": {
                "micro_domains": ["smartphones_tablets", "laptops_computers", "gaming_hardware", "software_apps", "ai_machine_learning"]
            },
            "fitness_health": {
                "micro_domains": ["gym_weightlifting", "yoga_mindfulness", "nutrition_supplements", "running_cardio", "calisthenics"]
            },
            "gaming_entertainment": {
                "micro_domains": ["game_reviews_walkthroughs", "esports", "gaming_gear_setups", "streaming_culture"]
            },
            "finance_investing": {
                "micro_domains": ["personal_finance", "stock_investing", "crypto", "real_estate", "dividend_investing"]
            },
            "food_cooking": {
                "micro_domains": ["recipes_cooking_tutorials", "restaurant_reviews", "food_travel_vlogs", "baking_pastry"]
            },
            "travel_adventure": {
                "micro_domains": ["travel_vlogs", "destination_guides", "backpacking", "road_trips"]
            },
            "education_science": {
                "micro_domains": ["science_experiments", "physics_math", "coding_tech", "history_documentary"]
            },
        }

    def _load_all_domain_keywords(self) -> dict[str, list[str]]:
        domain_kw: dict[str, list[str]] = {}
        domains_dir = self.root / "config" / "domains"
        for domain_key in self.DOMAIN_DISPLAY_NAMES.keys():
            cfg_path = domains_dir / f"{domain_key}.yaml"
            kws: list[str] = []
            if cfg_path.exists():
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        for item in data.get("keywords", {}).get("core", []):
                            if isinstance(item, dict):
                                kws.append(item.get("term", "").lower())
                            elif isinstance(item, str):
                                kws.append(item.lower())
                except Exception:
                    pass
            domain_kw[domain_key] = list(dict.fromkeys(kws))

        # Fallback beauty keywords if empty
        if not domain_kw.get("beauty_personal_care"):
            domain_kw["beauty_personal_care"] = [
                "skincare", "makeup", "serum", "moisturizer", "sunscreen", "spf",
                "lipstick", "foundation", "cleanser", "haircare", "shampoo",
                "fragrance", "perfume", "retinol", "hyaluronic", "beauty"
            ]
        return domain_kw

    def predict(self, text: str | None) -> dict[str, Any]:
        """
        Predict domain and micro-domains for text (product brief, video titles, channel bio).
        Handles empty or odd input strings gracefully without crashing (T-A2).
        """
        # Clean and validate input
        if text is None:
            raw = ""
        else:
            raw = str(text).strip()

        alphanumeric = re.sub(r"[^\w\s]", "", raw)
        if not raw or not alphanumeric.strip() or len(raw) < 2:
            return {
                "domain": "beauty_personal_care",
                "domain_name": self.DOMAIN_DISPLAY_NAMES["beauty_personal_care"],
                "confidence": 0.50,
                "domain_match_score": 0.50,
                "is_fallback": True,
                "is_outside_beauty": False,
                "matched_micro_domains": ["all"],
                "matched_keywords": [],
                "top_lexicon_terms": [],
                "top_alternatives": [],
                "message": "Enter a product description or search query to tailor discovery.",
            }

        text_lower = raw.lower()
        words = set(re.findall(r"\b[a-z0-9_-]{2,}\b", text_lower))

        # Score all domains based on keyword matches
        scores: dict[str, float] = {k: 0.05 for k in self.DOMAIN_DISPLAY_NAMES}
        # Prior default weight for beauty in fallback cases
        scores["beauty_personal_care"] = 0.06

        matched_by_domain: dict[str, list[str]] = {}

        for domain, kws in self.domain_keywords.items():
            matched = []
            for kw in kws:
                if " " in kw:
                    if kw in text_lower:
                        matched.append(kw)
                else:
                    if kw in words:
                        matched.append(kw)
            matched_by_domain[domain] = list(dict.fromkeys(matched))
            scores[domain] += len(matched) * 0.25

        # Normalise scores to probabilities
        total = sum(scores.values()) or 1.0
        probs = {k: v / total for k, v in scores.items()}

        sorted_domains = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
        best_domain, best_score = sorted_domains[0]
        confidence = round(min(0.99, max(best_score * 1.5, 0.50)), 2)

        # Top 2 alternative domains
        top_alternatives = []
        for d, s in sorted_domains[1:3]:
            if s > 0.05:
                top_alternatives.append({
                    "domain": d,
                    "domain_name": self.DOMAIN_DISPLAY_NAMES.get(d, d.replace("_", " ").title()),
                    "score": round(s, 2),
                    "pct": int(round(s * 100)),
                })

        # Identify micro-domains within best domain
        matched_micro = []
        domain_specs = self.taxonomy.get(best_domain, {})
        micro_list = domain_specs.get("micro_domains", [])
        for micro in micro_list:
            micro_clean = micro.replace("_", " ")
            if micro_clean in text_lower or any(part in words for part in micro.split("_")):
                matched_micro.append(micro_clean)

        if not matched_micro and micro_list:
            matched_micro = [micro_list[0].replace("_", " ")]

        top_lexicon_terms = matched_by_domain.get(best_domain, [])[:4]
        if not top_lexicon_terms:
            top_lexicon_terms = list(words)[:3]

        domain_title = self.DOMAIN_DISPLAY_NAMES.get(best_domain, best_domain.replace("_", " ").title())
        is_outside = (best_domain != "beauty_personal_care")

        micro_summary = ", ".join(matched_micro[:2]) if matched_micro else "general"
        msg = f"Identified category: {domain_title} ({micro_summary}) · {int(confidence * 100)}% match confidence."

        return {
            "domain": best_domain,
            "domain_name": domain_title,
            "confidence": confidence,
            "domain_match_score": confidence,
            "is_fallback": False,
            "is_outside_beauty": is_outside,
            "matched_micro_domains": matched_micro,
            "matched_keywords": top_lexicon_terms,
            "top_lexicon_terms": top_lexicon_terms,
            "top_alternatives": top_alternatives,
            "message": msg,
        }
