"""pages/dashboard.py — Security monitoring overview."""

from __future__ import annotations
import streamlit as st
import pandas as pd
from ueba_app.utils import state
from ueba_app.utils.charts import (
    activity_over_time, severity_distribution,
    top_users_by_risk, alerts_over_time, event_type_pie,
)

# Severity badge colours (inline HTML)
_SEV_COLOR = {"Critical": "#ff4444", "High": "#ff8c00", "Medium": "#ffd700", "Low": "#4caf50"}


def render() -> None:
    # ── Page header ───────────────────────────────────────────────────────────
    st.markdown(
        '<h1 style="font-size:1.75rem;font-weight:700;color:#58a6ff;'
        'margin-bottom:0.1rem;line-height:1.2;">🛡️ UEBA Security Dashboard</h1>',
        unsafe_allow_html=True,
    )

    if not state.pipeline_ready():
        st.markdown(
            '<p style="font-size:0.82rem;color:#6e7681;margin-top:2px;margin-bottom:12px;">'
            'No dataset loaded — go to <b>Dataset</b> to upload logs or load the demo.</p>',
            unsafe_allow_html=True,
        )
        _kpi_row(None, None, None, None)
        return

    events_df = state.get("events_df")
    scored_df = state.get("scored_df")
    alerts_df = state.get("alerts_df")
    name      = state.get("dataset_name") or "Loaded dataset"
    is_demo   = state.get("is_demo")

    # Sub-header line
    demo_badge = (
        ' &nbsp;<span style="background:#1f3a1f;color:#3fb950;font-size:0.68rem;'
        'padding:1px 7px;border-radius:10px;border:1px solid #2ea043;">DEMO</span>'
        if is_demo else ""
    )
    st.markdown(
        f'<p style="font-size:0.8rem;color:#6e7681;margin-top:0;margin-bottom:14px;">'
        f'Dataset: <span style="color:#c9d1d9;">{name}</span>{demo_badge}</p>',
        unsafe_allow_html=True,
    )

    # ── KPI values ────────────────────────────────────────────────────────────
    total_events = len(events_df)
    total_users  = events_df["user"].nunique()
    anomalies    = int(scored_df["is_anomaly"].sum()) if scored_df is not None else None
    high_alerts  = (
        int((alerts_df["severity"].isin(["Critical", "High"])).sum())
        if alerts_df is not None else None
    )
    _kpi_row(total_events, total_users, anomalies, high_alerts)

    # ── Severity summary strip (only when alerts exist) ───────────────────────
    if alerts_df is not None and len(alerts_df) > 0:
        _severity_strip(alerts_df)

    st.markdown('<div style="margin-top:10px;"></div>', unsafe_allow_html=True)

    # ── Row 1: activity timeline (wide) + event-type donut ───────────────────
    col_l, col_r = st.columns([3, 1], gap="small")
    with col_l:
        st.plotly_chart(
            activity_over_time(events_df),
            use_container_width=True,
            theme=None,
            config={"displayModeBar": False},
        )
    with col_r:
        st.plotly_chart(
            event_type_pie(events_df),
            use_container_width=True,
            theme=None,
            config={"displayModeBar": False},
        )

    # ── Row 2: alerts timeline + severity bar (only post-detection) ───────────
    if alerts_df is not None and len(alerts_df) > 0:
        col_l2, col_r2 = st.columns([3, 1], gap="small")
        with col_l2:
            st.plotly_chart(
                alerts_over_time(alerts_df),
                use_container_width=True,
                theme=None,
                config={"displayModeBar": False},
            )
        with col_r2:
            st.plotly_chart(
                severity_distribution(alerts_df),
                use_container_width=True,
                theme=None,
                config={"displayModeBar": False},
            )

        # ── Row 3: top users (half width to avoid stretching) ─────────────────
        col_main, col_pad = st.columns([2, 1], gap="small")
        with col_main:
            st.plotly_chart(
                top_users_by_risk(scored_df),
                use_container_width=True,
                theme=None,
                config={"displayModeBar": False},
            )
        with col_pad:
            _alert_summary_table(alerts_df)
    else:
        st.markdown(
            '<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;'
            'padding:14px 18px;font-size:0.83rem;color:#6e7681;margin-top:4px;">'
            '⚙️ Run <b>Anomaly Detection</b> to populate alert charts and risk rankings.'
            '</div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Sub-components
# ─────────────────────────────────────────────────────────────────────────────

def _kpi_row(
    total_events,
    total_users,
    anomalies,
    high_alerts,
) -> None:
    """Four equal KPI cards in one row."""
    cards = [
        ("Total Events",     total_events,  "#58a6ff"),
        ("Users Analysed",   total_users,   "#3fb950"),
        ("Anomalies Found",  anomalies,     "#ffa657"),
        ("High-Risk Alerts", high_alerts,   "#ff4444"),
    ]
    cols = st.columns(4, gap="small")
    for col, (label, value, accent) in zip(cols, cards):
        display = f"{value:,}" if isinstance(value, int) else "—"
        col.markdown(
            f'<div style="background:#161b22;border:1px solid #30363d;'
            f'border-radius:8px;padding:14px 18px 12px 18px;min-height:82px;">'
            f'<p style="font-size:0.7rem;color:#6e7681;text-transform:uppercase;'
            f'letter-spacing:0.05em;font-weight:500;margin:0 0 4px 0;">{label}</p>'
            f'<p style="font-size:1.85rem;font-weight:700;color:{accent};'
            f'margin:0;line-height:1.1;">{display}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _severity_strip(alerts_df: pd.DataFrame) -> None:
    """Compact one-line severity count badges."""
    order = ["Critical", "High", "Medium", "Low"]
    counts = alerts_df["severity"].value_counts()
    badges = ""
    for sev in order:
        n = counts.get(sev, 0)
        if n == 0:
            continue
        c = _SEV_COLOR[sev]
        badges += (
            f'<span style="background:{c}22;color:{c};border:1px solid {c}55;'
            f'border-radius:12px;padding:2px 10px;font-size:0.75rem;'
            f'font-weight:600;margin-right:6px;">{sev} {n}</span>'
        )
    st.markdown(
        f'<div style="margin:6px 0 2px 0;">{badges}</div>',
        unsafe_allow_html=True,
    )


def _alert_summary_table(alerts_df: pd.DataFrame) -> None:
    """Compact top-5 alert list shown beside the top-users chart."""
    st.markdown(
        '<p style="font-size:0.78rem;font-weight:600;color:#8b949e;'
        'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">'
        'Top Alerts</p>',
        unsafe_allow_html=True,
    )
    top5 = (
        alerts_df.sort_values("risk_score", ascending=False)
        .head(5)[["user", "date", "severity", "risk_score"]]
    )
    for _, row in top5.iterrows():
        c = _SEV_COLOR.get(row["severity"], "#8b949e")
        st.markdown(
            f'<div style="background:#0d1117;border:1px solid #21262d;'
            f'border-radius:6px;padding:7px 10px;margin-bottom:5px;">'
            f'<span style="font-size:0.8rem;font-weight:600;color:#e6edf3;">'
            f'{row["user"]}</span>'
            f'<span style="float:right;font-size:0.75rem;font-weight:700;color:{c};">'
            f'{row["risk_score"]:.0f}</span><br>'
            f'<span style="font-size:0.7rem;color:#6e7681;">{row["date"]}</span>'
            f'<span style="float:right;font-size:0.68rem;color:{c};">'
            f'{row["severity"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
