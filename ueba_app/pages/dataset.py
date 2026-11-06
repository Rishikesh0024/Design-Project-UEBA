"""pages/dataset.py — Upload, validate, and preview activity logs."""

from __future__ import annotations
import io
from pathlib import Path

import pandas as pd
import streamlit as st

from ueba_app.data.loader import load_csv
from ueba_app.utils import state

DEMO_PATH = Path(__file__).parent.parent.parent / "demo_data" / "demo_events.csv"
DEMO_USERS_PATH = Path(__file__).parent.parent.parent / "demo_data" / "demo_users.csv"


def render() -> None:
    st.title("📂 Dataset Upload & Preview")

    tab_upload, tab_demo = st.tabs(["Upload CSV", "Load Demo Dataset"])

    with tab_demo:
        _demo_tab()

    with tab_upload:
        _upload_tab()

    # ── Preview ───────────────────────────────────────────────────────────────
    if state.pipeline_ready():
        _show_preview()


# ─────────────────────────────────────────────────────────────────────────────

def _demo_tab() -> None:
    st.markdown(
        "Load the built-in **synthetic** demo dataset (16 k events, 30 users, "
        "60 days). Three users have planted anomalies with ground-truth labels."
    )
    st.warning(
        "⚠️ This is **synthetic** data generated for demonstration purposes. "
        "It does not represent real employees or real activity."
    )
    if st.button("Load Demo Dataset", type="primary"):
        _load_file(DEMO_PATH, is_demo=True)


def _upload_tab() -> None:
    st.markdown("Upload a CSV activity log. Required columns: **user**, **timestamp**, **activity**.")

    with st.expander("Column mapping (optional override)"):
        st.caption(
            "If your CSV uses non-standard column names, map them here. "
            "Leave blank to use auto-detection."
        )
        col1, col2 = st.columns(2)
        user_col  = col1.text_input("user column",      placeholder="e.g. employee_id")
        ts_col    = col1.text_input("timestamp column",  placeholder="e.g. event_time")
        act_col   = col2.text_input("activity column",   placeholder="e.g. event_type")
        pc_col    = col2.text_input("pc column",         placeholder="e.g. hostname")
        res_col   = col2.text_input("resource column",   placeholder="e.g. file_path")

    user_mapping: dict[str, str] = {}
    if user_col:  user_mapping["user"]      = user_col
    if ts_col:    user_mapping["timestamp"] = ts_col
    if act_col:   user_mapping["activity"]  = act_col
    if pc_col:    user_mapping["pc"]        = pc_col
    if res_col:   user_mapping["resource"]  = res_col

    uploaded = st.file_uploader(
        "Choose a CSV file", type=["csv"],
        help="Max 2 GB. Must contain user, timestamp, and activity columns.",
    )

    if uploaded is not None:
        size_mb = uploaded.size / (1024 * 1024)
        if size_mb > 2048:
            st.error(f"File too large ({size_mb:.1f} MB). Maximum is 2 GB.")
            return
        if st.button("Ingest Dataset", type="primary"):
            _load_bytes(uploaded.read(), uploaded.name, user_mapping, is_demo=False)


# ─────────────────────────────────────────────────────────────────────────────

def _load_file(path: Path, is_demo: bool) -> None:
    with st.spinner("Loading dataset…"):
        try:
            df, summary = load_csv(path)
            _store(df, summary, path.name, is_demo)
        except Exception as exc:
            st.error(f"Failed to load dataset: {exc}")


def _load_bytes(data: bytes, name: str, mapping: dict, is_demo: bool) -> None:
    with st.spinner("Ingesting dataset…"):
        try:
            df, summary = load_csv(io.BytesIO(data), user_mapping=mapping or None)
            _store(df, summary, name, is_demo)
        except Exception as exc:
            st.error(f"Ingestion failed: {exc}")


def _store(df: pd.DataFrame, summary: dict, name: str, is_demo: bool) -> None:
    state.set("events_df",    df)
    state.set("load_summary", summary)
    state.set("dataset_name", name)
    state.set("is_demo",      is_demo)
    state.clear_pipeline()

    # Load user metadata if demo
    if is_demo and DEMO_USERS_PATH.exists():
        users_df = pd.read_csv(DEMO_USERS_PATH)
        state.set("users_df", users_df)
    else:
        state.set("users_df", None)

    st.success(
        f"✅ Loaded **{summary['valid_rows']:,}** valid events "
        f"({summary['skipped_count']} skipped) | "
        f"**{summary['unique_users']}** users | "
        f"{summary['date_range'][0]} → {summary['date_range'][1]}"
    )
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────

def _show_preview() -> None:
    events_df = state.get("events_df")
    summary   = state.get("load_summary")

    st.divider()
    st.subheader("Ingestion Summary")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Rows",    f"{summary['total_rows']:,}")
    c2.metric("Valid Rows",    f"{summary['valid_rows']:,}")
    c3.metric("Skipped Rows",  f"{summary['skipped_count']:,}")
    c4.metric("Unique Users",  f"{summary['unique_users']:,}")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Date range**")
        st.write(f"{summary['date_range'][0]}  →  {summary['date_range'][1]}")
        st.markdown("**Event types detected**")
        for etype, cnt in summary["event_types"].items():
            st.write(f"  • `{etype}`: {cnt:,}")
    with col_r:
        st.markdown("**Column mapping resolved**")
        for canon, actual in summary["column_mapping"].items():
            st.write(f"  • `{canon}` ← `{actual}`")
        if summary.get("has_labels"):
            st.success("✅ Ground-truth labels detected — evaluation metrics available.")
        else:
            st.info("ℹ️ No ground-truth labels found.")

    if summary["skipped_count"] > 0:
        with st.expander(f"⚠️ Skipped rows ({summary['skipped_count']})"):
            st.dataframe(pd.DataFrame(summary["skipped_sample"]), use_container_width=True)

    st.divider()
    st.subheader("Event Log Preview (first 500 rows)")
    display_cols = [c for c in ["event_id", "timestamp", "user", "activity", "pc", "resource", "label"]
                    if c in events_df.columns]
    st.dataframe(events_df[display_cols].head(500), use_container_width=True)
