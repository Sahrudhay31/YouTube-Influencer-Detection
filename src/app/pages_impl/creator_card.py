"""
src/app/pages_impl/creator_card.py
Page 2: Creator Card Deep-Dive.
Displays multi-factor score breakdown, radar chart, sponsor track record, and authenticity diagnostics.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.app.components import render_header, render_disclaimer, render_radar_chart
from src.app.data_loader import load_scored_creators


def render_creator_card_page() -> None:
    render_header(
        title="Creator Intelligence Card",
        subtitle="Individual channel audit, component score contributions, and sponsorship track record.",
        badge="Creator Deep-Dive",
    )
    render_disclaimer()

    creators_df = load_scored_creators()
    if creators_df.empty:
        st.error("No creator profiles found in data/gold/. Please ensure gold data exists.")
        return

    # Select creator
    st.subheader("Select Creator to Inspect")
    channel_list = creators_df["channel_id"].tolist()

    # Form selector label showing rank and tier
    def format_creator_label(ch_id: str) -> str:
        row = creators_df[creators_df["channel_id"] == ch_id].iloc[0]
        score = row.get("promotion_potential_score", 0.0)
        tier = row.get("size_tier", "Unknown")
        return f"{ch_id} | Tier: {tier} | Score: {score:.1f}"

    selected_id = st.selectbox(
        "Choose a channel ID:",
        channel_list,
        format_func=format_creator_label,
        index=0,
    )

    row = creators_df[creators_df["channel_id"] == selected_id].iloc[0]

    # Header Card
    st.markdown("---")
    c_top1, c_top2, c_top3, c_top4 = st.columns([2, 1, 1, 1])

    with c_top1:
        tier = row.get("size_tier", "Nano")
        badge_class = f"badge-{tier.lower()}"
        st.markdown(
            f"""
            <div style="display: flex; align-items: baseline; gap: 10px;">
                <h2 style="margin: 0; color: #FFFFFF; font-size: 1.8rem;">{selected_id}</h2>
                <span class="{badge_class}">{tier}</span>
            </div>
            <p style="color: #94A3B8; margin: 4px 0 0 0;">
                Domain: <strong>Beauty & Personal Care</strong> | Focus: <strong>{row.get('domain_purity', 0.8)*100:.1f}% in-domain</strong>
                &nbsp;|&nbsp; <a href="https://www.youtube.com/channel/{selected_id}" target="_blank" style="color: #38BDF8; text-decoration: none; font-weight: 600;">🔗 View Channel on YouTube ↗</a>
            </p>
            """,
            unsafe_allow_html=True,
        )

    score_val = float(row.get("promotion_potential_score", 50.0))
    c_top2.metric("Promotion Score", f"{score_val:.1f}/100")
    c_top3.metric("Median Views", f"{int(row.get('median_views', 0)):,}")
    c_top4.metric("Engagement Rate", f"{row.get('engagement_rate', 0.0)*100:.2f}%")

    # Partial evidence alert if applicable
    is_partial = bool(row.get("partial_evidence", False))
    if is_partial:
        st.warning("⚠️ **Partial Evidence Profile**: One or more components were absent and dynamically renormalised. Confidence score scaled appropriately.")

    # ── Two-column breakdown: Radar chart & Component table ──────────────────
    st.markdown("### 1. Promotion-Potential Component Breakdown")
    c_radar, c_bars = st.columns([1, 1])

    # Extract component scores
    components = {
        "Product/Domain Fit": float(row.get("comp_fit", 0.5)),
        "Influencer Prob": float(row.get("prediction", 0.5)),
        "Real Reach": float(row.get("comp_real_reach", 0.5)),
        "Conversion Evidence": float(row.get("comp_conversion_evidence", 0.5) or 0.4),
        "Engagement Quality": float(row.get("comp_engagement_quality", 0.5)),
        "Consistency": float(row.get("comp_consistency", 0.5)),
    }

    with c_radar:
        fig_radar = render_radar_chart(components)
        st.plotly_chart(fig_radar, use_container_width=True)

    with c_bars:
        comp_df = pd.DataFrame([
            {"Component": k, "Normalized Score": round(v * 100, 1)}
            for k, v in components.items()
        ])
        fig_bar = px.bar(
            comp_df,
            x="Normalized Score",
            y="Component",
            orientation="h",
            color="Normalized Score",
            color_continuous_scale="Blues",
            range_x=[0, 100],
        )
        fig_bar.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#CBD5E1"),
            coloraxis_showscale=False,
            margin=dict(l=10, r=10, t=10, b=10),
            height=280,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # ── Section 2: Sponsorship & Commercial Track Record ─────────────────────
    st.markdown("---")
    st.markdown("### 2. Sponsorship & Promotional Track Record")

    sp_col1, sp_col2, sp_col3, sp_col4 = st.columns(4)
    spons_count = int(row.get("sponsored_count", 0))
    total_videos = int(row.get("video_count", 1))
    spons_rate = float(row.get("sponsored_rate", 0.0)) * 100
    promo_lift = row.get("promo_lift", None)

    sp_col1.metric("Sponsored Videos", f"{spons_count:,}", f"{spons_rate:.1f}% of catalog")
    sp_col2.metric("Total Catalog Videos", f"{total_videos:,}")

    if pd.notnull(promo_lift) and float(promo_lift) > 0:
        sp_col3.metric("Promo Lift Multiplier", f"{float(promo_lift):.2f}x", "vs organic baseline")
    else:
        sp_col3.metric("Promo Lift Multiplier", "N/A", "insufficient sponsored sample")

    pen_sat = float(row.get("penalty_saturation", 0.0))
    sp_col4.metric("Sponsorship Saturation Penalty", f"-{pen_sat:.1f} pts", "penalty" if pen_sat > 0 else "optimal")

    # ── Section 3: Audience Consistency & Health ─────────────────────────────
    st.markdown("---")
    st.markdown("### 3. Audience Health & Consistency Signals")

    h_col1, h_col2, h_col3 = st.columns(3)
    cv_val = float(row.get("view_consistency_cv", 1.0))
    h_col1.metric("View Volatility (CV)", f"{cv_val:.2f}", "lower is more predictable")

    cadence = float(row.get("upload_cadence_days", 7.0))
    h_col2.metric("Upload Cadence", f"{cadence:.1f} days / video")

    age_days = float(row.get("channel_age_days", 365.0))
    h_col3.metric("Channel Longevity", f"{int(age_days / 365.25)} years", f"{int(age_days):,} days")
