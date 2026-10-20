import os
import time
import html
import re
import difflib
from datetime import datetime, timezone
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Influencer Sponsorship Intelligence · Promotion Analytics",
    page_icon="🌟",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- MODERN DARK CSS ---
st.markdown("""
<style>
    /* Header banner */
    .hero-banner {
        background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 50%, #DB2777 100%);
        border-radius: 16px;
        padding: 24px 32px;
        margin-bottom: 20px;
        color: white;
        box-shadow: 0 10px 25px rgba(79, 70, 229, 0.25);
    }
    .hero-banner h1 { margin: 0; font-size: 2.1rem; font-weight: 800; letter-spacing: -0.5px; }
    .hero-banner p { margin: 6px 0 0 0; opacity: 0.9; font-size: 1.0rem; }

    /* Live pulse indicator */
    .pulse-live {
        display: inline-flex; align-items: center; gap: 6px;
        background: rgba(16,185,129,0.18); border: 1px solid #10B981;
        border-radius: 20px; padding: 4px 14px; font-size: 0.8rem;
        color: #10B981; font-weight: 700;
    }
    .pulse-live::before {
        content: ''; width: 8px; height: 8px; border-radius: 50%;
        background: #10B981; box-shadow: 0 0 8px #10B981;
        animation: blink 1.4s infinite;
    }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }

    /* Aspect sentiment badges */
    .asp-pos {
        background: rgba(16,185,129,0.18); color: #10B981; border: 1px solid #10B981;
        border-radius: 6px; padding: 3px 9px; font-weight: 600; font-size: 0.82rem;
        display: inline-block; margin: 2px 3px;
    }
    .asp-neg {
        background: rgba(239,68,68,0.18); color: #EF4444; border: 1px solid #EF4444;
        border-radius: 6px; padding: 3px 9px; font-weight: 600; font-size: 0.82rem;
        display: inline-block; margin: 2px 3px;
    }

    /* Query search and score card styles */
    .query-score-box {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.98) 100%);
        border: 1px solid rgba(139, 92, 246, 0.45);
        border-radius: 14px;
        padding: 20px 24px;
        margin: 16px 0 20px 0;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
    }
    .score-badge-pos {
        background: rgba(16, 185, 129, 0.2);
        color: #10B981;
        border: 1px solid #10B981;
        padding: 6px 16px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 0.92rem;
    }
    .score-badge-neg {
        background: rgba(239, 68, 68, 0.2);
        color: #EF4444;
        border: 1px solid #EF4444;
        padding: 6px 16px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 0.92rem;
    }
    .score-badge-neutral {
        background: rgba(148, 163, 184, 0.2);
        color: #94A3B8;
        border: 1px solid #94A3B8;
        padding: 6px 16px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 0.92rem;
    }
    .sentiment-meter {
        height: 14px;
        border-radius: 7px;
        display: flex;
        overflow: hidden;
        margin: 14px 0 10px 0;
        background: #334155;
    }
    .meter-pos { background: #10B981; }
    .meter-neu { background: #64748B; }
    .meter-neg { background: #EF4444; }

    .comment-card {
        background: #1E293B;
        border-radius: 10px;
        padding: 15px 18px;
        margin-bottom: 12px;
        border-left: 4px solid #6366F1;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .comment-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0,0,0,0.3);
    }
    .comment-card-pos { border-left-color: #10B981; }
    .comment-card-neg { border-left-color: #EF4444; }
    .comment-card-neu { border-left-color: #94A3B8; }
    .comment-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 0.82rem;
        color: #94A3B8;
        margin-bottom: 8px;
    }
    .comment-text {
        font-size: 0.95rem;
        color: #F1F5F9;
        line-height: 1.5;
    }
    .highlight {
        background-color: rgba(234, 179, 8, 0.35);
        color: #FDE047;
        padding: 1px 5px;
        border-radius: 4px;
        font-weight: 600;
    }

    /* Section headers */
    .section-title {
        font-size: 1.2rem; font-weight: 700; color: #E2E8F0;
        border-left: 4px solid #8B5CF6; padding-left: 12px; margin: 18px 0 8px 0;
    }
</style>
""", unsafe_allow_html=True)

# ======================================================
# INFLUENCER CATEGORIES & TAXONOMY
# ======================================================
INFLUENCER_TAXONOMY = {
    "Tech_Creators": {
        "label": "💻 Tech Creators",
        "influencers": ["MKBHD", "Mrwhosetheboss", "Linus Tech Tips", "Dave2D", "Unbox Therapy"],
        "brands": ["dbrand", "Casetify", "Ridge Wallet", "Humane AI Pin", "Raycon", "Anker"]
    },
    "Beauty_Lifestyle": {
        "label": "💄 Beauty & Lifestyle",
        "influencers": ["Mikayla Nogueira", "Jeffree Star", "Alix Earle", "Emma Chamberlain", "James Charles"],
        "brands": ["L'Oreal", "Bloom Nutrition", "Tarte", "Sephora", "Chamberlain Coffee"]
    },
    "Fitness_Health": {
        "label": "🏋️ Fitness & Health",
        "influencers": ["Andrew Huberman", "Liver King", "Chris Bumstead", "Athlean-X", "Jeff Nippard"],
        "brands": ["AG1", "Athletic Greens", "Gymshark", "Raw Nutrition", "Liver King Supplements"]
    },
    "Finance_Crypto": {
        "label": "📈 Finance & Crypto (Finfluencers)",
        "influencers": ["Coffeezilla", "Graham Stephan", "Andrei Jikh", "Meet Kevin", "Ali Abdaal"],
        "brands": ["FTX", "BlockFi", "Celsius", "Robinhood", "Webull", "CryptoZoo"]
    },
    "Gaming_Entertainment": {
        "label": "🎮 Gaming & Entertainment",
        "influencers": ["MrBeast", "Logan Paul", "KSI", "Kai Cenat", "PewDiePie", "Penguinz0"],
        "brands": ["Feastables", "Lunchly", "Prime Energy", "BetterHelp", "NordVPN", "GFuel", "Stake"]
    }
}

# ======================================================
# SIDEBAR
# ======================================================
st.sidebar.markdown("## ⚡ Controls")

auto_refresh = st.sidebar.toggle("Auto-Refresh (Live)", value=True)
refresh_sec  = st.sidebar.slider("Interval (sec)", 5, 60, 10, 5) if auto_refresh else 10

if st.sidebar.button("🔄 Refresh Now", width="stretch"):
    st.rerun()

st.sidebar.caption(
    f"🟢 Auto-refreshing every **{refresh_sec}s**" if auto_refresh
    else "⏸️ Manual refresh mode"
)
st.sidebar.divider()

# ======================================================
# DATA LOADING (multi-tier fallback)
# ======================================================
PROJECT_DIR   = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR    = os.path.join(PROJECT_DIR, "powerbi_export")
MASTER_PQ     = os.path.join(EXPORT_DIR, "master_stream_history.parquet")
LOCAL_DL      = os.path.join(PROJECT_DIR, "datalake", "social_events.parquet")
HDFS_URI      = "hdfs://localhost:8020/user/bda/datalake/"

@st.cache_resource
def _spark():
    try:
        from pyspark.sql import SparkSession
        s = SparkSession.builder \
            .appName("DashboardReader") \
            .config("spark.driver.memory", "1g") \
            .config("spark.ui.enabled", "false") \
            .getOrCreate()
        s.sparkContext.setLogLevel("ERROR")
        return s
    except Exception:
        return None

def load_data():
    """Load from HDFS → master parquet → local datalake → CSV, whichever works first."""
    # 1. HDFS via Spark
    spark = _spark()
    if spark:
        try:
            sdf = spark.read.parquet(HDFS_URI)
            if not sdf.isEmpty():
                return sdf.toPandas(), "Hadoop HDFS"
        except Exception:
            pass
    # 2. Master parquet
    if os.path.exists(MASTER_PQ):
        try:
            df = pd.read_parquet(MASTER_PQ)
            if not df.empty: return df, "Master Parquet"
        except Exception:
            pass
    # 3. Local datalake
    if os.path.exists(LOCAL_DL):
        try:
            df = pd.read_parquet(LOCAL_DL)
            if not df.empty: return df, "Local Datalake"
        except Exception:
            pass
    # 4. CSV export
    csv_path = os.path.join(EXPORT_DIR, "live_feed_summary.csv")
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            if not df.empty: return df, "CSV Export"
        except Exception:
            pass
    return pd.DataFrame(), "Awaiting Data"

def safe_list_col(series):
    """Convert column to list of strings."""
    def to_list(val):
        if val is None:
            return []
        if isinstance(val, (list, tuple)):
            return list(val)
        if isinstance(val, str):
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                try:
                    import ast
                    return ast.literal_eval(val)
                except Exception:
                    pass
            if "|" in val:
                return [x.strip() for x in val.split("|") if x.strip()]
            if "," in val:
                return [x.strip() for x in val.split(",") if x.strip()]
            return [val] if val and val != "None" else []
        try:
            return list(val)
        except Exception:
            return []
    return series.apply(to_list)

def highlight_terms(text, terms):
    """Safely escapes HTML and wraps matching search terms in a highlighted span."""
    if not text:
        return ""
    escaped = html.escape(str(text))
    if not terms:
        return escaped
    for t in terms:
        t_clean = str(t).strip()
        if len(t_clean) < 2:
            continue
        try:
            pattern = re.compile(re.escape(t_clean), re.IGNORECASE)
            escaped = pattern.sub(r'<span class="highlight">\g<0></span>', escaped)
        except Exception:
            pass
    return escaped

def search_comments(df, query, min_score=6):
    """
    Search comments across influencers, products, brands, and promotion ethics.
    Supports typo tolerance (e.g. 'mkbhd', 'feastables', 'ag1', 'coffeezilla').
    """
    if not query or not query.strip() or df.empty:
        return pd.DataFrame()
        
    q_raw = query.strip()
    q_lower = q_raw.lower()
    
    q_words = [w for w in re.split(r'[\s\-_,.]+', q_lower) if len(w) >= 2]
    if not q_words:
        q_words = [q_lower]
        
    records = []
    for _, row in df.iterrows():
        text = str(row.get("text", ""))
        text_lower = text.lower()
        
        entities = row.get("entities", [])
        if not isinstance(entities, list):
            entities = []
        entities_lower = [str(e).lower() for e in entities]
        
        aspects = row.get("aspect_sentiments", [])
        if not isinstance(aspects, list):
            aspects = []
        aspects_lower = [str(a).lower() for a in aspects]
        
        score = 0
        matched_terms = []
        
        # 1. Exact phrase match
        if q_lower in text_lower:
            score += 25
            matched_terms.append(q_raw)
            
        # 2. Token match
        text_tokens = re.findall(r'\b\w+\b', text_lower)
        for qw in q_words:
            if qw in text_tokens or qw in text_lower:
                score += 10
                matched_terms.append(qw)
                continue
                
            matched_ent = [ent for ent in entities_lower if qw in ent]
            if matched_ent:
                score += 12
                matched_terms.extend(matched_ent)
                continue
                
            matched_asp = [asp for asp in aspects_lower if qw in asp]
            if matched_asp:
                score += 12
                matched_terms.extend(matched_asp)
                continue
                
            if len(qw) >= 4:
                close_text = difflib.get_close_matches(qw, text_tokens, n=1, cutoff=0.72)
                if close_text:
                    score += 8
                    matched_terms.append(close_text[0])
                    continue
                close_ent = difflib.get_close_matches(qw, entities_lower, n=1, cutoff=0.72)
                if close_ent:
                    score += 9
                    matched_terms.append(close_ent[0])
                    continue
                    
        if score >= min_score:
            r = row.to_dict()
            r["_match_score"] = score
            r["_matched_terms"] = list(set(matched_terms))
            records.append(r)
            
    if not records:
        return pd.DataFrame()
        
    res_df = pd.DataFrame(records)
    sort_cols = ["_match_score"]
    asc = [False]
    if "timestamp" in res_df.columns:
        sort_cols.append("timestamp")
        asc.append(False)
    return res_df.sort_values(by=sort_cols, ascending=asc)

# ======================================================
# PRE-LOAD: populate sidebar category filter
# ======================================================
_init_df, _init_source = load_data()
_category_options = ["All Categories"] + list(INFLUENCER_TAXONOMY.keys())

sel_category = st.sidebar.selectbox(
    "🎯 Influencer Category",
    _category_options,
    format_func=lambda x: "🌐 All Categories" if x == "All Categories" else INFLUENCER_TAXONOMY.get(x, {}).get("label", x),
    key="category_filter"
)

# ======================================================
# MAIN DASHBOARD (auto-refresh fragment)
# ======================================================
@st.fragment(run_every=refresh_sec if auto_refresh else None)
def main_dashboard():
    now_str = datetime.now().strftime("%H:%M:%S")

    # --- HERO BANNER ---
    st.markdown(f"""
    <div class="hero-banner">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
                <h1>🌟 Influencer Sponsorship & Promotion Pulse</h1>
                <p>Analyzing Social Media Influencer Product Deals: Are they <b>Genuine (Good)</b> or <b>Deceptive (Wrong/Sellout)</b>?</p>
            </div>
            <div style="text-align:right;">
                <span class="pulse-live">LIVE ANALYTICS</span>
                <br><small style="opacity:0.8;">Last sync: {now_str}</small>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Load data
    df, source = load_data()
    st.caption(f"🗄️ Connected to DataLake: **{source}** · {len(df):,} influencer review records analyzed")

    if df.empty:
        st.warning("⏳ Pipeline is starting. Ensure `youtube_producer.py` and `spark_processor.py` are streaming influencer events.")
        return

    # Normalise columns
    if "domain" not in df.columns: df["domain"] = "Tech_Creators"
    if "sentiment" not in df.columns: df["sentiment"] = "Neutral"

    if "entities" in df.columns:
        df["entities"] = safe_list_col(df["entities"])
    else:
        df["entities"] = [[] for _ in range(len(df))]

    if "aspect_sentiments" in df.columns:
        df["aspect_sentiments"] = safe_list_col(df["aspect_sentiments"])
    else:
        df["aspect_sentiments"] = [[] for _ in range(len(df))]

    # Filter by category if selected
    sel_cat = st.session_state.get("category_filter", "All Categories")
    fdf = df if sel_cat == "All Categories" else df[df["domain"] == sel_cat]

    # ===================== KPI METRICS =====================
    total_reviews = len(fdf)
    good_promotions = int((fdf["sentiment"] == "POSITIVE").sum())
    wrong_promotions = int((fdf["sentiment"] == "NEGATIVE").sum())
    good_pct = round(good_promotions / total_reviews * 100, 1) if total_reviews else 0.0
    wrong_pct = round(wrong_promotions / total_reviews * 100, 1) if total_reviews else 0.0

    # Count distinct influencers mentioned
    all_known_inf = [inf for cat in INFLUENCER_TAXONOMY.values() for inf in cat["influencers"]]
    active_influencers = set()
    for row_text in fdf["text"]:
        tl = str(row_text).lower()
        for inf in all_known_inf:
            if inf.lower() in tl:
                active_influencers.add(inf)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("📢 Promotion Reviews", f"{total_reviews:,}")
    k2.metric("👍 Genuine Promotions (Good)", f"{good_pct:.1f}%", delta=f"+{good_promotions} authentic")
    k3.metric("🚨 Deceptive / Sellout (Wrong)", f"{wrong_pct:.1f}%", delta=f"-{wrong_promotions} shady", delta_color="inverse")
    k4.metric("👑 Influencers Tracked", f"{len(active_influencers)} creators")

    # ===================== QUERY SEARCH & SCORE =====================
    st.markdown('<div class="section-title">🔍 Search Influencer or Promoted Product</div>', unsafe_allow_html=True)
    st.caption("Inspect whether a creator's sponsorships are genuine or sellouts (e.g. **'MKBHD'**, **'MrBeast'**, **'Feastables'**, **'AG1'**, **'Coffeezilla'**, **'Mikayla'**, **'BetterHelp'**).")

    if "search_query" not in st.session_state:
        st.session_state["search_query"] = ""

    def _set_search_query(q):
        st.session_state["search_query"] = q

    search_col1, search_col2 = st.columns([5, 1])
    with search_col1:
        st.text_input(
            "Search Influencer or Brand",
            key="search_query",
            placeholder="Type influencer name or product (e.g. 'MKBHD', 'MrBeast', 'AG1', 'Feastables', 'Coffeezilla')...",
            label_visibility="collapsed"
        )

    with search_col2:
        st.button("🧹 Clear", on_click=_set_search_query, args=("",), width="stretch")

    # Quick suggestion chips
    quick_chips = ["MKBHD", "MrBeast", "Feastables", "AG1", "Coffeezilla", "Mikayla Nogueira", "Lunchly", "Logan Paul"]
    chip_cols = st.columns(len(quick_chips))
    for i, chip in enumerate(quick_chips):
        chip_cols[i].button(
            chip,
            key=f"quick_chip_{i}",
            on_click=_set_search_query,
            args=(chip,),
            width="stretch"
        )

    active_query = st.session_state.get("search_query", "").strip()

    if not active_query:
        st.info("💡 **Enter an influencer name or sponsored brand above** (e.g. `MKBHD`, `MrBeast`, `Feastables`, `AG1`, `Coffeezilla`) or click any chip to see if the promotion is rated **Good** or **Wrong**!")
    else:
        # Search within current filtered category
        search_res = search_comments(fdf, active_query)
        # If empty, search across all categories
        if search_res.empty and sel_cat != "All Categories":
            search_res = search_comments(df, active_query)
            if not search_res.empty:
                st.caption(f"ℹ️ Showing results from **All Categories** (found {len(search_res)} mentions for '{active_query}')")

        if search_res.empty:
            st.warning(f"🔍 No reviews found matching **'{active_query}'**. Try another creator like *'MKBHD'*, *'MrBeast'*, *'Feastables'*, *'AG1'*, or *'Coffeezilla'*.")
        else:
            q_total = len(search_res)
            q_pos = int((search_res["sentiment"] == "POSITIVE").sum())
            q_neg = int((search_res["sentiment"] == "NEGATIVE").sum())
            q_neu = q_total - q_pos - q_neg
            q_pos_pct = round(q_pos / q_total * 100, 1) if q_total else 0.0
            q_neg_pct = round(q_neg / q_total * 100, 1) if q_total else 0.0
            q_neu_pct = round(q_neu / q_total * 100, 1) if q_total else 0.0
            q_net_trust = round((q_pos - q_neg) / q_total * 100, 1) if q_total else 0.0

            # Verdict classification
            if q_net_trust >= 30:
                verdict_badge = f'<span class="score-badge-pos">🟢 Highly Authentic / Recommended Promotion ({q_net_trust:+.1f}% Trust)</span>'
            elif q_net_trust > 0:
                verdict_badge = f'<span class="score-badge-pos">🟢 Mostly Genuine ({q_net_trust:+.1f}% Trust)</span>'
            elif q_net_trust == 0:
                verdict_badge = f'<span class="score-badge-neutral">🟡 Mixed Opinions (0.0% Trust)</span>'
            elif q_net_trust > -30:
                verdict_badge = f'<span class="score-badge-neg">🔴 Shady / Questionable Promotion ({q_net_trust:+.1f}% Trust)</span>'
            else:
                verdict_badge = f'<span class="score-badge-neg">🔴 High Sellout / Scam Risk ({q_net_trust:+.1f}% Trust)</span>'

            # Extract matched terms
            matched_terms_all = set()
            for terms in search_res.get("_matched_terms", []):
                matched_terms_all.update(terms)
            terms_display = ", ".join(f"'{t}'" for t in sorted(matched_terms_all)) if matched_terms_all else f"'{active_query}'"

            # Render Query Score Card Container
            st.markdown(f"""
            <div class="query-score-box">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
                    <div>
                        <span style="font-size:1.3rem; font-weight:700; color:#F8FAFC;">Promotion Verdict for: <span style="color:#A78BFA;">"{active_query}"</span></span>
                        <br><small style="color:#94A3B8;">Keywords matched: <b>{terms_display}</b></small>
                    </div>
                    <div>{verdict_badge}</div>
                </div>
                <div class="sentiment-meter">
                    <div class="meter-pos" style="width: {q_pos_pct}%;" title="Good / Genuine: {q_pos_pct}%"></div>
                    <div class="meter-neu" style="width: {q_neu_pct}%;" title="Neutral: {q_neu_pct}%"></div>
                    <div class="meter-neg" style="width: {q_neg_pct}%;" title="Wrong / Sellout: {q_neg_pct}%"></div>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.82rem; color:#94A3B8;">
                    <span>🟢 <b>Good / Genuine:</b> {q_pos_pct}% ({q_pos} reviews)</span>
                    <span>⚪ <b>Neutral:</b> {q_neu_pct}% ({q_neu} reviews)</span>
                    <span>🔴 <b>Wrong / Sellout:</b> {q_neg_pct}% ({q_neg} reviews)</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Metrics
            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("📢 Promotion Reviews", f"{q_total:,}")
            sm2.metric("👍 'Good' / Authentic Rate", f"{q_pos_pct}%", delta=f"+{q_pos}")
            sm3.metric("🚨 'Wrong' / Sellout Rate", f"{q_neg_pct}%", delta=f"-{q_neg}", delta_color="inverse")
            sm4.metric("🎯 Net Trust Score", f"{q_net_trust:+.1f}%", delta="Consumer Trust")

            # Aspect breakdown
            q_aspects = []
            for tags in search_res["aspect_sentiments"]:
                for t in tags:
                    t_str = str(t)
                    if " -> " in t_str:
                        p = t_str.split(" -> ", 1)
                        q_aspects.append({"aspect": p[0].strip(), "sent": p[1].strip()})
            if q_aspects:
                q_asp_df = pd.DataFrame(q_aspects)
                q_pivot = q_asp_df.groupby(["aspect", "sent"]).size().unstack(fill_value=0).reset_index()
                for c in ["POSITIVE", "NEGATIVE"]:
                    if c not in q_pivot.columns: q_pivot[c] = 0
                q_pivot["Total"] = q_pivot["POSITIVE"] + q_pivot["NEGATIVE"]
                top_q_asp = q_pivot.sort_values("Total", ascending=False).head(8)
                
                st.markdown(f"**🎯 Sponsorship Aspects for '{active_query}':**")
                asp_badges_html = []
                for _, a_row in top_q_asp.iterrows():
                    asp_name = a_row["aspect"]
                    p_ct = a_row["POSITIVE"]
                    n_ct = a_row["NEGATIVE"]
                    badge = f"<span class='asp-pos'>🟢 {asp_name}: +{p_ct}</span>" if p_ct >= n_ct else f"<span class='asp-neg'>🔴 {asp_name}: -{n_ct}</span>"
                    asp_badges_html.append(badge)
                st.markdown(" ".join(asp_badges_html), unsafe_allow_html=True)

            st.write("")
            # Top Comments for this query
            st.markdown(f'<div class="section-title">💬 Top Reviews on "{active_query}"</div>', unsafe_allow_html=True)
            
            c_filter_col, _ = st.columns([3, 3])
            with c_filter_col:
                sent_filter = st.radio(
                    "Filter comments:",
                    ["All Reviews", "🟢 'Good' / Authentic", "🔴 'Wrong' / Sellout"],
                    horizontal=True,
                    key="query_comments_sentiment_filter"
                )

            filtered_comments = search_res.copy()
            if sent_filter == "🟢 'Good' / Authentic":
                filtered_comments = filtered_comments[filtered_comments["sentiment"] == "POSITIVE"]
            elif sent_filter == "🔴 'Wrong' / Sellout":
                filtered_comments = filtered_comments[filtered_comments["sentiment"] == "NEGATIVE"]

            if filtered_comments.empty:
                st.info(f"No {sent_filter.lower()} reviews found for this query.")
            else:
                top_comments_display = filtered_comments.head(35)
                st.caption(f"Showing **{len(top_comments_display)}** of **{len(filtered_comments)}** matching reviews:")
                for _, c_row in top_comments_display.iterrows():
                    c_sent = c_row.get("sentiment", "Neutral")
                    c_domain = c_row.get("domain", "General")
                    c_time = str(c_row.get("timestamp", ""))[:19]
                    c_text = str(c_row.get("text", ""))
                    c_terms = c_row.get("_matched_terms", [active_query])
                    
                    highlighted = highlight_terms(c_text, c_terms)
                    
                    card_class = "comment-card-pos" if c_sent == "POSITIVE" else ("comment-card-neg" if c_sent == "NEGATIVE" else "comment-card-neu")
                    sent_badge = "🟢 GENUINE / GOOD" if c_sent == "POSITIVE" else ("🔴 WRONG / SELLOUT" if c_sent == "NEGATIVE" else "⚪ NEUTRAL")
                    
                    aspect_badges = ""
                    c_aspects = c_row.get("aspect_sentiments", [])
                    if isinstance(c_aspects, list):
                        for a in c_aspects:
                            a_str = str(a)
                            if "POSITIVE" in a_str:
                                aspect_badges += f'<span class="asp-pos">{a_str}</span> '
                            elif "NEGATIVE" in a_str:
                                aspect_badges += f'<span class="asp-neg">{a_str}</span> '

                    st.markdown(f"""
                    <div class="comment-card {card_class}">
                        <div class="comment-meta">
                            <span><b>{sent_badge}</b> · 🏷️ {c_domain} · 🕒 {c_time}</span>
                            <span>{aspect_badges}</span>
                        </div>
                        <div class="comment-text">{highlighted}</div>
                    </div>
                    """, unsafe_allow_html=True)

    st.divider()

    # ===================== TABS =====================
    t_leaderboard, t_aspects, t_feed, t_export = st.tabs([
        "🏆  Top Influencers (Category-Wise)",
        "🎯  Sponsorship Ethics & ABSA",
        "⚡  Live Promotion Feed",
        "📥  Power BI Export",
    ])

    # ────────── TAB 1: CATEGORY-WISE INFLUENCER LEADERBOARD ──────────
    with t_leaderboard:
        st.markdown('<div class="section-title">🏆 Top Most Influencers by Category</div>', unsafe_allow_html=True)
        st.caption("Ranked by consumer trust score: how audiences perceive their sponsored product recommendations (Good / Authentic vs Wrong / Sellout).")

        # Build Category-Wise Leaderboard Data
        leaderboard_rows = []
        target_cats = list(INFLUENCER_TAXONOMY.keys()) if sel_cat == "All Categories" else [sel_cat]

        for cat_key in target_cats:
            cat_info = INFLUENCER_TAXONOMY[cat_key]
            cat_label = cat_info["label"]
            influencer_list = cat_info["influencers"]

            for inf in influencer_list:
                # Find matching comments mentioning this influencer
                inf_matches = df[df["text"].str.contains(inf, case=False, na=False)]
                total_m = len(inf_matches)
                if total_m > 0:
                    good_m = int((inf_matches["sentiment"] == "POSITIVE").sum())
                    wrong_m = int((inf_matches["sentiment"] == "NEGATIVE").sum())
                    good_r = round(good_m / total_m * 100, 1)
                    wrong_r = round(wrong_m / total_m * 100, 1)
                    net_t = round(good_r - wrong_r, 1)
                    
                    if net_t >= 25:
                        verdict_str = "🟢 High Trust / Authentic"
                    elif net_t >= -10:
                        verdict_str = "🟡 Mixed / Sponsored Bias"
                    else:
                        verdict_str = "🔴 High Sellout / Scam Risk"
                        
                    # Find brands mentioned in the same comments
                    brands_mentioned = []
                    for br in cat_info["brands"]:
                        if any(br.lower() in str(t).lower() for t in inf_matches["text"]):
                            brands_mentioned.append(br)

                    leaderboard_rows.append({
                        "Influencer": inf,
                        "Category": cat_label,
                        "Category_Key": cat_key,
                        "Reviews": total_m,
                        "Good %": good_r,
                        "Wrong %": wrong_r,
                        "Net Trust": net_t,
                        "Verdict": verdict_str,
                        "Promoted Products": ", ".join(brands_mentioned) if brands_mentioned else "Various Sponsors"
                    })

        if not leaderboard_rows:
            st.info("No influencer reviews matched yet. Let the pipeline stream a few micro-batches.")
        else:
            lb_df = pd.DataFrame(leaderboard_rows)

            # Leaderboard Chart
            c1, c2 = st.columns([3, 2])
            with c1:
                st.markdown("**📊 Net Trust Score by Creator**")
                sorted_lb = lb_df.sort_values(by="Net Trust", ascending=True)
                fig_trust = px.bar(
                    sorted_lb, y="Influencer", x="Net Trust",
                    color="Net Trust",
                    color_continuous_scale="RdYlGn",
                    orientation="h",
                    title="Net Consumer Trust Score (%)"
                )
                fig_trust.update_layout(margin=dict(t=30, b=10, l=10, r=10), height=380)
                st.plotly_chart(fig_trust, width="stretch")

            with c2:
                st.markdown("**📦 Reviews per Category**")
                cat_counts = df["domain"].value_counts().reset_index()
                cat_counts.columns = ["Category", "Reviews"]
                cat_counts["Category_Name"] = cat_counts["Category"].apply(lambda c: INFLUENCER_TAXONOMY.get(c, {}).get("label", c))
                fig_cat = px.pie(
                    cat_counts, names="Category_Name", values="Reviews",
                    color_discrete_sequence=px.colors.qualitative.Prism,
                    hole=0.4
                )
                fig_cat.update_layout(margin=dict(t=20, b=10, l=10, r=10), height=380, legend=dict(orientation="h", y=-0.15))
                st.plotly_chart(fig_cat, width="stretch")

            # Detailed Category Tables
            for cat_key in target_cats:
                cat_label = INFLUENCER_TAXONOMY[cat_key]["label"]
                cat_sub = lb_df[lb_df["Category_Key"] == cat_key].sort_values(by=["Reviews", "Net Trust"], ascending=[False, False])
                if not cat_sub.empty:
                    st.markdown(f"### {cat_label}")
                    cat_display = cat_sub[["Influencer", "Reviews", "Good %", "Wrong %", "Net Trust", "Verdict", "Promoted Products"]]
                    st.dataframe(cat_display, width="stretch", hide_index=True)

    # ────────── TAB 2: SPONSORSHIP ASPECTS & ABSA ──────────
    with t_aspects:
        st.markdown('<div class="section-title">🎯 Sponsorship Ethics & Aspect Sentiment (ABSA)</div>', unsafe_allow_html=True)
        st.caption("Examines key dimensions of influencer promotions: *'authenticity'*, *'honesty'*, *'product quality'*, *'disclosure'*, *'sellout'*, and *'pricing'*.")

        aspect_pairs = []
        for tags in fdf["aspect_sentiments"]:
            for t in tags:
                t_str = str(t)
                if " -> " in t_str:
                    parts = t_str.split(" -> ", 1)
                    aspect_pairs.append({"aspect": parts[0].strip(), "sent": parts[1].strip()})
        asp_df = pd.DataFrame(aspect_pairs) if aspect_pairs else pd.DataFrame(columns=["aspect", "sent"])

        if asp_df.empty:
            st.info("No aspect tags extracted yet. Wait for incoming Spark micro-batches.")
        else:
            pivot = asp_df.groupby(["aspect", "sent"]).size().unstack(fill_value=0).reset_index()
            for c in ["POSITIVE", "NEGATIVE"]:
                if c not in pivot.columns: pivot[c] = 0
            pivot["Total"] = pivot["POSITIVE"] + pivot["NEGATIVE"]
            pivot["Net Score"] = ((pivot["POSITIVE"] - pivot["NEGATIVE"]) / pivot["Total"] * 100).round(1)
            pivot = pivot.sort_values("Total", ascending=False).head(15)

            fig_asp = go.Figure()
            fig_asp.add_trace(go.Bar(
                y=pivot["aspect"], x=pivot["POSITIVE"],
                name="Good / Genuine", orientation="h", marker_color="#10B981"
            ))
            fig_asp.add_trace(go.Bar(
                y=pivot["aspect"], x=pivot["NEGATIVE"],
                name="Wrong / Sellout", orientation="h", marker_color="#EF4444"
            ))
            fig_asp.update_layout(
                barmode="stack", height=420,
                yaxis=dict(categoryorder="total ascending"),
                margin=dict(t=10, b=10, l=10, r=10),
                legend=dict(orientation="h", y=-0.12)
            )
            st.plotly_chart(fig_asp, width="stretch")

            st.markdown("**Sponsorship Aspect Scorecard**")
            st.dataframe(
                pivot[["aspect", "Total", "POSITIVE", "NEGATIVE", "Net Score"]].rename(columns={
                    "aspect": "Aspect / Entity",
                    "Total": "Total Mentions",
                    "POSITIVE": "👍 Genuine",
                    "NEGATIVE": "🚨 Deceptive",
                    "Net Score": "Net Trust %"
                }),
                width="stretch", hide_index=True
            )

    # ────────── TAB 3: LIVE PROMOTION FEED ──────────
    with t_feed:
        st.markdown('<div class="section-title">Latest 100 Enriched Influencer Promotion Reviews</div>', unsafe_allow_html=True)
        show = fdf.copy().tail(100).iloc[::-1]

        def fmt_aspects(tags):
            if not tags: return "—"
            badges = []
            for t in tags:
                s = str(t)
                if "POSITIVE" in s: badges.append(f"🟢 {s}")
                elif "NEGATIVE" in s: badges.append(f"🔴 {s}")
                else: badges.append(s)
            return " · ".join(badges)

        def fmt_entities(ents):
            if not ents: return "—"
            return ", ".join(str(e) for e in ents)

        show["Aspects"]  = show["aspect_sentiments"].apply(fmt_aspects)
        show["Entities"] = show["entities"].apply(fmt_entities)

        cols = ["timestamp", "domain", "sentiment", "Entities", "Aspects", "text"]
        cols = [c for c in cols if c in show.columns]

        st.dataframe(
            show[cols].rename(columns={
                "timestamp": "Time",
                "domain": "Category",
                "sentiment": "Verdict",
                "text": "Audience Review"
            }),
            width="stretch", height=480, hide_index=True
        )

    # ────────── TAB 4: POWER BI EXPORT ──────────
    with t_export:
        st.markdown('<div class="section-title">Continuous Power BI Analytics Export</div>', unsafe_allow_html=True)
        st.caption("Consolidated analytics files automatically written for Power BI dashboards.")

        files = [
            ("Influencer Leaderboard",  "influencer_leaderboard.csv"),
            ("Aspect Analytics",        "aspect_analytics.csv"),
            ("Category Summary",        "sentiment_summary.csv"),
            ("Live Review Feed",        "live_feed_summary.csv"),
            ("Scorecard KPI",           "kpi_summary.csv"),
        ]
        rows = []
        for label, fname in files:
            fp = os.path.join(EXPORT_DIR, fname)
            exists = os.path.exists(fp)
            rows.append({
                "Table":   label,
                "File":    fname,
                "Size":    f"{os.path.getsize(fp)/1024:.1f} KB" if exists else "—",
                "Updated": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%H:%M:%S") if exists else "—",
                "Status":  "✅ Ready" if exists else "⏳ Pending",
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        st.markdown(f"**Export folder:** `{EXPORT_DIR}`")
        dcols = st.columns(len(files))
        for i, (label, fname) in enumerate(files):
            fp = os.path.join(EXPORT_DIR, fname)
            if os.path.exists(fp):
                with open(fp, "rb") as f:
                    dcols[i].download_button(f"⬇ {fname}", f, file_name=fname, mime="text/csv", width="stretch")

main_dashboard()