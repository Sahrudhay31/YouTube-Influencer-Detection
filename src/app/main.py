"""
src/app/main.py
Main Streamlit Application Entrypoint (InfluencerAI v2).
Multi-page navigation for Domain-Aware Influencer Detection & Promotion Potential Ranking.
CRITICAL: Must not import or start Spark per page load (T-A1).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.app.components import render_custom_css
from src.app.leaderboard_logic import build_export_csv
from src.app.pages_impl.find_influencers import render_find_influencers_page
from src.app.pages_impl.creator_card import render_creator_card_page
from src.app.pages_impl.model_results import render_model_results_page
from src.app.pages_impl.pipeline_status import render_pipeline_status_page


def main() -> None:
    st.set_page_config(
        page_title="YouTube Influencer Intelligence | BDA Platform",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Inject modern custom dark styling
    render_custom_css()

    # Initialize session state variables
    if "shortlist" not in st.session_state:
        st.session_state["shortlist"] = []
    if "selected_creator_id" not in st.session_state:
        st.session_state["selected_creator_id"] = None
    if "compare_list" not in st.session_state:
        st.session_state["compare_list"] = []
    if "jump_to_card" not in st.session_state:
        st.session_state["jump_to_card"] = False

    # Sidebar Navigation Branding
    st.sidebar.markdown(
        """
        <div style="padding: 6px 0 12px 0;">
            <div style="font-size: 1.25rem; font-weight: 800; color: #FFFFFF; display: flex; align-items: center; gap: 8px;">
                <span>🎯</span> InfluencerAI
            </div>
            <div style="font-size: 0.75rem; color: #38BDF8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">
                Spark ML batch pipeline on Parquet (HDFS-ready)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_options = [
        "🔍 Find Influencers",
        "👤 Creator Card",
        "📊 Model Results",
        "⚙️ Pipeline Status",
    ]

    # Handle jump from leaderboard Inspect button
    if st.session_state.get("jump_to_card", False):
        default_nav_idx = 1
        st.session_state["jump_to_card"] = False
    else:
        default_nav_idx = 0

    nav_selection = st.sidebar.radio(
        "Navigation",
        nav_options,
        index=default_nav_idx,
        key="main_navigation_radio",
    )

    # Shortlist Drawer in Sidebar
    shortlist = st.session_state["shortlist"]
    st.sidebar.markdown("---")
    with st.sidebar.expander(f"⭐ Campaign Shortlist ({len(shortlist)})", expanded=(len(shortlist) > 0)):
        if shortlist:
            for item in list(shortlist):
                ch_id = item["channel_id"]
                ch_name = item.get("channel_name", ch_id)
                score = item.get("score", 0.0)
                tier = item.get("tier", "")
                c_s1, c_s2 = st.columns([3, 1])
                with c_s1:
                    st.markdown(f"**{ch_name}** ({tier}) — `{score:.1f}`")
                with c_s2:
                    if st.button("❌", key=f"remove_sl_{ch_id}", help="Remove from shortlist"):
                        st.session_state["shortlist"] = [x for x in st.session_state["shortlist"] if x["channel_id"] != ch_id]
                        st.rerun()

            sl_df = pd.DataFrame(shortlist)
            csv_data = build_export_csv(sl_df).encode("utf-8")
            st.download_button(
                label="📥 Export Shortlist (CSV)",
                data=csv_data,
                file_name="campaign_shortlist.csv",
                mime="text/csv",
                key="download_shortlist_csv",
            )
            if st.button("Clear Shortlist", key="clear_shortlist_btn"):
                st.session_state["shortlist"] = []
                st.rerun()
        else:
            st.caption("No creators shortlisted yet. Click '+ Shortlist' on the leaderboard or Creator Card.")

    # "About these numbers" in Sidebar
    with st.sidebar.expander("ℹ️ About These Numbers", expanded=False):
        st.markdown(
            """
            <div style="font-size: 0.82rem; color: #CBD5E1; line-height: 1.5;">
            <strong>Key Metrics Glossary:</strong><br><br>
            • <strong>Promotion Score (0–100):</strong> Percentile rank within the creator's domain and size tier. Score 90 means top 10% among similar-sized beauty channels.<br><br>
            • <strong>Raw Score (0–100):</strong> Weighted composite of active components before percentile normalisation.<br><br>
            • <strong>Partial Evidence:</strong> One or more data streams (e.g. comments or sponsorships) were absent and weights were dynamically rescaled to sum to 100%.<br><br>
            • <strong>Promo Lift (e.g. 1.41x):</strong> Sponsored vs non-sponsored view multiplier. Requires ≥3 sponsored and ≥3 organic videos.<br><br>
            • <strong>Typical Views:</strong> Median views on non-sponsored uploads (pure organic reach).
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Technical System Summary
    st.sidebar.markdown(
        """
        <div style="font-size: 0.78rem; color: #94A3B8; line-height: 1.4; padding: 6px 0;">
            <strong>System Architecture:</strong><br>
            • Deep Domain: <em>Beauty & Personal Care</em><br>
            • Models: <em>TF-IDF text classifier, GBT influencer classifier</em><br>
            • Quota Guard: <em>Pacific Ledger Rollover (8k cap)</em><br>
            • Backtest: <em>3 time-split cutoffs (2018–2019)</em>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Route to selected page
    if nav_selection == "🔍 Find Influencers":
        render_find_influencers_page()
    elif nav_selection == "👤 Creator Card":
        render_creator_card_page()
    elif nav_selection == "📊 Model Results":
        render_model_results_page()
    elif nav_selection == "⚙️ Pipeline Status":
        render_pipeline_status_page()


if __name__ == "__main__":
    main()
