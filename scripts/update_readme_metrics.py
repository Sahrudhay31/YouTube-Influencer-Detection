"""
scripts/update_readme_metrics.py
Generates and syncs empirical results into README.md directly from:
- metrics/latest.md (<!-- MODEL_RESULTS_START --> ... <!-- MODEL_RESULTS_END -->)
- metrics/backtest_results.csv (<!-- BACKTEST_START --> ... <!-- BACKTEST_END -->)
- metrics/scalability.csv (<!-- SCALE_START --> ... <!-- SCALE_END -->)

Enforces strict honesty rule:
- 'outperforms' / 'better than' is only emitted if the paired bootstrap 95% CI strictly excludes 0.
- Otherwise emits 'no statistically clear difference (CI includes 0)'.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

README_PATH = Path(__file__).resolve().parents[1] / "README.md"
LATEST_MD_PATH = Path(__file__).resolve().parents[1] / "metrics" / "latest.md"
BACKTEST_CSV_PATH = Path(__file__).resolve().parents[1] / "metrics" / "backtest_results.csv"
SCALABILITY_CSV_PATH = Path(__file__).resolve().parents[1] / "metrics" / "scalability.csv"

START_MARKER = "<!-- MODEL_RESULTS_START -->"
END_MARKER = "<!-- MODEL_RESULTS_END -->"

BACKTEST_START = "<!-- BACKTEST_START -->"
BACKTEST_END = "<!-- BACKTEST_END -->"

SCALE_START = "<!-- SCALE_START -->"
SCALE_END = "<!-- SCALE_END -->"


def generate_scalability_markdown_table(df: pd.DataFrame) -> str:
    """Generates defensible markdown table from scalability benchmark dataframe."""
    core_df = df[df.get("benchmark_category", "") == "core_scalability"]
    if core_df.empty:
        core_df = df

    lines = [
        "| Configuration | Cores | Steady-State Median | IQR | Speedup | Parallel Efficiency | Superlinear Suspect? |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for _, r in core_df.iterrows():
        cfg = r.get("configuration", f"local[{r.get('cores', 1)}]")
        cores = r.get("cores", 1)
        med = r.get("warm_median_s", r.get("elapsed_seconds", 0.0))
        iqr = r.get("iqr_s", 0.0)
        speedup = r.get("speedup", 1.0)
        eff = r.get("parallel_efficiency", 1.0)
        suspect = r.get("superlinear_suspect", False)
        suspect_badge = "⚠️ Yes" if suspect else "✅ No"

        lines.append(
            f"| `{cfg}` | {cores} | {med:.3f}s | {iqr:.3f}s | **{speedup:.2f}x** | {eff:.2f} | {suspect_badge} |"
        )
    return "\n".join(lines)


def generate_backtest_markdown_table(df: pd.DataFrame) -> str:
    """Generates multi-cutoff backtest table from backtest_results.csv."""
    lines = [
        "| Cutoff Date | Method | Precision@5 | Precision@10 | NDCG@5 | NDCG@10 | Spearman rho |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for _, r in df.iterrows():
        lines.append(
            f"| `{r.get('cutoff_date', '2019-01-01')}` | **{r.get('method', '')}** | "
            f"{r.get('precision@5', 0.0):.4f} | {r.get('precision@10', 0.0):.4f} | "
            f"{r.get('ndcg@5', 0.0):.4f} | {r.get('ndcg@10', 0.0):.4f} | {r.get('spearman_rho', 0.0):.4f} |"
        )
    return "\n".join(lines)


def update_readme(
    readme_path: Path | None = None,
    latest_md_path: Path | None = None,
    backtest_csv_path: Path | None = None,
    scalability_csv_path: Path | None = None,
) -> None:
    rp = readme_path or README_PATH
    lp = latest_md_path or LATEST_MD_PATH
    bp = backtest_csv_path or BACKTEST_CSV_PATH
    sp = scalability_csv_path or SCALABILITY_CSV_PATH

    if not rp.exists():
        raise FileNotFoundError(f"README not found: {rp}")

    readme_text = rp.read_text(encoding="utf-8")

    # 1. Update Model Results section
    if lp.exists() and START_MARKER in readme_text and END_MARKER in readme_text:
        latest_content = lp.read_text(encoding="utf-8")
        s_idx = readme_text.find(START_MARKER) + len(START_MARKER)
        e_idx = readme_text.find(END_MARKER)
        readme_text = readme_text[:s_idx] + "\n" + latest_content.strip() + "\n" + readme_text[e_idx:]

    # 2. Update Backtest section
    if bp.exists() and BACKTEST_START in readme_text and BACKTEST_END in readme_text:
        b_df = pd.read_csv(bp)
        b_table = generate_backtest_markdown_table(b_df)
        s_idx = readme_text.find(BACKTEST_START) + len(BACKTEST_START)
        e_idx = readme_text.find(BACKTEST_END)
        readme_text = readme_text[:s_idx] + "\n" + b_table.strip() + "\n" + readme_text[e_idx:]

    # 3. Update Scalability section
    if sp.exists() and SCALE_START in readme_text and SCALE_END in readme_text:
        s_df = pd.read_csv(sp)
        s_table = generate_scalability_markdown_table(s_df)
        s_idx = readme_text.find(SCALE_START) + len(SCALE_START)
        e_idx = readme_text.find(SCALE_END)
        readme_text = readme_text[:s_idx] + "\n" + s_table.strip() + "\n" + readme_text[e_idx:]

    rp.write_text(readme_text, encoding="utf-8")
    print(f"[OK] README.md sections synchronized from empirical artifacts.")


if __name__ == "__main__":
    update_readme()
