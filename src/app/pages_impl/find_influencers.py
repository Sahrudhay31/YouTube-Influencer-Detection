"""
src/app/pages_impl/find_influencers.py
Page 1: Find Influencers & Portfolio Budget Allocator.
Enables product brief domain prediction, ranked creator exploration,
live YouTube Data API v3 candidate discovery, and greedy knapsack allocation.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.app.components import render_header, render_disclaimer
from src.app.data_loader import load_scored_creators, load_rate_card
from src.app.domain_predictor import DomainPredictor
from src.app.portfolio_optimizer import optimize_portfolio
from src.discovery.candidate_discovery import discover_live_candidates
from src.discovery.query_builder import build_search_queries
from src.enrichment.youtube_client import YouTubeClient


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
        st.error("No gold scored creator data found in data/gold/. Please ensure gold data has been generated.")
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

    # Predict domain using fast pure-Python classifier
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

    # ── Section 2: Creator Cohort vs Live YouTube API Discovery Tabs ──────────
    tab_offline, tab_live = st.tabs([
        "📚 Offline YouNiverse Cohort (2,615 Scored Channels)",
        "🔴 Live YouTube API Discovery (Real-Time Search)",
    ])

    with tab_offline:
        st.subheader("Ranked Creator Leaderboard")

        col_f1, col_f2, col_f3, col_f4 = st.columns([1.5, 1, 1, 1])

        search_query = col_f1.text_input(
            "Search Channel Name",
            value="",
            placeholder="e.g. Kylie, Andrea, Vogue, James...",
            help="Filter creators by human-readable channel name.",
        )

        available_tiers = sorted(creators_df["size_tier"].unique().tolist())
        selected_tiers = col_f2.multiselect("Filter Size Tiers", available_tiers, default=available_tiers)

        min_score = col_f3.slider("Min Promotion Score", min_value=0, max_value=100, value=20, step=5)

        only_sponsored = col_f4.checkbox("Only sponsored history", value=False)

        # Filter dataframe
        filtered = creators_df[
            (creators_df["size_tier"].isin(selected_tiers))
            & (creators_df["promotion_potential_score"] >= min_score)
        ].copy()

        if search_query.strip():
            filtered = filtered[
                filtered["channel_name"].str.contains(search_query.strip(), case=False, na=False)
            ]

        if only_sponsored and "sponsored_count" in filtered.columns:
            filtered = filtered[filtered["sponsored_count"] > 0]

        # Re-sort descending by promotion potential score
        filtered = filtered.sort_values(by="promotion_potential_score", ascending=False).reset_index(drop=True)

        st.markdown(f"**Showing {len(filtered):,} eligible beauty creators** with human-readable channel names and verified subscriber counts:")

        # Create clickable YouTube link column
        filtered["channel_url"] = "https://www.youtube.com/channel/" + filtered["channel_id"].astype(str)

        # Prepare display columns
        display_cols = [
            "channel_name",
            "channel_url",
            "subscribers",
            "size_tier",
            "promotion_potential_score",
            "median_views",
            "engagement_rate",
            "promo_lift_display",
            "sponsored_count",
            "domain_purity",
            "channel_id",
            "partial_evidence",
        ]
        existing_disp = [c for c in display_cols if c in filtered.columns]

        rename_map = {
            "channel_name": "Channel Name",
            "channel_url": "YouTube Link",
            "subscribers": "Subscribers",
            "size_tier": "Size Tier",
            "promotion_potential_score": "Promotion Score",
            "median_views": "Median Views",
            "engagement_rate": "Engagement Rate",
            "promo_lift_display": "Promo Lift",
            "sponsored_count": "Sponsored Videos",
            "domain_purity": "Domain Purity",
            "channel_id": "Channel ID",
            "partial_evidence": "Partial Evidence",
        }

        st.dataframe(
            filtered[existing_disp].rename(columns=rename_map),
            column_config={
                "YouTube Link": st.column_config.LinkColumn(
                    "YouTube Channel",
                    display_text="Open on YouTube ↗",
                ),
                "Subscribers": st.column_config.NumberColumn(
                    "Subscribers",
                    format="%d",
                ),
            },
            use_container_width=True,
            height=340,
        )

        # CSV Download Button
        csv_bytes = filtered[existing_disp].to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export Shortlisted Creators (CSV)",
            data=csv_bytes,
            file_name="shortlisted_beauty_influencers.csv",
            mime="text/csv",
        )

        # ── Budget Portfolio Simulator ─────────────────────────────────────────
        st.markdown("---")
        st.subheader("Budget Portfolio Optimizer (Greedy Knapsack)")
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
                    color_discrete_sequence=["#0EA5E9", "#8B5CF6", "#EC4899", "#64748B", "#10B981"],
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
                    "channel_name": "Channel Name",
                    "channel_id": "Channel ID",
                    "subscribers": "Subscribers",
                    "size_tier": "Size Tier",
                    "promotion_potential_score": "Score",
                    "median_views": "Median Views",
                    "est_cost_usd": "Est. Cost ($)",
                    "efficiency": "Efficiency (Score/$)",
                    "promo_lift": "Promo Lift",
                }),
                use_container_width=True,
            )

    # ── TAB 2: Live YouTube API Discovery ─────────────────────────────────────
    with tab_live:
        st.subheader("🔴 Live Creator Discovery (YouTube Data API v3)")
        st.markdown(
            """
            Search YouTube live to discover active beauty creators matching your product brief.
            All calls are protected by the **Pacific Time Quota Ledger** and single-entrypoint architecture.
            """
        )

        c_api1, c_api2, c_api3 = st.columns([2, 1, 1])

        live_query = c_api1.text_input(
            "Live Search Query:",
            value=product_brief,
            help="Custom query or automatic query derived from product brief.",
        )

        exec_mode = c_api2.selectbox(
            "API Mode:",
            ["Dry Run (0 units)", "Live Mode (YouTube API)"],
            index=1,
            help="Dry run simulates the call with zero quota consumed. Live mode queries the official YouTube Data API v3.",
        )

        max_quota = c_api3.slider(
            "Quota Cap (Units):",
            min_value=50,
            max_value=500,
            value=150,
            step=50,
            help="Safety threshold for this discovery run.",
        )

        # Plan preview
        planned_queries = build_search_queries(live_query, max_queries=1)
        est_cost = len(planned_queries) * 100 + 1
        st.caption(f"ℹ️ Planned search queries: `'{planned_queries[0]}'` | Estimated Quota: **{est_cost} units** (100 search + 1 channel stats)")

        if st.button("🚀 Discover Live Beauty Influencers", type="primary"):
            is_live = (exec_mode == "Live Mode (YouTube API)")
            mode_str = "live" if is_live else "dry_run"

            with st.spinner(f"Querying YouTube Data API ({mode_str.upper()})..."):
                yt = YouTubeClient(mode=mode_str, per_run_max=max_quota)
                if is_live:
                    df_live = discover_live_candidates(
                        product_brief=live_query,
                        yt_client=yt,
                        max_search_calls=1,
                        max_results_per_call=25,
                    )
                else:
                    df_live = pd.DataFrame()
                    st.info(f"DRY RUN completed successfully: 0 network calls made, 0 quota units consumed. Estimated units for live run: {est_cost}.")

            if not df_live.empty:
                st.success(f"Discovered **{len(df_live)} live YouTube channels** via YouTube Data API v3! Quota used: **{yt.quota.units_used} units**.")

                df_live["channel_url"] = "https://www.youtube.com/channel/" + df_live["channel_id"].astype(str)

                disp_cols = [
                    "channel_name",
                    "channel_url",
                    "subscribers",
                    "size_tier",
                    "topical_focus",
                    "promotion_potential_score",
                    "total_views",
                    "video_count",
                    "channel_id",
                ]
                existing_live = [c for c in disp_cols if c in df_live.columns]

                st.dataframe(
                    df_live[existing_live].rename(columns={
                        "channel_name": "Channel Name",
                        "channel_url": "YouTube Link",
                        "subscribers": "Subscribers",
                        "size_tier": "Size Tier",
                        "topical_focus": "Topical Beauty Focus",
                        "promotion_potential_score": "Promotion Score",
                        "total_views": "Total Views",
                        "video_count": "Total Videos",
                        "channel_id": "Channel ID",
                    }),
                    column_config={
                        "YouTube Link": st.column_config.LinkColumn(
                            "YouTube Channel",
                            display_text="Open on YouTube ↗",
                        ),
                        "Subscribers": st.column_config.NumberColumn(
                            "Subscribers",
                            format="%d",
                        ),
                        "Topical Beauty Focus": st.column_config.ProgressColumn(
                            "Topical Focus",
                            min_value=0.0,
                            max_value=1.0,
                            format="%.2f",
                        ),
                    },
                    use_container_width=True,
                    height=360,
                )

                # Show creator summary cards
                st.markdown("#### Live Discovered Creator Highlights")
                card_cols = st.columns(3)
                for i, (_, creator) in enumerate(df_live.head(6).iterrows()):
                    col_idx = i % 3
                    with card_cols[col_idx]:
                        thumb = creator.get("thumbnail_url")
                        img_html = f"<img src='{thumb}' style='width: 48px; height: 48px; border-radius: 50%; float: left; margin-right: 12px;' />" if thumb else ""
                        st.markdown(
                            f"""
                            <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 10px; padding: 12px; margin-bottom: 12px; min-height: 110px;">
                                {img_html}
                                <div style="overflow: hidden;">
                                    <div style="font-weight: 700; color: #FFFFFF; font-size: 1.05rem;">{creator['channel_name']}</div>
                                    <div style="color: #38BDF8; font-size: 0.85rem; font-weight: 600;">{creator.get('subscribers', 0):,} subs &bull; {creator.get('size_tier', 'Micro')}</div>
                                    <div style="color: #94A3B8; font-size: 0.8rem; margin-top: 4px;">Topical Focus: {int(creator.get('topical_focus', 0)*100)}% &bull; Score: <strong>{creator.get('promotion_potential_score', 0):.1f}</strong></div>
                                    <a href="{creator['channel_url']}" target="_blank" style="color: #0EA5E9; font-size: 0.82rem; text-decoration: none; font-weight: 600; display: inline-block; margin-top: 4px;">Visit Channel ↗</a>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
            elif is_live:
                st.warning("No creators returned or quota limit reached.")
