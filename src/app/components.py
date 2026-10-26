"""
src/app/components.py
Reusable UI design elements, charts, and styling components for InfluencerAI v2.
Dark theme with sky-blue accents, emerald/amber semantic evidence badges,
compact glassmorphic headers, and responsive Plotly visualizers.
"""
from __future__ import annotations

from typing import Any, Mapping
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render_custom_css() -> None:
    """Inject modern dark-mode glassmorphic styling, typography, and badges."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        /* Compact glassmorphic header */
        .main-header {
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.95) 100%);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 16px;
            box-shadow: 0 4px 20px 0 rgba(0, 0, 0, 0.25);
        }

        /* Slim governance disclaimer */
        .disclaimer-banner {
            background: rgba(245, 158, 11, 0.08);
            border-left: 3px solid #F59E0B;
            border-radius: 6px;
            padding: 8px 14px;
            margin-bottom: 18px;
            color: #FCD34D;
            font-size: 0.85rem;
            line-height: 1.4;
        }

        /* Semantic evidence badges */
        .badge-full {
            background-color: rgba(16, 185, 129, 0.15);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.4);
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.72rem;
            font-weight: 700;
            display: inline-block;
        }
        .badge-partial {
            background-color: rgba(245, 158, 11, 0.15);
            color: #FBBF24;
            border: 1px solid rgba(245, 158, 11, 0.4);
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.72rem;
            font-weight: 700;
            display: inline-block;
        }

        /* Size tier badges */
        .badge-nano { background-color: #475569; color: #F8FAFC; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; }
        .badge-micro { background-color: #0284C7; color: #FFFFFF; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; }
        .badge-mid { background-color: #6366F1; color: #FFFFFF; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; }
        .badge-macro { background-color: #8B5CF6; color: #FFFFFF; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; }
        .badge-mega { background-color: #D946EF; color: #FFFFFF; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; }

        /* KPI Card */
        .kpi-card {
            background: rgba(30, 41, 59, 0.5);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            padding: 14px;
            margin-bottom: 10px;
        }

        /* Filter chip */
        .filter-chip {
            background: rgba(56, 189, 248, 0.12);
            color: #38BDF8;
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 12px;
            padding: 3px 10px;
            font-size: 0.75rem;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            margin-right: 6px;
            margin-bottom: 6px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_disclaimer() -> None:
    """Render mandatory honest framing disclaimer banner."""
    st.markdown(
        """
        <div class="disclaimer-banner">
            <strong>⚠️ Research & Governance Disclaimer:</strong>
            Scores estimate promotional fit and organic lift from public YouTube catalog signals;
            they do <strong>not</strong> represent measured sales, commercial ROI, or confidential platform earnings.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str, badge: str = "Parquet Batch Pipeline (HDFS-Ready)") -> None:
    """Render slim header banner with subtle gradient depth."""
    st.markdown(
        f"""
        <div class="main-header">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <div>
                    <span style="background: rgba(56, 189, 248, 0.15); color: #38BDF8; padding: 3px 10px; border-radius: 10px; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; border: 1px solid rgba(56, 189, 248, 0.3);">{badge}</span>
                    <h1 style="margin: 6px 0 2px 0; font-size: 1.7rem; font-weight: 800; background: linear-gradient(90deg, #FFFFFF 0%, #E2E8F0 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{title}</h1>
                    <p style="margin: 0; color: #94A3B8; font-size: 0.9rem;">{subtitle}</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_missing_gold_banner() -> None:
    """Display friendly empty-state when gold scored data is missing."""
    st.error(
        """
        **Gold Cohort Data Missing**: `data/gold/scored_creators.parquet` was not found.
        
        To build the precomputed Gold cohort table, run the automated pipeline build script in your terminal:
        ```bash
        python scripts/build_gold_cohort.py
        ```
        This reads Silver Parquet and computes Promotion-Potential Scores, size tiers, and evidence flags.
        """
    )


def render_radar_chart(
    components: dict[str, float],
    title: str | None = None,
) -> go.Figure:
    """Render a single-channel Plotly radar chart of Promotion-Potential Score components."""
    labels = list(components.keys())
    values = [float(v) * 100.0 if float(v) <= 1.0 else float(v) for v in components.values()]
    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=values_closed,
            theta=labels_closed,
            fill="toself",
            fillcolor="rgba(56, 189, 248, 0.22)",
            line=dict(color="#38BDF8", width=2.2),
            marker=dict(size=5, color="#0284C7"),
            name="Profile",
            hovertemplate="%{theta}: %{r:.1f}/100<extra></extra>",
        )
    )
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color="#64748B", gridcolor="rgba(255, 255, 255, 0.08)"),
            angularaxis=dict(color="#CBD5E1", gridcolor="rgba(255, 255, 255, 0.08)"),
            bgcolor="rgba(15, 23, 42, 0.4)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=30, r=30, t=20, b=20),
        height=300,
        showlegend=False,
    )
    return fig


def render_compare_radar_chart(
    creators_components: list[dict[str, Any]],
) -> go.Figure:
    """
    Render side-by-side multi-creator radar chart comparing 2 to 4 creators.
    creators_components is a list of dicts:
      [
        {"name": "Andrea Russett", "components": {"Fit": 80, ...}},
        {"name": "Kylie Cosmetics", "components": {"Fit": 90, ...}},
      ]
    """
    palette = ["#38BDF8", "#F59E0B", "#10B981", "#D946EF"]
    fill_palette = [
        "rgba(56, 189, 248, 0.15)",
        "rgba(245, 158, 11, 0.15)",
        "rgba(16, 185, 129, 0.15)",
        "rgba(217, 70, 239, 0.15)",
    ]

    fig = go.Figure()
    all_labels = []

    for idx, c in enumerate(creators_components):
        name = c["name"]
        comp = c["components"]
        labels = list(comp.keys())
        all_labels = labels
        values = [float(v) * 100.0 if float(v) <= 1.0 else float(v) for v in comp.values()]

        labels_closed = labels + [labels[0]]
        values_closed = values + [values[0]]
        color = palette[idx % len(palette)]
        fill = fill_palette[idx % len(fill_palette)]

        fig.add_trace(
            go.Scatterpolar(
                r=values_closed,
                theta=labels_closed,
                fill="toself",
                fillcolor=fill,
                line=dict(color=color, width=2.0),
                marker=dict(size=4, color=color),
                name=name,
                hovertemplate=f"<b>{name}</b><br>%{{theta}}: %{{r:.1f}}/100<extra></extra>",
            )
        )

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color="#64748B", gridcolor="rgba(255, 255, 255, 0.08)"),
            angularaxis=dict(color="#CBD5E1", gridcolor="rgba(255, 255, 255, 0.08)"),
            bgcolor="rgba(15, 23, 42, 0.4)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=30, r=30, t=25, b=25),
        height=360,
        legend=dict(orientation="h", y=-0.15, font=dict(color="#E2E8F0")),
    )
    return fig


def render_waterfall_chart(contributions: list[dict[str, Any]]) -> go.Figure:
    """
    Render a horizontal contribution bar chart showing weighted points
    and deductions toward the raw score.
    contributions: list of dicts with 'name', 'points', 'type' ('positive' or 'penalty')
    """
    names = [c["name"] for c in contributions]
    points = [c["points"] for c in contributions]
    colors = ["#EF4444" if c.get("type") == "penalty" else "#38BDF8" for c in contributions]

    fig = go.Figure(
        go.Bar(
            x=points,
            y=names,
            orientation="h",
            marker=dict(color=colors, line=dict(color="rgba(255, 255, 255, 0.1)", width=1)),
            text=[f"{p:+.1f} pts" if p != 0 else "0.0 pts" for p in points],
            textposition="auto",
            hovertemplate="%{y}: %{x:.2f} points<extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#CBD5E1"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=280,
        xaxis=dict(title="Points Contributed (out of 100)", gridcolor="rgba(255, 255, 255, 0.06)"),
        yaxis=dict(autorange="reversed"),
    )
    return fig


def render_confusion_matrix_chart(cm_df) -> go.Figure:
    """Render heatmap for confusion matrix."""
    z = cm_df.values
    x = ["Pred: Non-Influencer", "Pred: Influencer"] if cm_df.shape[1] == 2 else [f"Pred {c}" for c in cm_df.columns]
    y = ["Actual: Non-Influencer", "Actual: Influencer"] if cm_df.shape[0] == 2 else [f"Actual {i}" for i in range(cm_df.shape[0])]

    fig = px.imshow(
        z,
        x=x,
        y=y,
        color_continuous_scale="Blues",
        text_auto=True,
        aspect="auto",
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#CBD5E1"),
        margin=dict(l=20, r=20, t=20, b=20),
        height=280,
    )
    return fig
