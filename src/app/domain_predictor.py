"""
src/app/domain_predictor.py
Fast in-app domain prediction and product brief semantic matcher.
Operates 100% in pure Python without invoking Spark (T-A1).
Handles empty, blank, or odd/corrupted input text gracefully (T-A2).
Provides lexicon driver transparency, alternative domain ranking, and out-of-domain detection.
"""
from __future__ import annotations

import re
from typing import Any
import yaml

from src.common.paths import project_root


class DomainPredictor:
    """Predicts product domain, micro-domains, and semantic keywords from product brief text."""

    def __init__(self) -> None:
        self.root = project_root()
        self.taxonomy = self._load_taxonomy()
        self.bpc_keywords = self._load_bpc_keywords()

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
            "fitness_health": {
                "micro_domains": ["gym_weightlifting", "yoga_mindfulness", "nutrition_supplements", "running_cardio"]
            },
            "technology": {
                "micro_domains": ["smartphones_tablets", "laptops_computers", "gaming_hardware", "software_apps"]
            },
            "finance_investing": {
                "micro_domains": ["budgeting", "investing", "crypto", "real_estate"]
            },
        }

    def _load_bpc_keywords(self) -> list[str]:
        bpc_path = self.root / "config" / "domains" / "beauty_personal_care.yaml"
        keywords = []
        if bpc_path.exists():
            try:
                with open(bpc_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    for item in data.get("keywords", {}).get("core", []):
                        if isinstance(item, dict):
                            keywords.append(item.get("term", "").lower())
                        elif isinstance(item, str):
                            keywords.append(item.lower())
            except Exception:
                pass
        if not keywords:
            keywords = [
                "skincare", "makeup", "serum", "moisturizer", "sunscreen", "spf",
                "lipstick", "foundation", "cleanser", "haircare", "shampoo",
                "fragrance", "perfume", "retinol", "hyaluronic", "beauty",
                "nail", "mascara", "eyeliner", "conditioner", "matte", "gloss"
            ]
        return list(dict.fromkeys(keywords))  # unique preserving order

    def predict(self, text: str | None) -> dict[str, Any]:
        """
        Predict domain and micro-domains for a product brief.
        Handles empty or odd input strings without crashing (T-A2).
        Returns top lexicon terms and top alternative domains.
        """
        domain_display_names = {
            "beauty_personal_care": "Beauty & Personal Care",
            "fitness_health": "Fitness & Health",
            "technology": "Technology & Consumer Electronics",
            "finance_investing": "Finance & Investing",
        }

        # Clean and validate input
        if text is None:
            raw = ""
        else:
            raw = str(text).strip()

        alphanumeric = re.sub(r"[^\w\s]", "", raw)
        if not raw or not alphanumeric.strip() or len(raw) < 2:
            return {
                "domain": "beauty_personal_care",
                "domain_name": "Beauty & Personal Care",
                "confidence": 0.50,
                "domain_match_score": 0.50,
                "is_fallback": True,
                "is_outside_beauty": False,
                "matched_micro_domains": ["all"],
                "matched_keywords": [],
                "top_lexicon_terms": [],
                "top_alternatives": [],
                "message": "Enter a product description to tailor influencer fit scoring.",
            }

        text_lower = raw.lower()
        words = set(re.findall(r"\b[a-z]{2,}\b", text_lower))

        # Base prior scores across macro domains
        scores: dict[str, float] = {
            "beauty_personal_care": 0.10,
            "fitness_health": 0.05,
            "technology": 0.05,
            "finance_investing": 0.05,
        }

        # 1. Match Beauty keywords (exact terms or sub-word tokens)
        matched_bpc = []
        for kw in self.bpc_keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                matched_bpc.append(kw)
            elif any(w == kw or (len(w) >= 4 and w in kw) for w in words):
                matched_bpc.append(kw)
        matched_bpc = list(dict.fromkeys(matched_bpc))

        scores["beauty_personal_care"] += min(len(matched_bpc) * 0.20, 0.85)

        # 2. Check tech, fitness, finance indicators
        tech_words = {"tech", "app", "phone", "laptop", "software", "device", "pc", "gadget", "gpu", "cpu", "ai", "hardware"}
        fitness_words = {"fitness", "gym", "workout", "protein", "supplement", "weight", "diet", "running", "training", "whey", "creatine"}
        finance_words = {"finance", "crypto", "invest", "money", "stock", "trading", "wallet", "budget", "bank", "etf", "portfolio"}

        matched_tech = words & tech_words
        matched_fitness = words & fitness_words
        matched_finance = words & finance_words

        scores["technology"] += len(matched_tech) * 0.25
        scores["fitness_health"] += len(matched_fitness) * 0.25
        scores["finance_investing"] += len(matched_finance) * 0.25

        # Normalise to pseudo-probabilities / relative match scores
        total = sum(scores.values()) or 1.0
        probs = {k: v / total for k, v in scores.items()}

        sorted_domains = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
        best_domain, best_score = sorted_domains[0]
        confidence = round(max(best_score, 0.50), 2)

        # Top 2 alternative domains
        top_alternatives = []
        for d, s in sorted_domains[1:3]:
            if s > 0.05:
                top_alternatives.append({
                    "domain": d,
                    "domain_name": domain_display_names.get(d, d),
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

        top_lexicon_terms = matched_bpc[:3] if best_domain == "beauty_personal_care" else list(words & (tech_words | fitness_words | finance_words))[:3]

        is_outside = (best_domain != "beauty_personal_care")
        if is_outside:
            msg = (
                f"Classified as '{domain_display_names.get(best_domain, best_domain)}' ({int(confidence * 100)}% match score). "
                f"Note: This pipeline's scored creators are currently limited to the Beauty & Personal Care cohort."
            )
        else:
            msg = (
                f"Identified Beauty category: {', '.join(matched_micro[:2])} "
                f"({int(confidence * 100)}% domain match score)."
            )

        return {
            "domain": best_domain,
            "domain_name": domain_display_names.get(best_domain, best_domain.replace("_", " ").title()),
            "confidence": confidence,
            "domain_match_score": confidence,
            "is_fallback": False,
            "is_outside_beauty": is_outside,
            "matched_micro_domains": matched_micro,
            "matched_keywords": matched_bpc[:6],
            "top_lexicon_terms": top_lexicon_terms,
            "top_alternatives": top_alternatives,
            "message": msg,
        }
