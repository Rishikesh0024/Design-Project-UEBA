"""
ueba_app/utils/state.py
------------------------
Centralised session-state keys and helpers.
All pipeline results are stored here so they survive Streamlit reruns
and page navigation.
"""

from __future__ import annotations
import streamlit as st


KEYS = {
    "events_df":    None,   # raw cleaned event log
    "users_df":     None,   # user metadata (optional)
    "daily_df":     None,   # daily feature matrix
    "baselines_df": None,   # per-user baselines
    "scored_df":    None,   # daily features + anomaly scores
    "alerts_df":    None,   # alert table
    "eval_results": None,   # evaluation dict
    "load_summary": None,   # ingestion summary dict
    "detector":     None,   # fitted UEBADetector instance
    "dataset_name": "",     # display name
    "is_demo":      False,  # whether demo data is loaded
}


def init_state() -> None:
    for key, default in KEYS.items():
        if key not in st.session_state:
            st.session_state[key] = default


def get(key: str):
    return st.session_state.get(key)


def set(key: str, value) -> None:  # noqa: A001
    st.session_state[key] = value


def clear_pipeline() -> None:
    """Reset all pipeline results (keep raw events)."""
    for key in ["daily_df", "baselines_df", "scored_df", "alerts_df",
                "eval_results", "detector"]:
        st.session_state[key] = None


def pipeline_ready() -> bool:
    return st.session_state.get("events_df") is not None


def detection_ready() -> bool:
    return st.session_state.get("scored_df") is not None


def alerts_ready() -> bool:
    df = st.session_state.get("alerts_df")
    return df is not None and len(df) > 0
