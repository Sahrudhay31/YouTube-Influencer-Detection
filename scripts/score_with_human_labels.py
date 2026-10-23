"""
scripts/score_with_human_labels.py
Phase R4 — Honest Evaluation against Human Annotated Ground Truth.
Computes accuracy, precision, recall, F1, confusion matrix, and Cohen's Kappa
between weak keyword rules and human labels in labels/domain_to_label.csv
and labels/sponsor_to_label.csv.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score, confusion_matrix, precision_recall_fscore_support, accuracy_score

from src.common.config import project_root
from src.common.logging_setup import setup_logging

logger = setup_logging(__name__)


def evaluate_domain_labels(csv_path: Path | None = None) -> dict[str, Any]:
    """
    Evaluate weak domain labels vs human ground truth labels.
    """
    if csv_path is None:
        csv_path = project_root() / "labels" / "domain_to_label.csv"

    if not csv_path.exists():
        logger.warning("Domain labels file not found: %s", csv_path)
        return {"status": "file_not_found"}

    df = pd.read_csv(csv_path)
    mask = df["human_label"].fillna("").astype(str).str.strip() != ""
    labeled = df[mask].copy()

    if len(labeled) == 0:
        logger.info("Domain labels file has 0 human annotations. Awaiting user labeling.")
        return {
            "status": "unlabeled",
            "total_rows": len(df),
            "labeled_rows": 0,
            "message": "Awaiting human annotation in labels/domain_to_label.csv",
        }

    # Binarize labels
    y_true = (labeled["human_label"] == "beauty_personal_care").astype(int)
    y_pred = (labeled["weak_label"] == "beauty_personal_care").astype(int)

    acc = accuracy_score(y_true, y_pred)
    prec, rec, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    cm = confusion_matrix(y_true, y_pred).tolist()
    kappa = cohen_kappa_score(y_true, y_pred)

    res = {
        "status": "evaluated",
        "eval_target": "human_labels",
        "n_samples": len(labeled),
        "accuracy": float(acc),
        "precision": float(prec),
        "recall": float(rec),
        "f1": float(f1),
        "cohen_kappa": float(kappa),
        "confusion_matrix": cm,
    }

    print("\n--- DOMAIN HUMAN EVALUATION ---")
    print(f"Sample Size: {len(labeled)} rows")
    print(f"Accuracy: {acc:.4f} | Precision: {prec:.4f} | Recall: {rec:.4f} | F1: {f1:.4f}")
    print(f"Cohen's Kappa (Agreement): {kappa:.4f}")
    print(f"Confusion Matrix (TN, FP / FN, TP): {cm}")
    return res


def evaluate_sponsor_labels(csv_path: Path | None = None) -> dict[str, Any]:
    """
    Evaluate weak sponsorship disclosure rules vs human annotations.
    """
    if csv_path is None:
        csv_path = project_root() / "labels" / "sponsor_to_label.csv"

    if not csv_path.exists():
        logger.warning("Sponsor labels file not found: %s", csv_path)
        return {"status": "file_not_found"}

    df = pd.read_csv(csv_path)
    mask = df["human_label"].fillna("").astype(str).str.strip() != ""
    labeled = df[mask].copy()

    if len(labeled) == 0:
        logger.info("Sponsor labels file has 0 human annotations. Awaiting user labeling.")
        return {
            "status": "unlabeled",
            "total_rows": len(df),
            "labeled_rows": 0,
            "message": "Awaiting human annotation in labels/sponsor_to_label.csv",
        }

    y_true = (labeled["human_label"] == "sponsored").astype(int)
    y_pred = (labeled["weak_label"] == "sponsored").astype(int)

    acc = accuracy_score(y_true, y_pred)
    prec, rec, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    cm = confusion_matrix(y_true, y_pred).tolist()
    kappa = cohen_kappa_score(y_true, y_pred)

    res = {
        "status": "evaluated",
        "eval_target": "human_labels",
        "n_samples": len(labeled),
        "accuracy": float(acc),
        "precision": float(prec),
        "recall": float(rec),
        "f1": float(f1),
        "cohen_kappa": float(kappa),
        "confusion_matrix": cm,
    }

    print("\n--- SPONSORSHIP HUMAN EVALUATION ---")
    print(f"Sample Size: {len(labeled)} rows")
    print(f"Accuracy: {acc:.4f} | Precision: {prec:.4f} | Recall: {rec:.4f} | F1: {f1:.4f}")
    print(f"Cohen's Kappa: {kappa:.4f}")
    print(f"Confusion Matrix: {cm}")
    return res


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate weak labels against human annotations")
    parser.parse_args()

    print("=" * 60)
    print("PHASE R4: HUMAN GROUND TRUTH EVALUATION")
    print("=" * 60)

    d_res = evaluate_domain_labels()
    s_res = evaluate_sponsor_labels()

    if d_res["status"] == "unlabeled" and s_res["status"] == "unlabeled":
        print("\n[NOTE] Both domain and sponsor CSVs currently have 0 human labels.")
        print("To evaluate models against human ground truth, fill the 'human_label' column in:")
        print("  - labels/domain_to_label.csv (allowed: beauty_personal_care | out_of_domain)")
        print("  - labels/sponsor_to_label.csv (allowed: sponsored | organic)")
        print("All reported metrics remain marked eval_target=weak_labels.")


if __name__ == "__main__":
    main()
