"""
src/app/pages_impl/model_results.py
Page 3: Model Results & Benchmarks.
Reads strictly from metrics/model_registry.csv and metrics/runs/.
NO hardcoded metrics or manual literals allowed (R7, T-A3, T-A4).
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.app.components import render_header, render_disclaimer, render_confusion_matrix_chart
from src.app.data_loader import (
    load_model_registry,
    load_confusion_matrix,
    load_backtest_results,
    load_run_metrics_json,
)


def render_model_results_page(registry_df: pd.DataFrame | None = None) -> None:
    render_header(
        title="Model Registry & Benchmark Results",
        subtitle="Empirically measured train, validation, and test performance across all pipeline models.",
        badge="Governance & Metrics",
    )
    render_disclaimer()

    # Load registry (supports injected DataFrame for T-A3 test)
    if registry_df is None:
        registry_df = load_model_registry()

    if registry_df.empty:
        st.warning("No model runs recorded in metrics/model_registry.csv yet.")
        return

    # ── Section 1: All Logged Models Table ────────────────────────────────────
    st.subheader("1. Active Models in Model Registry")
    st.caption("Every entry corresponds to an actual logged Spark ML training run. Hardcoding metrics is strictly prohibited.")

    # Select columns to display
    summary_cols = [
        "model_name",
        "task",
        "algorithm",
        "train_accuracy",
        "val_accuracy",
        "test_accuracy",
        "val_macro_f1",
        "val_pr_auc",
        "test_rmse",
        "majority_baseline_accuracy",
        "notes",
    ]
    disp_cols = [c for c in summary_cols if c in registry_df.columns]

    # Format numeric columns for clean display
    formatted_df = registry_df[disp_cols].copy()
    for col in ["train_accuracy", "val_accuracy", "test_accuracy", "val_macro_f1", "val_pr_auc", "majority_baseline_accuracy"]:
        if col in formatted_df.columns:
            formatted_df[col] = formatted_df[col].apply(lambda x: f"{x:.4f}" if pd.notnull(x) else "-")
    if "test_rmse" in formatted_df.columns:
        formatted_df["test_rmse"] = formatted_df["test_rmse"].apply(lambda x: f"{x:.4f}" if pd.notnull(x) else "-")

    st.dataframe(formatted_df, use_container_width=True)

    # ── Section 2: Validation Performance Comparison ──────────────────────────
    st.markdown("---")
    st.subheader("2. Model Performance vs. Baseline")

    # Filter to classifier models with val_accuracy
    classifiers = registry_df[
        (registry_df["task"].isin(["domain_classification", "influencer_classification"]))
        & (registry_df["val_accuracy"].notnull())
    ].copy()

    if not classifiers.empty:
        chart_data = []
        for _, r in classifiers.iterrows():
            m_name = f"{r.get('model_name', '')} ({r.get('algorithm', '')})"
            chart_data.append({"Model": m_name, "Metric": "Validation Accuracy", "Score": float(r["val_accuracy"])})
            if pd.notnull(r.get("majority_baseline_accuracy")):
                chart_data.append({"Model": m_name, "Metric": "Majority Baseline", "Score": float(r["majority_baseline_accuracy"])})
            if pd.notnull(r.get("val_macro_f1")):
                chart_data.append({"Model": m_name, "Metric": "Macro F1", "Score": float(r["val_macro_f1"])})

        chart_df = pd.DataFrame(chart_data)
        fig_comp = px.bar(
            chart_df,
            x="Model",
            y="Score",
            color="Metric",
            barmode="group",
            color_discrete_sequence=["#0EA5E9", "#64748B", "#8B5CF6"],
            range_y=[0.0, 1.05],
        )
        fig_comp.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#CBD5E1"),
            margin=dict(l=10, r=10, t=10, b=10),
            height=340,
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    # ── Section 3: Run Inspector (Confusion Matrix & Artifacts) ───────────────
    st.markdown("---")
    st.subheader("3. Inspect Specific Run Artifacts")

    available_runs = registry_df["run_id"].dropna().tolist() if "run_id" in registry_df.columns else []
    if available_runs:
        selected_run = st.selectbox("Select Run ID to Inspect:", available_runs, index=len(available_runs) - 1)
        run_row = registry_df[registry_df["run_id"] == selected_run].iloc[0]

        r_col1, r_col2 = st.columns([1, 1])

        with r_col1:
            st.markdown(f"**Model Details:** `{run_row.get('model_name')}`")
            st.write(f"- Task: **{run_row.get('task')}**")
            st.write(f"- Algorithm: **{run_row.get('algorithm')}**")
            st.write(f"- Timestamp: `{run_row.get('timestamp_utc')}`")
            if pd.notnull(run_row.get("overfit_gap_acc")) and float(run_row.get("overfit_gap_acc", 0.0)) > 0.10:
                st.warning(f"⚠️ **Overfit Alert**: Train - Val accuracy gap is {float(run_row['overfit_gap_acc']):.4f} (> 0.10 threshold).")

            # Load metrics.json
            metrics_json = load_run_metrics_json(selected_run)
            if metrics_json:
                with st.expander("Full metrics.json payload"):
                    st.json(metrics_json)

        with r_col2:
            cm_df = load_confusion_matrix(selected_run)
            if cm_df is not None:
                st.markdown("**Validation Confusion Matrix:**")
                fig_cm = render_confusion_matrix_chart(cm_df)
                st.plotly_chart(fig_cm, use_container_width=True)
            else:
                st.info("No confusion matrix artifact stored for this run (e.g. regression model).")

    # ── Section 4: Time-Split Backtest Results ────────────────────────────────
    st.markdown("---")
    st.subheader("4. Time-Split Backtest Evaluation (Cutoff T = 2019-01-01)")
    st.caption("Temporal holdout test: models trained on <= T, evaluated on strictly unseen post-T videos.")

    backtest_df = load_backtest_results()
    if not backtest_df.empty:
        col_map = {
            "method": "Ranking Method",
            "precision@5": "Precision@5",
            "precision@10": "Precision@10",
            "ndcg@5": "NDCG@5",
            "ndcg@10": "NDCG@10",
            "spearman_rho": "Spearman rho",
            "spearman_pvalue": "p-value",
        }
        disp_bt = backtest_df.rename(columns=col_map)
        st.dataframe(disp_bt)

        id_var = "Ranking Method" if "Ranking Method" in disp_bt.columns else disp_bt.columns[0]
        val_vars = [c for c in ["Precision@5", "NDCG@5", "NDCG@10"] if c in disp_bt.columns]

        if val_vars and id_var in disp_bt.columns:
            bt_melted = pd.melt(
                disp_bt,
                id_vars=[id_var],
                value_vars=val_vars,
                var_name="Evaluation Metric",
                value_name="Score",
            )
            fig_bt = px.bar(
                bt_melted,
                x=id_var,
                y="Score",
                color="Evaluation Metric",
                barmode="group",
                color_discrete_sequence=["#10B981", "#38BDF8", "#6366F1"],
                range_y=[0.0, 1.0],
            )
            fig_bt.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#CBD5E1"),
                margin=dict(l=10, r=10, t=10, b=10),
                height=300,
            )
            st.plotly_chart(fig_bt, use_container_width=True)
    else:
        st.info("No backtest results found in metrics/backtest_results.csv.")
