"""
src/app/pages_impl/find_influencers.py
Page 1: Find Influencers & Portfolio Budget Allocator.
Enables product brief domain prediction, ranked creator exploration, and greedy knapsack allocation.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.app.components import render_header, render_disclaimer
from src.app.data_loader import load_scored_creators, load_rate_card
from src.app.domain_predictor import DomainPredictor
from src.app.portfolio_optimizer import optimize_portfolio


def render_find_influencers_page() -> None:
    render_header(
        title="Find Influencers & Promotion Ranking",
        subtitle="Match brand product briefs to domain-specialized creators and simulate optimal campaign portfolios.",
        badge="Discovery & Optimization Engine",
    )
    render_disclaimer()

    # Load precomputed gold creators
    creators_df = load_scored_creators()
    rate_card = load_rate_card()
    predictor = DomainPredictor()

    if creators_df.empty:
        st.error("No gold scored creator data found in data/gold/. Please ensure Phase 7 pipeline has executed.")
        return

    # ── Section 1: Product Brief Input & Domain Classifier ────────────────────
    st.subheader("1. Enter Product Description")

    col_input, col_preset = st.columns([3, 1])
    with col_preset:
        preset = st.selectbox(
            "Quick Presets",
            [
                "Custom Input...",
                "Hydrating Hyaluronic Acid Serum (Skincare)",
                "Waterproof Liquid Eyeliner & Mascara (Makeup)",
                "Keratin Repair Hair Mask & Argan Oil (Haircare)",
                "Protein Powder & Muscle Recovery (Fitness)",
            ],
            index=0,
        )

    preset_texts = {
        "Hydrating Hyaluronic Acid Serum (Skincare)": "Ultra-hydrating hyaluronic acid facial serum with niacinamide and SPF 30 sunscreen for daily dry skin restoration.",
        "Waterproof Liquid Eyeliner & Mascara (Makeup)": "Long-wearing waterproof liquid eyeliner and volumizing mascara for smudge-proof glam makeup tutorials.",
        "Keratin Repair Hair Mask & Argan Oil (Haircare)": "Intense restorative keratin hair mask with organic Moroccan argan oil for heat-damaged and color-treated hair.",
        "Protein Powder & Muscle Recovery (Fitness)": "Whey isolate protein powder with BCAAs and electrolytes for post-workout muscle recovery and athletic performance.",
    }

    default_text = preset_texts.get(preset, "Ultra-hydrating daily serum with hyaluronic acid, retinol, and SPF sunscreen.")
    product_brief = col_input.text_area(
        "Product brief / target audience:",
        value=default_text,
        height=90,
        help="Type any product brief. The semantic engine classifies the domain and tailors fit alignment without starting Spark.",
    )

    # Predict domain using fast pure-Python classifier (T-A2: empty/odd text handled)
    domain_result = predictor.predict(product_brief)

    # Domain Result Banner
    st.markdown(
        f"""
        <div style="background: rgba(14, 165, 233, 0.12); border: 1px solid rgba(14, 165, 233, 0.3); border-radius: 12px; padding: 14px 18px; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-size: 0.8rem; text-transform: uppercase; color: #38BDF8; font-weight: 700; letter-spacing: 0.05em;">Predicted Domain</span>
                    <h3 style="margin: 2px 0 0 0; color: #FFFFFF; font-size: 1.3rem;">{domain_result['domain_name']}</h3>
                    <p style="margin: 2px 0 0 0; color: #94A3B8; font-size: 0.88rem;">{domain_result['message']}</p>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 0.8rem; color: #94A3B8;">Model Confidence</span>
                    <div style="font-size: 1.5rem; font-weight: 800; color: #38BDF8;">{int(domain_result['confidence'] * 100)}%</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Section 2: Filters & Ranked Leaderboard ───────────────────────────────
    st.subheader("2. Ranked Creator Leaderboard")

    col_f1, col_f2, col_f3 = st.columns([1, 1, 1])

    available_tiers = sorted(creators_df["size_tier"].unique().tolist())
    selected_tiers = col_f1.multiselect("Filter Size Tiers", available_tiers, default=available_tiers)

    min_score = col_f2.slider("Min Promotion Score", min_value=0, max_value=100, value=20, step=5)

    only_sponsored = col_f3.checkbox("Only creators with sponsor history", value=False)

    # Filter dataframe
    filtered = creators_df[
        (creators_df["size_tier"].isin(selected_tiers))
        & (creators_df["promotion_potential_score"] >= min_score)
    ].copy()

    if only_sponsored and "sponsored_count" in filtered.columns:
        filtered = filtered[filtered["sponsored_count"] > 0]

    # Re-sort descending by promotion potential score
    filtered = filtered.sort_values(by="promotion_potential_score", ascending=False).reset_index(drop=True)

    st.markdown(f"**Found {len(filtered)} eligible creators** matching criteria:")
    st.caption("ℹ️ Creators in the YouNiverse baseline are indexed by their permanent 24-character YouTube Channel ID (`UC...`). Click **Open on YouTube ↗** to view their channel name, profile, and video uploads.")

    # Create clickable YouTube link column
    filtered["channel_url"] = "https://www.youtube.com/channel/" + filtered["channel_id"].astype(str)

    # Prepare display columns
    display_cols = [
        "channel_name",
        "channel_url",
        "channel_id",
        "subscribers",
        "size_tier",
        "promotion_potential_score",
        "median_views",
        "engagement_rate",
        "promo_lift_display",
        "sponsored_count",
        "domain_purity",
        "partial_evidence",
    ]
    existing_disp = [c for c in display_cols if c in filtered.columns]

    rename_map = {
        "channel_name": "Channel Name",
        "channel_url": "YouTube Link",
        "channel_id": "Channel ID",
        "subscribers": "Subscribers",
        "size_tier": "Size Tier",
        "promotion_potential_score": "Promotion Score",
        "median_views": "Median Views",
        "engagement_rate": "Engagement Rate",
        "promo_lift_display": "Promo Lift",
        "sponsored_count": "Sponsored Videos",
        "domain_purity": "Domain Purity",
        "partial_evidence": "Partial Evidence",
    }

    st.dataframe(
        filtered[existing_disp].rename(columns=rename_map),
        column_config={
            "YouTube Link": st.column_config.LinkColumn(
                "YouTube Channel",
                display_text="Open on YouTube ↗",
            ),
        },
        use_container_width=True,
        height=320,
    )

    # CSV Download Button
    csv_bytes = filtered[existing_disp].to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Export Shortlisted Creators (CSV)",
        data=csv_bytes,
        file_name="shortlisted_influencers.csv",
        mime="text/csv",
    )

    # ── Section 3: Interactive Budget Portfolio Simulator ────────────────────
    st.markdown("---")
    st.subheader("3. Budget Portfolio Optimizer (Greedy Knapsack)")
    st.caption("Allocate a target marketing budget across creator tiers to maximize campaign exposure and expected efficiency.")

    p_col1, p_col2 = st.columns([1, 2])
    with p_col1:
        budget = st.number_input("Campaign Budget ($ USD)", min_value=500, max_value=500000, value=15000, step=500)
        max_tier_pct = st.slider("Max Budget Share per Tier", min_value=0.20, max_value=1.00, value=0.50, step=0.05)
        st.write("**CPM Rate Card Used ($/1k views):**")
        for tier, cpm in rate_card.items():
            st.write(f"- {tier}: **${cpm:.0f}**")

    # Run optimizer
    portfolio_res = optimize_portfolio(
        creators_df=filtered,
        budget_usd=float(budget),
        rate_card=rate_card,
        max_tier_share=float(max_tier_pct),
    )

    with p_col2:
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Selected Creators", len(portfolio_res["selected_creators"]))
        kpi2.metric("Total Spend", f"${portfolio_res['total_spent']:,.0f}", delta=f"-${portfolio_res['remaining_budget']:,.0f} left")
        kpi3.metric("Est. Total Reach", f"{portfolio_res['total_estimated_reach']:,} views")
        kpi4.metric("Avg Score", f"{portfolio_res['avg_score']:.1f}/100")

        if portfolio_res["tier_breakdown"]:
            spend_df = pd.DataFrame([
                {"Tier": t, "Spend ($)": s} for t, s in portfolio_res["tier_breakdown"].items()
            ])
            fig_pie = px.pie(
                spend_df,
                names="Tier",
                values="Spend ($)",
                hole=0.45,
                color_discrete_sequence=["#0EA5E9", "#8B5CF6", "#EC4899", "#64748B"],
            )
            fig_pie.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#CBD5E1"),
                margin=dict(l=10, r=10, t=10, b=10),
                height=220,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    if portfolio_res["selected_creators"]:
        st.markdown("**Optimal Campaign Allocation:**")
        alloc_df = pd.DataFrame(portfolio_res["selected_creators"])
        st.dataframe(
            alloc_df.rename(columns={
                "channel_id": "Channel ID",
                "size_tier": "Size Tier",
                "promotion_potential_score": "Score",
                "median_views": "Median Views",
                "est_cost_usd": "Est. Cost ($)",
                "efficiency": "Efficiency (Score/$)",
                "promo_lift": "Promo Lift",
            }),
            use_container_width=True,
        )
