"""
scripts/update_readme_metrics.py
Replaces the section between <!-- MODEL_RESULTS_START --> and
<!-- MODEL_RESULTS_END --> in README.md with the content of
metrics/latest.md.

Run at the end of every phase that trains a model.

Usage:
    python scripts/update_readme_metrics.py
"""
from __future__ import annotations

from pathlib import Path

# These are module-level so tests can patch them.
README_PATH = Path(__file__).resolve().parents[1] / "README.md"
LATEST_MD_PATH = Path(__file__).resolve().parents[1] / "metrics" / "latest.md"

START_MARKER = "<!-- MODEL_RESULTS_START -->"
END_MARKER = "<!-- MODEL_RESULTS_END -->"


def update_readme(
    readme_path: Path | None = None,
    latest_md_path: Path | None = None,
) -> None:
    rp = readme_path or README_PATH
    lp = latest_md_path or LATEST_MD_PATH

    if not rp.exists():
        raise FileNotFoundError(f"README not found: {rp}")
    if not lp.exists():
        raise FileNotFoundError(
            f"metrics/latest.md not found: {lp}. "
            "Run a model training script first."
        )

    readme_text = rp.read_text(encoding="utf-8")
    latest_content = lp.read_text(encoding="utf-8")

    start_idx = readme_text.find(START_MARKER)
    end_idx = readme_text.find(END_MARKER)

    if start_idx == -1 or end_idx == -1:
        raise ValueError(
            f"README.md is missing one or both markers:\n"
            f"  {START_MARKER}\n  {END_MARKER}\n"
            "Add these markers to README.md to enable auto-update."
        )
    if start_idx >= end_idx:
        raise ValueError("START_MARKER must appear before END_MARKER in README.md.")

    new_readme = (
        readme_text[:start_idx + len(START_MARKER)]
        + "\n"
        + latest_content.strip()
        + "\n"
        + readme_text[end_idx:]
    )

    rp.write_text(new_readme, encoding="utf-8")
    print(f"✅ README.md model results section updated from {lp}")


if __name__ == "__main__":
    update_readme()
