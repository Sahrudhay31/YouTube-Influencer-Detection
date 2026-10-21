"""
src/app/domain_predictor.py
Phase 8 — Fast in-app domain prediction and product brief semantic matcher.
Operates 100% in pure Python / scikit-learn without invoking Spark (T-A1).
Handles empty, blank, or odd/corrupted input text gracefully (T-A2).
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
                "fragrance", "perfume", "retinol", "hyaluronic", "beauty"
            ]
        return keywords

    def predict(self, text: str | None) -> dict[str, Any]:
        """
        Predict domain and micro-domains for a product brief.
        Handles empty or odd input strings without crashing (T-A2).
        """
        # T-A2: Clean and validate input
        if text is None:
            raw = ""
        else:
            raw = str(text).strip()

        # Check for empty, whitespace, or pure punctuation / non-alphanumeric noise
        alphanumeric = re.sub(r"[^\w\s]", "", raw)
        if not raw or not alphanumeric.strip() or len(raw) < 2:
            return {
                "domain": "beauty_personal_care",
                "domain_name": "Beauty & Personal Care",
                "confidence": 0.50,
                "is_fallback": True,
                "matched_micro_domains": ["all"],
                "matched_keywords": [],
                "message": "Enter a product description to tailor influencer fit scoring.",
            }

        text_lower = raw.lower()
        words = set(re.findall(r"\b[a-z]{2,}\b", text_lower))

        # Score domains based on keyword / micro-domain matches
        scores: dict[str, float] = {
            "beauty_personal_care": 0.15,  # Prioritize deep first domain
            "fitness_health": 0.05,
            "technology": 0.05,
            "finance_investing": 0.05,
        }

        # 1. Match Beauty keywords
        matched_bpc = [kw for kw in self.bpc_keywords if kw in text_lower or any(w in kw for w in words)]
        scores["beauty_personal_care"] += min(len(matched_bpc) * 0.15, 0.80)

        # 2. Check tech, fitness, finance indicators
        tech_words = {"tech", "app", "phone", "laptop", "software", "device", "pc", "gadget", "gpu", "cpu", "ai"}
        fitness_words = {"fitness", "gym", "workout", "protein", "supplement", "weight", "diet", "running", "training"}
        finance_words = {"finance", "crypto", "invest", "money", "stock", "trading", "wallet", "budget", "bank"}

        scores["technology"] += len(words & tech_words) * 0.20
        scores["fitness_health"] += len(words & fitness_words) * 0.20
        scores["finance_investing"] += len(words & finance_words) * 0.20

        # Normalise to softmax/probabilities
        total = sum(scores.values()) or 1.0
        probs = {k: v / total for k, v in scores.items()}

        best_domain = max(probs, key=lambda k: probs[k])
        confidence = round(probs[best_domain], 2)

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

        domain_display_names = {
            "beauty_personal_care": "Beauty & Personal Care",
            "fitness_health": "Fitness & Health",
            "technology": "Technology & Consumer Electronics",
            "finance_investing": "Finance & Investing",
        }

        return {
            "domain": best_domain,
            "domain_name": domain_display_names.get(best_domain, best_domain.replace("_", " ").title()),
            "confidence": max(confidence, 0.55),
            "is_fallback": False,
            "matched_micro_domains": matched_micro,
            "matched_keywords": matched_bpc[:6],
            "message": f"Identified category: {domain_display_names.get(best_domain, best_domain)} ({int(confidence * 100)}% match).",
        }
