"""
src/app/main.py
Phase 8 — Main Streamlit Application Entrypoint.
Multi-page navigation for Domain-Aware Influencer Detection & Promotion Potential Ranking.
CRITICAL: Must not import or start Spark per page load (T-A1).
"""
from __future__ import annotations

import streamlit as st

from src.app.components import render_custom_css
from src.app.pages_impl.find_influencers import render_find_influencers_page
from src.app.pages_impl.creator_card import render_creator_card_page
from src.app.pages_impl.model_results import render_model_results_page
from src.app.pages_impl.pipeline_status import render_pipeline_status_page


def main() -> None:
    # Configure Streamlit page layout
    st.set_page_config(
        page_title="YouTube Influencer Intelligence | BDA Platform",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Inject modern custom dark styling
    render_custom_css()

    # Sidebar Navigation
    st.sidebar.markdown(
        """
        <div style="padding: 10px 0 16px 0;">
            <div style="font-size: 1.25rem; font-weight: 800; color: #FFFFFF; display: flex; align-items: center; gap: 8px;">
                <span>🎯</span> InfluencerAI
            </div>
            <div style="font-size: 0.8rem; color: #38BDF8; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;">
                Hadoop + Spark ML Platform
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_selection = st.sidebar.radio(
        "Navigation",
        [
            "🔍 Find Influencers",
            "👤 Creator Card",
            "📊 Model Results",
            "⚙️ Pipeline Status",
        ],
        index=0,
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        """
        <div style="font-size: 0.82rem; color: #94A3B8; line-height: 1.5;">
            <strong>System Summary:</strong><br>
            • Deep Domain: <em>Beauty & Personal Care</em><br>
            • Engine: <em>Spark ML (GBT + TF-IDF)</em><br>
            • Quota Guard: <em>Pacific Ledger Rollover</em><br>
            • Backtest: <em>Unseen 2019 Holdout</em>
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
