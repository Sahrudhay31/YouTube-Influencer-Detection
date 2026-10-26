"""
src/app/pages_impl/creator_card.py
Page 2: Creator Card Deep-Dive (InfluencerAI v2).
Displays multi-factor score breakdown, radar chart, contribution waterfall,
precise dynamic renormalisation explanations, sponsorship track record, and audience diagnostics.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.app.components import (
    render_header,
    render_disclaimer,
    render_missing_gold_banner,
    render_radar_chart,
    render_waterfall_chart,
)
from src.app.data_loader import load_scored_creators
from src.app.evidence import (
    get_missing_components,
    compute_renormalisation,
    get_evidence_badge,
    COMPONENT_WEIGHTS,
)
from src.app.formatters import (
    format_subscribers,
    format_views,
    format_percentage,
    format_promo_lift,
)


def render_creator_card_page() -> None:
    render_header(
        title="Creator Intelligence Card",
        subtitle="Individual channel audit, component score contributions, and sponsorship track record.",
        badge="Creator Deep-Dive",
    )
    render_disclaimer()

    creators_df = load_scored_creators()
    if creators_df.empty:
        render_missing_gold_banner()
        return

    # Select creator (supports pre-selection via session_state from Find Influencers)
    st.subheader("Select Creator to Inspect")
    channel_list = creators_df["channel_id"].tolist()

    preselected_id = st.session_state.get("selected_creator_id")
    if preselected_id and preselected_id in channel_list:
        default_idx = channel_list.index(preselected_id)
    else:
        default_idx = 0

    def format_creator_label(ch_id: str) -> str:
        r = creators_df[creators_df["channel_id"] == ch_id].iloc[0]
        score = r.get("promotion_potential_score", 0.0)
        raw = r.get("raw_score", 0.0)
        tier = r.get("size_tier", "Unknown")
        name = r.get("channel_name", ch_id)
        raw_str = f"Raw: {raw:.1f} | " if pd.notnull(raw) else ""
        return f"{name} ({ch_id}) | Tier: {tier} | {raw_str}Percentile: {score:.1f}"

    selected_id = st.selectbox(
        "Choose a channel to inspect:",
        channel_list,
        format_func=format_creator_label,
        index=default_idx,
        key="creator_card_selector",
    )

    # Sync back to session_state
    st.session_state["selected_creator_id"] = selected_id
    row = creators_df[creators_df["channel_id"] == selected_id].iloc[0]

    # Header Card
    st.markdown("---")
    c_top1, c_top2, c_top3, c_top4, c_top5 = st.columns([2.2, 1, 1, 1, 1.2])

    ch_name = row.get("channel_name", selected_id)
    tier = str(row.get("size_tier", "Nano")).capitalize()
    badge_class = f"badge-{tier.lower()}"
    evidence_badge = get_evidence_badge(row.get("partial_evidence", False))

    with c_top1:
        st.markdown(
            f"""
            <div style="display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;">
                <h2 style="margin: 0; color: #FFFFFF; font-size: 1.6rem; font-weight: 800;">{ch_name}</h2>
                <span class="{badge_class}">{tier}</span>
                <span style="background-color: {evidence_badge['bg_color']}; color: {evidence_badge['color']}; border: 1px solid {evidence_badge['border_color']}; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 700;">{evidence_badge['label']}</span>
            </div>
            <div style="color: #94A3B8; font-size: 0.82rem; margin-top: 4px;">
                Channel ID: <code>{selected_id}</code> &nbsp;|&nbsp;
                <a href="https://www.youtube.com/channel/{selected_id}" target="_blank" style="color: #38BDF8; text-decoration: none; font-weight: 600;">Open on YouTube ↗</a>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Dual Scores Presentation
    pct_score = float(row.get("promotion_potential_score", 50.0))
    raw_score = float(row.get("raw_score", 50.0)) if pd.notnull(row.get("raw_score")) else None

    c_top2.metric(
        "Percentile Rank",
        f"{pct_score:.1f}/100",
        help="Percentile rank within domain x size tier. (100 = top channel in this tier).",
    )
    c_top3.metric(
        "Raw Score",
        f"{raw_score:.1f}/100" if raw_score is not None else "n/a",
        help="Weighted sum of active components (0-100) before percentile ranking.",
    )
    c_top4.metric("Typical Views", format_views(row.get("median_views")), help="Historical median views on non-sponsored uploads.")

    with c_top5:
        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
        # Shortlist button
        current_sl = st.session_state.get("shortlist", [])
        is_in_sl = any(item["channel_id"] == selected_id for item in current_sl)
        if is_in_sl:
            st.button("⭐ Shortlisted", disabled=True, key=f"sl_added_{selected_id}")
        else:
            if st.button("⭐ + Add to Shortlist", type="primary", key=f"sl_add_btn_{selected_id}"):
                st.session_state["shortlist"].append({
                    "channel_id": selected_id,
                    "channel_name": ch_name,
                    "score": pct_score,
                    "tier": tier,
                    "subscribers": int(row.get("subscribers", 0)) if pd.notnull(row.get("subscribers")) else 0,
                })
                st.rerun()

    # Evidence Banner & Dynamic Renormalisation Explanation
    missing_comps = get_missing_components(row)
    active_weight, rescale_factor, renorm_msg = compute_renormalisation(missing_comps)

    if missing_comps:
        st.warning(f"⚠️ **Dynamic Weight Renormalisation**: {renorm_msg}")
    else:
        st.success("✅ **Full Evidence Profile**: All 6 score components available. Standard baseline weights applied without renormalisation.")

    # ── Section 1: Components Radar & Contribution Waterfall ─────────────────
    st.markdown("### 1. Promotion-Potential Component Analysis")

    comp_profile = {
        "Domain Fit": float(row.get("comp_fit", 0.5)),
        "Conversion Evidence": float(row.get("comp_conversion_evidence", 0.5) or 0.0),
        "Real Reach": float(row.get("comp_real_reach", 0.5)),
        "Engagement Quality": float(row.get("comp_engagement_quality", 0.5)),
        "Cadence Momentum": float(row.get("comp_momentum", 0.5)),
        "View Consistency": float(row.get("comp_consistency", 0.5)),
    }

    c_radar, c_waterfall = st.columns([1, 1.1])

    with c_radar:
        st.markdown("##### 6-Factor Normalized Profile (0–100)")
        fig_radar = render_radar_chart(comp_profile)
        st.plotly_chart(fig_radar, use_container_width=True)

    with c_waterfall:
        st.markdown("##### Weighted Points Toward Raw Score")
        # Build exact weighted contribution points
        norm_factor = 100.0 / active_weight
        contributions = []
        for key, base_w in COMPONENT_WEIGHTS.items():
            disp_name = key.replace("comp_", "").replace("_", " ").title()
            val = row.get(key)
            if val is not None and pd.notnull(val):
                pts = round(float(val) * (base_w * norm_factor), 2)
            else:
                pts = 0.0
            contributions.append({"name": disp_name, "points": pts, "type": "positive"})

        # Penalties
        pen_sat = float(row.get("penalty_saturation", 0.0))
        if pen_sat > 0:
            contributions.append({"name": "Sponsor Saturation Penalty", "points": -round(pen_sat, 2), "type": "penalty"})

        pen_comp = float(row.get("penalty_competitor", 0.0))
        if pen_comp > 0:
            contributions.append({"name": "Competitor Brand Penalty", "points": -round(pen_comp, 2), "type": "penalty"})

        fig_waterfall = render_waterfall_chart(contributions)
        st.plotly_chart(fig_waterfall, use_container_width=True)

    # ── Section 2: Sponsorship & Commercial Track Record ─────────────────────
    st.markdown("---")
    st.markdown("### 2. Sponsorship & Commercial Track Record")

    sp_col1, sp_col2, sp_col3, sp_col4 = st.columns(4)
    spons_count = int(row.get("sponsored_count", 0))
    total_videos = int(row.get("video_count", 1))
    organic_count = max(0, total_videos - spons_count)
    spons_rate = float(row.get("sponsored_rate", 0.0)) * 100
    promo_lift = row.get("promo_lift", None)

    sp_col1.metric("Sponsored Videos", f"{spons_count:,}", f"{spons_rate:.1f}% catalog")
    sp_col2.metric("Organic Videos", f"{organic_count:,}")

    has_lift = pd.notnull(promo_lift) and float(promo_lift) > 0
    if has_lift:
        sp_col3.metric("Promo Lift Multiplier", f"{float(promo_lift):.2f}x", "vs organic baseline")
    else:
        sp_col3.metric("Promo Lift Multiplier", "N/A", "insufficient sample")

    sp_col4.metric(
        "Sponsor Saturation",
        f"{spons_rate:.1f}%",
        "-10 pts penalty" if spons_rate > 50.0 else "Optimal (<50%)",
        delta_color="inverse" if spons_rate > 50.0 else "normal",
    )

    # Rule explanation for promo lift
    if not has_lift:
        st.caption(
            f"ℹ️ **Promo Lift Calculation Policy:** Requires at least **3 sponsored and 3 organic videos** in the catalog. "
            f"This channel has {spons_count} sponsored and {organic_count} organic videos, so promo lift is uncalculated."
        )

    # ── Section 3: Audience Health & Consistency Signals ─────────────────────
    st.markdown("---")
    st.markdown("### 3. Audience Health & Consistency Signals")

    h_col1, h_col2, h_col3 = st.columns(3)
    cv_val = float(row.get("view_consistency_cv", 1.0))
    h_col1.metric("View Volatility (CV)", f"{cv_val:.2f}", "lower is more predictable")

    cadence = float(row.get("upload_cadence_days", 7.0))
    h_col2.metric("Upload Cadence", f"{cadence:.1f} days / video")

    age_days = float(row.get("channel_age_days", 365.0))
    h_col3.metric("Channel Longevity", f"{int(age_days / 365.25)} years", f"{int(age_days):,} days")

    # Audience quality / comment enrichment diagnostics
    has_comment_sample = False
    for col in ["duplicate_comment_share", "loyal_commenter_share", "purchase_intent_rate"]:
        if col in row and pd.notnull(row[col]):
            has_comment_sample = True
            break

    if has_comment_sample:
        st.markdown("#### Sampled Audience Authenticity Metrics")
        a1, a2, a3 = st.columns(3)
        a1.metric("Duplicate Comment Share", format_percentage(row.get("duplicate_comment_share", 0.0)))
        a2.metric("Loyal Repeat Commenters", format_percentage(row.get("loyal_commenter_share", 0.0)))
        a3.metric("Purchase Intent Rate", format_percentage(row.get("purchase_intent_rate", 0.0)))
    else:
        st.info("ℹ️ **Audience Authenticity Sampling:** Not sampled (quota-limited). Live comment scraping and sentiment analysis is reserved for shortlisted campaign candidates to preserve daily YouTube API units.")
