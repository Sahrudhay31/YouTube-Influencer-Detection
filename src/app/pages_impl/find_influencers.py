"""
src/app/pages_impl/find_influencers.py
Page 1: Find Influencers & Portfolio Budget Allocator (InfluencerAI v2).
Enables product brief domain prediction, ranked creator exploration,
side-by-side creator comparison, live YouTube Data API discovery, and greedy knapsack allocation.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.app.components import (
    render_header,
    render_disclaimer,
    render_missing_gold_banner,
    render_compare_radar_chart,
)
from src.app.data_loader import (
    load_scored_creators,
    load_rate_card,
    load_quota_ledger,
)
from src.app.domain_predictor import DomainPredictor
from src.app.evidence import get_evidence_badge
from src.app.formatters import (
    format_subscribers,
    format_views,
    format_percentage,
    format_promo_lift,
    format_currency,
)
from src.app.leaderboard_logic import (
    filter_and_rank_creators,
    paginate_dataframe,
    build_export_csv,
)
from src.app.portfolio_optimizer import optimize_portfolio
from src.app.quota_service import inspect_quota_status, validate_api_action
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
    default_rate_card = load_rate_card()
    predictor = DomainPredictor()

    if creators_df.empty:
        render_missing_gold_banner()
        return

    # ── Section 1: Product Brief Input & Domain Classifier ────────────────────
    st.subheader("1. Enter Product Description")

    col_input, col_preset = st.columns([3, 1])

    presets = [
        "Custom Input...",
        "Hydrating Hyaluronic Acid Serum (Skincare)",
        "Velvet Matte Liquid Lipstick (Makeup)",
        "Clarifying Shampoo for Dry Scalp & Hair (Haircare)",
        "Long-Lasting Gel Nail Polish (Nails)",
        "Warm Vanilla & Amber Eau de Parfum (Fragrance)",
        "Whey Isolate Protein Powder (Fitness Out-of-Domain)",
    ]

    preset_texts = {
        "Hydrating Hyaluronic Acid Serum (Skincare)": "Ultra-hydrating hyaluronic acid facial serum with niacinamide and SPF 30 sunscreen for daily dry skin restoration.",
        "Velvet Matte Liquid Lipstick (Makeup)": "Long-wearing transfer-proof velvet matte liquid lipstick with high pigment for all-day glam makeup looks.",
        "Clarifying Shampoo for Dry Scalp & Hair (Haircare)": "Sulfate-free clarifying shampoo infused with tea tree oil and argan oil for dry scalp relief and hair hydration.",
        "Long-Lasting Gel Nail Polish (Nails)": "Chip-resistant salon-grade UV gel nail polish with high-shine top coat and cuticle oil.",
        "Warm Vanilla & Amber Eau de Parfum (Fragrance)": "Luxurious long-lasting floral gourmand perfume featuring warm vanilla bourbon, amber resin, and jasmine.",
        "Whey Isolate Protein Powder (Fitness Out-of-Domain)": "Whey isolate protein powder with BCAAs and electrolytes for post-workout muscle recovery and gym athletic performance.",
    }

    with col_preset:
        preset_choice = st.selectbox("Quick Presets", presets, index=1)

    default_text = preset_texts.get(preset_choice, "Ultra-hydrating daily serum with hyaluronic acid, retinol, and SPF sunscreen.")
    product_brief = col_input.text_area(
        "Product brief / target audience:",
        value=default_text,
        height=85,
        help="Type any product brief. The semantic engine analyzes domain fit and highlights key lexicon drivers without starting Spark.",
    )

    # Predict domain using fast pure-Python classifier
    domain_result = predictor.predict(product_brief)

    # Out-of-domain warning if applicable
    if domain_result.get("is_outside_beauty", False):
        st.warning(
            f"⚠️ **Out-of-Domain Notice**: This product brief was classified as **{domain_result['domain_name']}** "
            f"({int(domain_result['confidence'] * 100)}% match score). "
            f"Please note that the current ranked creator cohort is specialized exclusively for **Beauty & Personal Care**."
        )

    # Domain Result Banner
    lexicon_chips = "".join([f"<span class='filter-chip'>🏷️ {term}</span>" for term in domain_result.get("top_lexicon_terms", [])])
    alt_domains = domain_result.get("top_alternatives", [])
    alt_text = " | ".join([f"{a['domain_name']} ({a['pct']}%)" for a in alt_domains]) if alt_domains else "None"

    st.markdown(
        f"""
        <div style="background: rgba(14, 165, 233, 0.10); border: 1px solid rgba(14, 165, 233, 0.25); border-radius: 10px; padding: 12px 16px; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px;">
                <div>
                    <span style="font-size: 0.72rem; text-transform: uppercase; color: #38BDF8; font-weight: 700; letter-spacing: 0.05em;">Domain Semantic Classification</span>
                    <h3 style="margin: 2px 0 2px 0; color: #FFFFFF; font-size: 1.25rem;">{domain_result['domain_name']}</h3>
                    <p style="margin: 0; color: #94A3B8; font-size: 0.85rem;">{domain_result['message']}</p>
                    <div style="margin-top: 6px;">
                        <span style="color: #64748B; font-size: 0.78rem; margin-right: 6px;">Key matched lexicon terms:</span>
                        {lexicon_chips if lexicon_chips else "<span style='color: #64748B; font-size: 0.78rem;'>None</span>"}
                    </div>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 0.75rem; color: #94A3B8;">Domain Match Score</span>
                    <div style="font-size: 1.6rem; font-weight: 800; color: #38BDF8;">{int(domain_result['confidence'] * 100)}%</div>
                    <span style="font-size: 0.72rem; color: #64748B;">Alt: {alt_text}</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Section 2: Tabs ───────────────────────────────────────────────────────
    tab_offline, tab_live = st.tabs([
        "📚 Offline YouNiverse Cohort (2,615 Scored Channels)",
        "🔴 Live YouTube API Discovery",
    ])

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 1: Offline Leaderboard & Portfolio Optimizer
    # ═════════════════════════════════════════════════════════════════════════
    with tab_offline:
        st.subheader("Ranked Creator Leaderboard")

        # ── Filters Bar ───────────────────────────────────────────────────────
        with st.expander("🔍 Search & Filter Options", expanded=True):
            f_col1, f_col2, f_col3, f_col4 = st.columns([1.5, 1.2, 1, 1])

            search_query = f_col1.text_input(
                "Search Channel Name / ID",
                value="",
                placeholder="e.g. Kylie, Andrea, Vogue...",
                help="Filter by human-readable channel name or 24-character ID.",
            )

            all_tiers = ["Nano", "Micro", "Mid", "Macro", "Mega"]
            available_tiers = [t for t in all_tiers if t in creators_df["size_tier"].unique().tolist()] or all_tiers
            selected_tiers = f_col2.multiselect("Filter Size Tiers", available_tiers, default=available_tiers)

            min_score = f_col3.slider(
                "Min Promotion Score",
                min_value=0,
                max_value=100,
                value=0,
                step=5,
                help="Percentile rank threshold (0-100) within domain x tier.",
            )

            min_eng = f_col4.slider(
                "Min Engagement Rate (%)",
                min_value=0.0,
                max_value=15.0,
                value=0.0,
                step=0.5,
                help="Minimum engagement rate (likes + comments ÷ views).",
            )

            f2_col1, f2_col2, f2_col3, f2_col4 = st.columns([1, 1, 1, 1])

            rank_full_first = f2_col1.toggle(
                "Rank full-evidence first",
                value=True,
                help="Score is a percentile rank within domain and size tier, not an absolute quality rating. Ties at 100 are broken by full-evidence priority and secondary raw scores.",
            )

            full_evidence_only = f2_col2.checkbox("Full evidence only", value=False, help="Exclude channels with missing components.")
            only_sponsored = f2_col3.checkbox("Only sponsored history", value=False, help="Show only creators with sponsored_count > 0.")

            # Reset filters button
            if f2_col4.button("🔄 Reset Filters", help="Reset all filters to defaults"):
                st.session_state["reset_filters_trigger"] = True
                st.rerun()

        # Execute pure filtering & ranking
        filtered = filter_and_rank_creators(
            df=creators_df,
            search_query=search_query,
            selected_tiers=selected_tiers,
            min_score=float(min_score),
            min_engagement_pct=float(min_eng),
            full_evidence_only=full_evidence_only,
            only_sponsored=only_sponsored,
            rank_full_evidence_first=rank_full_first,
        )

        st.markdown(
            f"**Showing {len(filtered):,} eligible beauty creators** "
            f"(Sorted by: {'Full Evidence Priority → ' if rank_full_first else ''}Percentile Rank → Secondary Raw Score)"
        )

        # ── Compare Feature (Side-by-side Radar & Table) ──────────────────────
        with st.expander("⚖️ Compare Creators Side-by-Side (Select 2–4 Creators)", expanded=False):
            compare_options = filtered["channel_name"].tolist() if not filtered.empty else []
            selected_to_compare = st.multiselect(
                "Select 2 to 4 creators to compare across components:",
                compare_options,
                max_selections=4,
                help="Select between 2 and 4 creators from the filtered list to visualize comparative score radar and metrics.",
            )

            if len(selected_to_compare) >= 2:
                comp_records = []
                comp_creators = []
                for ch_name in selected_to_compare:
                    c_row = filtered[filtered["channel_name"] == ch_name].iloc[0]
                    comp_profile = {
                        "Fit": float(c_row.get("comp_fit", 0.5)),
                        "Conversion": float(c_row.get("comp_conversion_evidence", 0.5) or 0.3),
                        "Real Reach": float(c_row.get("comp_real_reach", 0.5)),
                        "Engagement": float(c_row.get("comp_engagement_quality", 0.5)),
                        "Momentum": float(c_row.get("comp_momentum", 0.5)),
                        "Consistency": float(c_row.get("comp_consistency", 0.5)),
                    }
                    comp_creators.append({"name": ch_name, "components": comp_profile})
                    comp_records.append({
                        "Channel": ch_name,
                        "Size Tier": c_row.get("size_tier", "Micro"),
                        "Percentile Score": f"{c_row.get('promotion_potential_score', 0):.1f}",
                        "Raw Score": f"{c_row.get('raw_score', 0):.1f}" if pd.notnull(c_row.get('raw_score')) else "n/a",
                        "Subscribers": format_subscribers(c_row.get("subscribers")),
                        "Median Views": format_views(c_row.get("median_views")),
                        "Engagement Rate": format_percentage(c_row.get("engagement_rate")),
                        "Promo Lift": format_promo_lift(c_row.get("promo_lift")),
                        "Evidence": "Partial" if c_row.get("partial_evidence", False) else "High (Full)",
                    })

                col_cmp1, col_cmp2 = st.columns([1.2, 1])
                with col_cmp1:
                    fig_cmp = render_compare_radar_chart(comp_creators)
                    st.plotly_chart(fig_cmp, use_container_width=True)
                with col_cmp2:
                    st.dataframe(pd.DataFrame(comp_records), use_container_width=True, hide_index=True)
            elif selected_to_compare:
                st.info("Select at least 2 creators to generate comparative radar overlay.")

        # ── Quick Action / Creator Inspection ────────────────────────────────
        c_act1, c_act2, c_act3 = st.columns([2, 1, 1])
        with c_act1:
            creator_names = filtered["channel_name"].tolist() if not filtered.empty else []
            inspect_target = st.selectbox(
                "Select Creator to Inspect in Creator Card:",
                creator_names,
                index=0 if creator_names else None,
                help="Choose a creator and click 'Deep-Dive Card' to jump directly to the Creator Card page.",
            )
        with c_act2:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("👤 View Creator Card", type="secondary", disabled=not bool(inspect_target)):
                target_row = filtered[filtered["channel_name"] == inspect_target].iloc[0]
                st.session_state["selected_creator_id"] = target_row["channel_id"]
                st.session_state["jump_to_card"] = True
                st.rerun()
        with c_act3:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if st.button("⭐ + Shortlist", type="primary", disabled=not bool(inspect_target)):
                target_row = filtered[filtered["channel_name"] == inspect_target].iloc[0]
                ch_id = target_row["channel_id"]
                # Prevent duplicate addition
                current_sl = st.session_state.get("shortlist", [])
                if not any(item["channel_id"] == ch_id for item in current_sl):
                    st.session_state["shortlist"].append({
                        "channel_id": ch_id,
                        "channel_name": target_row.get("channel_name", ch_id),
                        "score": float(target_row.get("promotion_potential_score", 0.0)),
                        "tier": target_row.get("size_tier", ""),
                        "subscribers": int(target_row.get("subscribers", 0)) if pd.notnull(target_row.get("subscribers")) else 0,
                    })
                    st.success(f"Added {inspect_target} to shortlist!")
                    st.rerun()
                else:
                    st.info(f"{inspect_target} is already in your shortlist.")

        # ── Pagination Controls ───────────────────────────────────────────────
        pg_col1, pg_col2, pg_col3 = st.columns([1, 1, 2])
        page_size = pg_col1.selectbox("Creators per Page", [25, 50, 100], index=0)
        total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
        page_num = pg_col2.number_input(f"Page (of {total_pages})", min_value=1, max_value=total_pages, value=1, step=1)

        paged_df, total_rows, _ = paginate_dataframe(filtered, page_number=int(page_num), page_size=int(page_size))

        # Format display columns
        display_df = paged_df.copy()
        display_df["channel_url"] = "https://www.youtube.com/channel/" + display_df["channel_id"].astype(str)
        display_df["evidence_badge"] = display_df["partial_evidence"].apply(
            lambda p: "⚠️ Partial" if p else "✅ High"
        )
        display_df["subscribers_fmt"] = display_df["subscribers"].apply(format_subscribers)
        display_df["views_fmt"] = display_df["median_views"].apply(format_views)
        display_df["engagement_fmt"] = display_df["engagement_rate"].apply(format_percentage)
        display_df["lift_fmt"] = display_df["promo_lift"].apply(format_promo_lift)

        table_cols = [
            "channel_name",
            "size_tier",
            "evidence_badge",
            "promotion_potential_score",
            "raw_score",
            "subscribers_fmt",
            "views_fmt",
            "engagement_fmt",
            "lift_fmt",
            "sponsored_count",
            "channel_url",
            "channel_id",
        ]
        available_table_cols = [c for c in table_cols if c in display_df.columns]

        st.dataframe(
            display_df[available_table_cols].rename(columns={
                "channel_name": "Channel Name",
                "size_tier": "Size Tier",
                "evidence_badge": "Evidence",
                "promotion_potential_score": "Promotion Score",
                "raw_score": "Raw Score (0-100)",
                "subscribers_fmt": "Subscribers",
                "views_fmt": "Median Views",
                "engagement_fmt": "Engagement Rate",
                "lift_fmt": "Promo Lift",
                "sponsored_count": "Sponsored Videos",
                "channel_url": "YouTube Link",
                "channel_id": "Channel ID",
            }),
            column_config={
                "Channel Name": st.column_config.TextColumn("Channel Name", pinned=True, width="medium"),
                "Promotion Score": st.column_config.ProgressColumn(
                    "Promotion Score",
                    help="Percentile rank within domain x size tier (0-100).",
                    format="%.1f",
                    min_value=0.0,
                    max_value=100.0,
                    width="small",
                ),
                "Raw Score (0-100)": st.column_config.NumberColumn(
                    "Raw Score",
                    help="Weighted component score before percentile normalisation.",
                    format="%.1f",
                    width="small",
                ),
                "YouTube Link": st.column_config.LinkColumn(
                    "YouTube Link",
                    display_text="Open Channel ↗",
                    width="small",
                ),
                "Evidence": st.column_config.TextColumn(
                    "Evidence",
                    help="High = All 6 components measured directly; Partial = Missing streams rescaled to 100%.",
                    width="small",
                ),
                "Size Tier": st.column_config.TextColumn("Size Tier", width="small"),
                "Subscribers": st.column_config.TextColumn("Subscribers", width="small"),
                "Median Views": st.column_config.TextColumn("Median Views", width="small"),
                "Engagement Rate": st.column_config.TextColumn("Engagement Rate", width="small"),
                "Promo Lift": st.column_config.TextColumn("Promo Lift", width="small"),
                "Sponsored Videos": st.column_config.NumberColumn("Sponsored Videos", format="%d", width="small"),
            },
            hide_index=True,
            use_container_width=True,
            height=380,
        )

        # CSV Download Button with Disclaimer
        csv_export_str = build_export_csv(filtered)
        st.download_button(
            label=f"📥 Export Filtered Creators ({len(filtered):,} rows CSV)",
            data=csv_export_str.encode("utf-8"),
            file_name="filtered_beauty_influencers.csv",
            mime="text/csv",
        )

        # ── Budget Portfolio Allocator Section ────────────────────────────────
        st.markdown("---")
        st.subheader("Budget Portfolio Allocator (Greedy Knapsack)")
        st.caption("Allocate campaign budget to maximize total exposure across size tiers. Cost estimates use industry benchmark rate cards.")

        with st.expander("⚙️ Configure Rate Card & Overheads (Session Overrides)", expanded=False):
            st.info("ℹ️ **Default rates are placeholder industry benchmarks, not real quotes.** Customize CPM and overhead for this session.")
            rc_col1, rc_col2 = st.columns(2)
            custom_rate_card = {}
            for idx, (tier_name, rates) in enumerate(default_rate_card.items()):
                target_col = rc_col1 if idx % 2 == 0 else rc_col2
                with target_col:
                    st.markdown(f"**{tier_name} Tier**")
                    c_cpm, c_ovh = st.columns(2)
                    cpm_val = c_cpm.number_input(f"{tier_name} CPM ($)", min_value=1.0, max_value=500.0, value=float(rates["cpm"]), step=1.0, key=f"cpm_{tier_name}")
                    ovh_val = c_ovh.number_input(f"{tier_name} Overhead ($)", min_value=0.0, max_value=2000.0, value=float(rates["overhead"]), step=25.0, key=f"ovh_{tier_name}")
                    custom_rate_card[tier_name] = {"cpm": cpm_val, "overhead": ovh_val}

        p_input1, p_input2, p_input3 = st.columns(3)
        with p_input1:
            budget = st.number_input("Campaign Budget ($ USD)", min_value=500, max_value=1000000, value=15000, step=1000)
        with p_input2:
            max_share = st.slider("Max Budget Share per Tier", min_value=0.20, max_value=1.00, value=0.50, step=0.05, help="Prevents over-concentration in a single tier.")
        with p_input3:
            max_creators_count = st.number_input("Max Creators to Select", min_value=1, max_value=100, value=25, step=1)

        # Run portfolio optimizer
        portfolio_res = optimize_portfolio(
            creators_df=filtered,
            budget_usd=float(budget),
            rate_card=custom_rate_card,
            max_tier_share=float(max_share),
            max_creators=int(max_creators_count),
        )

        # Results KPI summary
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Selected Creators", len(portfolio_res["selected_creators"]))
        k2.metric("Total Spend", format_currency(portfolio_res["total_spent"]), delta=f"-{format_currency(portfolio_res['remaining_budget'])} left", delta_color="normal")
        k3.metric("Total Typical Views", format_views(portfolio_res["total_typical_views"]), help="Sum of historical median views on non-sponsored uploads. Typical views, NOT predicted sales/ROI.")
        k4.metric("Avg Promotion Score", f"{portfolio_res['avg_score']:.1f}/100")

        # Visual Spend Progress
        spend_pct = min(1.0, portfolio_res["total_spent"] / max(1.0, float(budget)))
        st.progress(spend_pct, text=f"Budget Utilized: {spend_pct*100:.1f}% ({format_currency(portfolio_res['total_spent'])} of {format_currency(budget)})")

        if portfolio_res["selected_creators"]:
            st.markdown("#### Optimal Campaign Allocation Portfolio:")
            alloc_df = pd.DataFrame(portfolio_res["selected_creators"])
            st.dataframe(
                alloc_df.rename(columns={
                    "channel_name": "Channel Name",
                    "channel_id": "Channel ID",
                    "size_tier": "Size Tier",
                    "promotion_potential_score": "Score",
                    "raw_score": "Raw Score",
                    "median_views": "Typical Views",
                    "est_cost_usd": "Est. Cost ($)",
                    "efficiency": "Efficiency (Score/$)",
                    "promo_lift": "Promo Lift",
                }),
                hide_index=True,
                use_container_width=True,
            )

    # ═════════════════════════════════════════════════════════════════════════
    # TAB 2: Live YouTube API Discovery
    # ═════════════════════════════════════════════════════════════════════════
    with tab_live:
        st.subheader("🔴 Live Creator Discovery (YouTube Data API v3)")

        # Mandatory Governance Banner
        st.markdown(
            """
            <div style="background: rgba(56, 189, 248, 0.08); border-left: 3px solid #38BDF8; border-radius: 6px; padding: 10px 14px; margin-bottom: 16px; color: #E2E8F0; font-size: 0.88rem;">
                <strong>ℹ️ Live Discovery Architecture Notice:</strong>
                All reported model and backtest results come from YouNiverse (2019).
                Live results are exploratory and unscored by the backtested pipeline.
                Live candidate discovery utilizes YouTube Data API v3 via single-entrypoint architecture protected by QuotaGuard.
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Quota Telemetry Panel
        ledger_data = load_quota_ledger()
        quota_status = inspect_quota_status(ledger=ledger_data)

        st.markdown("#### YouTube API Daily Quota Status (Pacific Ledger)")
        q1, q2, q3, q4 = st.columns(4)
        q1.metric("Units Used Today", f"{quota_status['units_used']:,} / {quota_status['daily_unit_cap']:,}", f"{quota_status['pct_used']}% used")
        q2.metric("Remaining Units", f"{quota_status['remaining_units']:,} units")
        q3.metric("Search Calls Today", f"{quota_status['search_used']} / {quota_status['search_list_cap']}", f"{quota_status['remaining_searches']} left")
        q4.metric("Midnight Reset", quota_status["time_to_reset"], help="Next Pacific Midnight rollover (America/Los_Angeles)")

        # Mode Selection & Query Controls
        st.markdown("---")
        l_col1, l_col2, l_col3 = st.columns([2, 1, 1])

        live_query = l_col1.text_input(
            "Live Search Query:",
            value=product_brief,
            help="Custom query or derived brief for YouTube search.",
        )

        # Default mode MUST BE Dry Run
        api_mode = l_col2.selectbox(
            "API Mode:",
            ["Dry Run (0 units)", "Live Mode (YouTube API)"],
            index=0,
            help="Dry run simulates API calls with 0 quota consumed. Live mode queries the official YouTube Data API.",
        )

        per_run_limit = l_col3.slider(
            "Per-Run Limit (Units):",
            min_value=50,
            max_value=1500,
            value=150,
            step=50,
            help="Strict per-run safety ceiling (max allowed: 1,500 units).",
        )

        # Cost Breakdown Preview
        planned_queries = build_search_queries(live_query, max_queries=1)
        planned_q = planned_queries[0] if planned_queries else live_query
        # 1 search.list call (100 units) + 1 batch channels.list call (1 unit for up to 50 channels)
        est_cost_units = 101

        st.markdown(
            f"""
            <div style="background: rgba(30, 41, 59, 0.4); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 0.85rem; color: #94A3B8;">
                <strong>Planned Action:</strong> 1x <code>search.list</code> (100 units) + 1x <code>channels.list</code> (1 unit)<br>
                <strong>Target Query:</strong> <code>"{planned_q}"</code><br>
                <strong>Estimated Cost:</strong> <strong style="color: #38BDF8;">{est_cost_units} units</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Explicit Confirmation Step for Live Mode
        is_live_selected = (api_mode == "Live Mode (YouTube API)")
        confirmed_live = False
        if is_live_selected:
            confirmed_live = st.checkbox(
                "⚠️ I confirm execution of a LIVE YouTube API query and authorize quota unit deduction from the Pacific ledger.",
                value=False,
                help="Confirmation is mandatory before live network requests are issued.",
            )

        # Validate action
        is_action_allowed, reason = validate_api_action(
            mode=api_mode,
            estimated_units=est_cost_units,
            confirmed_live=confirmed_live,
            quota_status=quota_status,
            requires_search=True,
        )

        if not is_action_allowed:
            st.info(f"🔒 {reason}")

        if st.button("🚀 Discover YouTube Influencers", type="primary", disabled=not is_action_allowed):
            mode_str = "live" if is_live_selected else "dry_run"
            with st.spinner(f"Executing YouTube Discovery ({mode_str.upper()})..."):
                yt = YouTubeClient(mode=mode_str, per_run_max=per_run_limit)
                if is_live_selected:
                    df_live = discover_live_candidates(
                        product_brief=live_query,
                        yt_client=yt,
                        max_search_calls=1,
                        max_results_per_call=25,
                    )
                else:
                    df_live = pd.DataFrame()
                    st.info(f"✅ DRY RUN completed: 0 network calls issued, 0 quota units consumed. Estimated units for live execution: {est_cost_units}.")

            if not df_live.empty:
                # Add live tag to ensure results are never mixed without identification
                df_live["data_source"] = "LIVE_DISCOVERY_EXPLORATORY"
                df_live["channel_url"] = "https://www.youtube.com/channel/" + df_live["channel_id"].astype(str)

                st.success(f"Discovered **{len(df_live)} live channels** via YouTube Data API v3! Actual units charged to ledger: **{yt.quota.units_used} units**.")

                disp_cols = [
                    "channel_name",
                    "channel_url",
                    "subscribers",
                    "size_tier",
                    "topical_focus",
                    "total_views",
                    "video_count",
                    "channel_id",
                    "data_source",
                ]
                existing_live = [c for c in disp_cols if c in df_live.columns]

                st.dataframe(
                    df_live[existing_live].rename(columns={
                        "channel_name": "Channel Name",
                        "channel_url": "YouTube Link",
                        "subscribers": "Subscribers",
                        "size_tier": "Size Tier",
                        "topical_focus": "Topical Beauty Focus",
                        "total_views": "Total Views",
                        "video_count": "Total Videos",
                        "channel_id": "Channel ID",
                        "data_source": "Source Tag",
                    }),
                    column_config={
                        "YouTube Link": st.column_config.LinkColumn("YouTube Channel", display_text="Open on YouTube ↗"),
                        "Topical Beauty Focus": st.column_config.ProgressColumn("Topical Focus", min_value=0.0, max_value=1.0, format="%.2f"),
                    },
                    hide_index=True,
                    use_container_width=True,
                )
            elif is_live_selected:
                st.warning("No live creators returned or search query returned empty catalog.")
