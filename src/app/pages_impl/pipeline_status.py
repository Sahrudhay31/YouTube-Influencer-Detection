"""
src/app/pages_impl/pipeline_status.py
Page 4: Pipeline Status & YouTube Governance (InfluencerAI v2).
Monitors API quota consumption, Pacific ledger 7-day history, audit logs,
30-day retention partition countdown, and data layer freshness.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

from src.app.components import render_header, render_disclaimer
from src.app.data_loader import (
    load_quota_ledger,
    load_api_call_logs,
    load_data_freshness,
    get_project_root,
)
from src.app.quota_service import (
    inspect_quota_status,
    get_seven_day_quota_history,
)
from src.common.config import get_quota_config, get_settings


def render_pipeline_status_page() -> None:
    render_header(
        title="Pipeline Operations & YouTube API Governance",
        subtitle="Real-time quota monitoring, daily consumption ledger, and automated retention compliance status.",
        badge="System Operations & Compliance",
    )
    render_disclaimer()

    quota_cfg = get_quota_config()
    settings = get_settings()

    daily_cap = quota_cfg.get("daily_unit_cap", 8000)
    search_cap = quota_cfg.get("search_list_daily_cap", 20)
    per_run_cap = quota_cfg.get("per_run_max_units", 1500)

    ledger = load_quota_ledger()
    quota_status = inspect_quota_status(
        ledger=ledger,
        daily_cap=daily_cap,
        search_cap=search_cap,
        per_run_cap=per_run_cap,
    )

    units_used = quota_status["units_used"]
    remaining_units = quota_status["remaining_units"]
    search_used = quota_status["search_used"]
    is_exhausted = quota_status["is_exhausted"]
    pct_used = quota_status["pct_used"]

    # ── Section 1: Daily Quota Status ─────────────────────────────────────────
    st.subheader("1. Daily YouTube API Quota Status (Pacific Ledger)")

    q_col1, q_col2, q_col3, q_col4 = st.columns(4)
    q_col1.metric("Units Used Today", f"{units_used:,} / {daily_cap:,}", f"{pct_used:.1f}% consumed")
    q_col2.metric("Remaining Units", f"{remaining_units:,}", delta=f"-{units_used} used", delta_color="normal")
    q_col3.metric("Search Calls Today", f"{search_used} / {search_cap}", f"{search_cap - search_used} left")
    q_col4.metric("Reset Rollover", quota_status["time_to_reset"], help="Time until next Pacific Midnight (America/Los_Angeles)")

    # Status message & progress bar
    if is_exhausted:
        st.error("🔴 **API Quota Server Exhausted**: Google API returned HTTP 403 quotaExceeded. Execution halted until Pacific midnight.")
    elif units_used > daily_cap * 0.90:
        st.warning("🟡 **Quota Warning**: Over 90% of daily unit budget consumed. Live search should be used selectively.")
    else:
        st.success("🟢 **Quota Guard Active**: Operating safely within 8,000 unit daily allocation with 20% Google Cloud safety margin.")

    st.progress(min(units_used / max(1, daily_cap), 1.0), text=f"Daily Quota: {units_used:,} of {daily_cap:,} units utilized")
    st.caption(f"Enforced by `src/ingestion/quota_guard.py`. Per-run ceiling: **{per_run_cap:,} units**. Ledger reset: Pacific Midnight.")

    # ── Section 2: 7-Day Quota Consumption History ────────────────────────────
    st.markdown("---")
    st.subheader("2. 7-Day Quota Consumption History")

    history_records = get_seven_day_quota_history(ledger)
    if history_records:
        h_df = pd.DataFrame(history_records)
        fig_hist = px.bar(
            h_df,
            x="date",
            y="units_used",
            title="Daily Units Consumed (Last 7 Recorded Days)",
            color="units_used",
            color_continuous_scale="Blues",
            text="units_used",
        )
        fig_hist.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#CBD5E1"),
            margin=dict(l=10, r=10, t=35, b=10),
            height=260,
            xaxis=dict(title="Pacific Date (YYYY-MM-DD)"),
            yaxis=dict(title="Units Consumed", range=[0, max(daily_cap, max(h_df['units_used']) + 500)]),
            coloraxis_showscale=False,
        )
        fig_hist.add_hline(y=daily_cap, line_dash="dot", line_color="#EF4444", annotation_text="8k Cap")
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("No prior ledger history recorded in state/quota_ledger.json.")

    # ── Section 3: 30-Day Retention Compliance Monitor ────────────────────────
    st.markdown("---")
    st.subheader("3. YouTube Terms 30-Day Retention Compliance Monitor")

    raw_api_days = settings.get("retention", {}).get("raw_api_days", 30)
    warning_days = settings.get("retention", {}).get("refresh_warning_days", 25)

    root = get_project_root()
    raw_api_dir = root / "data" / "raw" / "api"
    partitions = []
    if raw_api_dir.exists():
        for d in raw_api_dir.iterdir():
            if d.is_dir() and "dt=" in d.name:
                dt_str = d.name.replace("dt=", "")
                try:
                    p_date = datetime.strptime(dt_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    age_days = (datetime.now(timezone.utc) - p_date).days
                    days_left = max(0, raw_api_days - age_days)
                    status = "🚨 EXPIRED (Purge Imminent)" if days_left <= 0 else ("⚠️ Expiring Soon" if days_left <= (raw_api_days - warning_days) else "✅ Compliant")
                    partitions.append({
                        "Partition": d.name,
                        "Capture Date": dt_str,
                        "Age (Days)": age_days,
                        "Days to Purge": days_left,
                        "Compliance Status": status,
                    })
                except Exception:
                    pass

    r_col1, r_col2 = st.columns([2, 1])
    with r_col1:
        st.markdown(
            f"""
            - **Raw API Partition Retention:** Max **{raw_api_days} days** (enforced automatically by `src/maintenance/purge_api_data.py`).
            - **Automated Warning Threshold:** Day {warning_days}+ triggers refresh or purge flag.
            - **Privacy Comment Hashing:** Commenter IDs are salted via SHA-256 before disk writes (`COMMENT_HASH_SALT`).
            """
        )

    with r_col2:
        if any(p["Days to Purge"] == 0 for p in partitions):
            st.error("🚨 Stale Partitions Detected. Run purge_api_data.py.")
        else:
            st.markdown(
                """
                <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 10px; padding: 12px; text-align: center;">
                    <span style="font-size: 1.4rem;">🛡️</span>
                    <div style="color: #34D399; font-weight: 700; font-size: 1.0rem;">Retention Compliant</div>
                    <div style="color: #94A3B8; font-size: 0.8rem;">Zero Stale API Partitions (>30d)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if partitions:
        st.dataframe(pd.DataFrame(partitions), hide_index=True, use_container_width=True)
    else:
        st.caption("No raw API date-partition directories currently stored in `data/raw/api/`.")

    # ── Section 4: Recent API Audit Log ───────────────────────────────────────
    st.markdown("---")
    st.subheader("4. Recent API Audit Trail (logs/api_calls.jsonl)")

    api_logs = load_api_call_logs(limit=25)
    if api_logs:
        log_df = pd.DataFrame(api_logs)
        display_log_cols = [c for c in ["timestamp", "method", "units", "status", "key_tag", "param_hash", "endpoint", "units_charged", "status_code"] if c in log_df.columns]
        st.dataframe(log_df[display_log_cols], hide_index=True, use_container_width=True, height=220)
    else:
        st.info("No API invocations logged in `logs/api_calls.jsonl` yet.")

    # ── Section 5: Data Lake Freshness & Environment Mode ─────────────────────
    st.markdown("---")
    st.subheader("5. Data Lake Storage Freshness & Architecture")

    freshness_data = load_data_freshness()
    f_col1, f_col2 = st.columns([1, 2])

    with f_col1:
        st.metric("Active Storage Mode", freshness_data["storage_mode"], help="Configured in config/settings.yaml (file:/// vs hdfs://)")
        st.write("- **Engine**: Spark ML batch pipelines")
        st.write("- **Storage**: Snappy Columnar Parquet")
        st.write("- **Python**: 3.11 venv (Standalone)")

    with f_col2:
        table_df = pd.DataFrame(freshness_data["tables"])
        st.dataframe(
            table_df.rename(columns={
                "name": "Data Asset",
                "layer": "Lake Layer",
                "exists": "Status",
                "modified": "Last Modified",
                "size_mb": "Size (MB)",
                "path": "Relative Path",
            }),
            column_config={
                "Status": st.column_config.CheckboxColumn("Exists", disabled=True),
            },
            hide_index=True,
            use_container_width=True,
        )
