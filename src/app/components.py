"""
src/app/components.py
Phase 8 — Reusable UI design elements, charts, and styling components.
Adheres strictly to the modern dark aesthetic and glassmorphism guidelines.
"""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render_custom_css() -> None:
    """Inject modern dark-mode glassmorphic styling and typography."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        .main-header {
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.36);
        }

        .disclaimer-banner {
            background: rgba(245, 158, 11, 0.12);
            border-left: 4px solid #F59E0B;
            border-radius: 8px;
            padding: 12px 18px;
            margin-bottom: 24px;
            color: #FCD34D;
            font-size: 0.92rem;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .kpi-card {
            background: rgba(30, 41, 59, 0.6);
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 12px;
            transition: transform 0.2s ease, border-color 0.2s ease;
        }
        .kpi-card:hover {
            border-color: rgba(56, 189, 248, 0.4);
            transform: translateY(-2px);
        }

        .badge-nano { background-color: #64748B; color: #F8FAFC; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
        .badge-micro { background-color: #0EA5E9; color: #FFFFFF; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
        .badge-macro { background-color: #8B5CF6; color: #FFFFFF; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
        .badge-mega { background-color: #EC4899; color: #FFFFFF; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }

        .score-pill {
            background: linear-gradient(135deg, #0284C7 0%, #2563EB 100%);
            color: white;
            padding: 4px 10px;
            border-radius: 14px;
            font-weight: 700;
            font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_disclaimer() -> None:
    """Render mandatory honest framing disclaimer banner (Section 1)."""
    st.markdown(
        """
        <div class="disclaimer-banner">
            <div>
                <strong>⚠️ Research & Governance Disclaimer:</strong>
                <em>Predicted promotion potential is computed from public YouTube video and channel engagement signals;
                it does <strong>not</strong> represent measured sales, commercial ROI, or confidential platform earnings.</em>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, subtitle: str, badge: str = "Hadoop + Spark ML") -> None:
    """Render header banner with glassmorphic depth."""
    st.markdown(
        f"""
        <div class="main-header">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="background: rgba(56, 189, 248, 0.2); color: #38BDF8; padding: 4px 12px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; border: 1px solid rgba(56, 189, 248, 0.3);">{badge}</span>
                    <h1 style="margin: 8px 0 4px 0; font-size: 2.1rem; font-weight: 800; background: linear-gradient(90deg, #FFFFFF 0%, #CBD5E1 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{title}</h1>
                    <p style="margin: 0; color: #94A3B8; font-size: 1.0rem;">{subtitle}</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_radar_chart(components: dict[str, float]) -> go.Figure:
    """Render a Plotly radar chart of Promotion-Potential Score components."""
    labels = list(components.keys())
    values = [float(v) * 100.0 if float(v) <= 1.0 else float(v) for v in components.values()]
    # Close the radar loop
    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=values_closed,
            theta=labels_closed,
            fill="toself",
            fillcolor="rgba(56, 189, 248, 0.25)",
            line=dict(color="#38BDF8", width=2.5),
            marker=dict(size=6, color="#0284C7"),
            name="Score Profile",
        )
    )
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], color="#64748B", gridcolor="rgba(255, 255, 255, 0.1)"),
            angularaxis=dict(color="#CBD5E1", gridcolor="rgba(255, 255, 255, 0.1)"),
            bgcolor="rgba(15, 23, 42, 0.5)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=35, r=35, t=25, b=25),
        height=320,
        showlegend=False,
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
