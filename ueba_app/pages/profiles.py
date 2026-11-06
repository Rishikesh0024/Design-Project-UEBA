"""pages/profiles.py — User behaviour profiles and baselines."""

from __future__ import annotations
import pandas as pd
import streamlit as st

from ueba_app.data.features import extract_features, FEATURE_COLS
from ueba_app.utils import state
from ueba_app.utils.charts import user_activity_timeline


@st.cache_data(show_spinner=False)
def _cached_timeline(events_df: pd.DataFrame, user: str):
    """Cache the per-user chart so switching users is instant."""
    return user_activity_timeline(events_df, user)


def render() -> None:
    st.title("👤 User Behaviour Profiles")

    if not state.pipeline_ready():
        st.info("Load a dataset first (Dataset page).")
        return

    events_df = state.get("events_df")
    users_df  = state.get("users_df")

    # ── Run feature extraction if not done ───────────────────────────────────
    if state.get("daily_df") is None:
        with st.spinner("Extracting behavioural features…"):
            daily, baselines = extract_features(events_df, users_df)
            state.set("daily_df",     daily)
            state.set("baselines_df", baselines)
        st.success(f"Features extracted for {baselines['user'].nunique()} users.")

    daily_df    = state.get("daily_df")
    baselines   = state.get("baselines_df")

    # ── Role / user filter ────────────────────────────────────────────────────
    all_users = sorted(events_df["user"].unique())
    selected  = st.selectbox("Select a user to inspect", all_users)

    col_l, col_r = st.columns([2, 1])

    with col_l:
        st.plotly_chart(
            _cached_timeline(events_df, selected),
            use_container_width=True,
            theme=None,
        )

    with col_r:
        _user_stats(events_df, selected, users_df)

    st.divider()
    _baseline_table(baselines, selected, daily_df)

    st.divider()
    _all_baselines(baselines)


# ─────────────────────────────────────────────────────────────────────────────

def _user_stats(events_df: pd.DataFrame, user: str, users_df) -> None:
    df = events_df[events_df["user"] == user]
    st.markdown(f"**User:** `{user}`")

    if users_df is not None and "user_id" in users_df.columns:
        row = users_df[users_df["user_id"] == user]
        if not row.empty:
            st.write(f"Role: **{row.iloc[0].get('role', '—')}**")
            st.write(f"Dept: **{row.iloc[0].get('dept', '—')}**")

    st.metric("Total events",  f"{len(df):,}")
    st.metric("Active days",   df["date"].nunique())
    st.metric("Event types",   df["activity"].nunique())

    st.markdown("**Event breakdown**")
    for act, cnt in df["activity"].value_counts().items():
        st.write(f"  • `{act}`: {cnt:,}")


def _baseline_table(baselines: pd.DataFrame, user: str, daily_df: pd.DataFrame) -> None:
    st.subheader(f"Behavioural Baseline — {user}")

    bl_row = baselines[baselines["user"] == user]
    if bl_row.empty:
        st.warning("No baseline computed for this user.")
        return

    source = bl_row.iloc[0].get("baseline_source", "unknown")
    st.caption(f"Baseline source: **{source}**")

    rows = []
    for feat in FEATURE_COLS:
        med = bl_row.iloc[0].get(f"{feat}_median", None)
        mad = bl_row.iloc[0].get(f"{feat}_mad",    None)
        if med is not None:
            rows.append({"Feature": feat, "Median (baseline)": round(med, 2),
                         "MAD": round(mad, 2) if mad is not None else "—"})
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Recent vs baseline comparison
    user_daily = daily_df[daily_df["user"] == user].sort_values("date")
    if len(user_daily) > 0:
        st.markdown("**Recent daily activity (last 10 days)**")
        display = user_daily.tail(10)[
            ["date", "total_events", "logon_count", "file_count",
             "web_count", "device_count", "after_hours_count", "new_resources"]
        ].copy()
        st.dataframe(display, use_container_width=True, hide_index=True)


def _all_baselines(baselines: pd.DataFrame) -> None:
    st.subheader("All User Baselines")
    cols = ["user", "baseline_source"] + [
        f"{f}_median" for f in FEATURE_COLS if f"{f}_median" in baselines.columns
    ]
    cols = [c for c in cols if c in baselines.columns]
    st.dataframe(baselines[cols].round(2), use_container_width=True, hide_index=True)
