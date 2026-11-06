"""pages/explorer.py — Search and inspect processed activity events."""

from __future__ import annotations
import pandas as pd
import streamlit as st

from ueba_app.utils import state


def render() -> None:
    st.title("🔎 Activity Explorer")

    if not state.pipeline_ready():
        st.info("Load a dataset first (Dataset page).")
        return

    events_df = state.get("events_df")

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.expander("Filters", expanded=True):
        col1, col2, col3 = st.columns(3)
        user_filter = col1.text_input("User ID contains", "")
        act_filter  = col2.multiselect(
            "Activity type",
            sorted(events_df["activity"].unique()),
            default=list(events_df["activity"].unique()),
        )
        res_filter  = col3.text_input("Resource contains", "")

        col4, col5 = st.columns(2)
        dates = sorted(events_df["date"].unique())
        date_from = col4.selectbox("From date", dates, index=0)
        date_to   = col5.selectbox("To date",   dates, index=len(dates) - 1)

    mask = (
        events_df["activity"].isin(act_filter)
        & (events_df["date"] >= date_from)
        & (events_df["date"] <= date_to)
    )
    if user_filter:
        mask &= events_df["user"].str.contains(user_filter, case=False, na=False)
    if res_filter:
        mask &= events_df["resource"].str.contains(res_filter, case=False, na=False)

    filtered = events_df[mask].copy()
    st.caption(f"**{len(filtered):,}** events match filters")

    display_cols = [c for c in
                    ["event_id", "timestamp", "user", "activity", "pc", "resource", "label"]
                    if c in filtered.columns]

    # Pagination
    page_size = 200
    total_pages = max(1, (len(filtered) - 1) // page_size + 1)
    page = st.number_input("Page", 1, total_pages, 1)
    start = (page - 1) * page_size
    st.dataframe(
        filtered[display_cols].iloc[start: start + page_size].reset_index(drop=True),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(f"Page {page} of {total_pages}")
