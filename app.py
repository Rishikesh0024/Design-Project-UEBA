"""
app.py — UEBA Prototype entry point
Run with:  streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="UEBA — Internal Threat Identification",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background-color: #0d1117; }
[data-testid="stSidebar"]          { background-color: #161b22; }
[data-testid="stHeader"]           { background-color: #0d1117; border-bottom: 1px solid #21262d; }

.block-container {
    padding-top: 1.2rem !important;
    padding-bottom: 1rem !important;
    max-width: 100% !important;
}

html, body, [class*="css"] {
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    font-size: 14px;
}
h1 { color: #58a6ff !important; font-size: 1.75rem !important;
     font-weight: 600 !important; margin-bottom: 0.15rem !important; }
h2 { color: #e6edf3 !important; font-size: 1.2rem  !important;
     font-weight: 600 !important; margin-top: 0.8rem !important; }
h3 { color: #c9d1d9 !important; font-size: 1rem   !important;
     font-weight: 500 !important; }

[data-testid="metric-container"] {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 14px 18px 12px 18px;
    min-height: 88px;
}
[data-testid="metric-container"] > div:first-child {
    font-size: 0.75rem !important;
    color: #8b949e !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 500;
}
[data-testid="stMetricValue"] {
    font-size: 1.9rem !important;
    font-weight: 700 !important;
    color: #e6edf3 !important;
    line-height: 1.15 !important;
}
[data-testid="stMetricDelta"] { font-size: 0.78rem !important; }

[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    text-align: left;
    background-color: transparent;
    border: none;
    color: #8b949e;
    padding: 5px 10px;
    border-radius: 5px;
    font-size: 0.85rem;
    line-height: 1.4;
    margin-bottom: 1px;
    transition: background 0.15s, color 0.15s;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background-color: #21262d;
    color: #e6edf3;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {
    gap: 0px !important;
}

.sidebar-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #58a6ff;
    letter-spacing: 0.02em;
    margin: 0;
    padding: 0;
}
.sidebar-subtitle {
    font-size: 0.72rem;
    color: #6e7681;
    margin-top: 1px;
    margin-bottom: 0;
}

.status-row {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.78rem;
    color: #8b949e;
    padding: 2px 0;
}
.dot-on  { color: #3fb950; font-size: 0.6rem; }
.dot-off { color: #484f58; font-size: 0.6rem; }

hr { border-color: #21262d !important; margin: 0.5rem 0 !important; }

[data-testid="stDataFrame"] {
    border: 1px solid #30363d;
    border-radius: 6px;
    font-size: 0.82rem;
}

[data-testid="stAlert"] { border-radius: 6px; font-size: 0.85rem; }

[data-testid="stExpander"] summary {
    font-size: 0.85rem;
    color: #8b949e;
}

[data-testid="stTabs"] [role="tab"] { font-size: 0.85rem; }

[data-testid="column"] { padding-left: 6px !important; padding-right: 6px !important; }
</style>
""", unsafe_allow_html=True)

from ueba_app.utils import state
from ueba_app.pages import (
    dashboard, dataset, profiles, detection, alerts, evaluation, explorer,
)

state.init_state()

with st.sidebar:
    st.markdown(
        '<p class="sidebar-title">🛡️ UEBA</p>'
        '<p class="sidebar-subtitle">Internal Threat Identification</p>',
        unsafe_allow_html=True,
    )
    st.divider()

    pages = {
        "🏠  Dashboard":          "dashboard",
        "📂  Dataset":            "dataset",
        "🔎  Activity Explorer":  "explorer",
        "👤  Behaviour Profiles": "profiles",
        "🔍  Anomaly Detection":  "detection",
        "🚨  Alerts":             "alerts",
        "📊  Evaluation":         "evaluation",
    }

    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "dashboard"

    for label, key in pages.items():
        is_active = st.session_state["current_page"] == key
        if st.button(
            label,
            key=f"nav_{key}",
            type="primary" if is_active else "secondary",
        ):
            st.session_state["current_page"] = key
            st.rerun()

    st.divider()

    def _status_html(ok: bool, label: str) -> str:
        col = "#3fb950" if ok else "#484f58"
        return (
            f'<div class="status-row">'
            f'<span style="color:{col};font-size:0.55rem;">●</span>'
            f'<span>{label}</span></div>'
        )

    st.markdown(
        '<p style="font-size:0.72rem;font-weight:600;color:#6e7681;'
        'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;">'
        'Pipeline</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        _status_html(state.pipeline_ready(), "Dataset loaded") +
        _status_html(state.get("daily_df") is not None, "Features extracted") +
        _status_html(state.detection_ready(), "Detection run") +
        _status_html(state.alerts_ready(), "Alerts generated"),
        unsafe_allow_html=True,
    )

    st.divider()
    st.markdown(
        '<p style="font-size:0.68rem;color:#484f58;line-height:1.5;">'
        'Design Project — Phase 1<br>Synthetic demo data only.</p>',
        unsafe_allow_html=True,
    )

page = st.session_state.get("current_page", "dashboard")

if page == "dashboard":
    dashboard.render()
elif page == "dataset":
    dataset.render()
elif page == "explorer":
    explorer.render()
elif page == "profiles":
    profiles.render()
elif page == "detection":
    detection.render()
elif page == "alerts":
    alerts.render()
elif page == "evaluation":
    evaluation.render()
