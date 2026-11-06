"""pages/alerts.py — Browse, filter, and investigate alerts."""

from __future__ import annotations
import pandas as pd
import streamlit as st

from ueba_app.utils import state
from ueba_app.utils.charts import branch_score_bars, branch_score_radar

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
SEVERITY_COLOR = {"Critical": "#ff4444", "High": "#ff8c00", "Medium": "#ffd700", "Low": "#4caf50"}
SEVERITY_EMOJI = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}

_BRANCH_CSS = """
<style>
.branch-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 8px;
}
.branch-title {
    font-size: 11px;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 4px;
}
.branch-score {
    font-size: 22px;
    font-weight: 700;
    line-height: 1.1;
}
.branch-contrib {
    font-size: 11px;
    color: #8b949e;
    margin-top: 2px;
}
.formula-row {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    padding: 6px 0;
    border-bottom: 1px solid #21262d;
}
.formula-label { color: #8b949e; width: 180px; flex-shrink: 0; }
.formula-bar-wrap { flex: 1; background: #21262d; border-radius: 4px; height: 8px; }
.formula-bar { height: 8px; border-radius: 4px; }
.formula-val { color: #e6edf3; font-weight: 600; width: 52px; text-align: right; flex-shrink: 0; }
.formula-contrib { color: #8b949e; font-size: 11px; width: 60px; text-align: right; flex-shrink: 0; }
</style>
"""

_BRANCH_META = [
    ("Isolation Forest", "if_score",   0.45, "#58a6ff",
     "Unsupervised ML model trained on normal behaviour. High score = isolated outlier."),
    ("Statistical MAD",  "stat_score", 0.35, "#d2a8ff",
     "Mean positive deviation from personal baseline (median ± MAD). High score = far from normal."),
    ("Rule-Based",       "rule_score", 0.20, "#ffa657",
     "Fraction of 5 deterministic rules triggered (after-hours, device spike, new resources, etc.)."),
]


def render() -> None:
    st.markdown(_BRANCH_CSS, unsafe_allow_html=True)
    st.title("🚨 Alerts")

    if not state.alerts_ready():
        st.info("Run **Anomaly Detection** first to generate alerts.")
        return

    alerts_df = state.get("alerts_df").copy()

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.expander("🔎 Search & Filter", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        search_user   = col1.text_input("User ID contains", "")
        sev_filter    = col2.multiselect(
            "Severity", ["Critical", "High", "Medium", "Low"],
            default=["Critical", "High", "Medium", "Low"],
        )
        status_filter = col3.multiselect(
            "Status", ["open", "investigating", "reviewed"],
            default=["open", "investigating", "reviewed"],
        )
        min_score = col4.slider("Min risk score", 0, 100, 0)

    mask = (
        alerts_df["severity"].isin(sev_filter)
        & alerts_df["status"].isin(status_filter)
        & (alerts_df["risk_score"] >= min_score)
    )
    if search_user:
        mask &= alerts_df["user"].str.contains(search_user, case=False, na=False)

    filtered = alerts_df[mask].copy()
    filtered["_sev_order"] = filtered["severity"].map(SEVERITY_ORDER)
    filtered = (
        filtered.sort_values(["_sev_order", "risk_score"], ascending=[True, False])
        .drop(columns="_sev_order")
        .reset_index(drop=True)
    )

    st.caption(f"Showing **{len(filtered)}** of **{len(alerts_df)}** alerts")

    if len(filtered) == 0:
        st.warning("No alerts match the current filters.")
        return

    # ── Alert table ───────────────────────────────────────────────────────────
    display_cols = ["alert_id", "date", "user", "primary_activity",
                    "risk_score", "severity", "if_score", "stat_score",
                    "rule_score", "status", "n_supporting_events"]
    display_cols = [c for c in display_cols if c in filtered.columns]

    st.dataframe(
        filtered[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "risk_score": st.column_config.ProgressColumn(
                "Risk Score", min_value=0, max_value=100, format="%.1f"
            ),
            "if_score":   st.column_config.ProgressColumn(
                "IF Score", min_value=0, max_value=1, format="%.3f"
            ),
            "stat_score": st.column_config.ProgressColumn(
                "Stat Score", min_value=0, max_value=1, format="%.3f"
            ),
            "rule_score": st.column_config.ProgressColumn(
                "Rule Score", min_value=0, max_value=1, format="%.3f"
            ),
        },
    )

    st.divider()

    # ── Alert detail / investigation ──────────────────────────────────────────
    st.subheader("Alert Detail & Investigation")
    alert_ids   = filtered["alert_id"].tolist()
    selected_id = st.selectbox("Select alert to inspect", alert_ids)

    row = filtered[filtered["alert_id"] == selected_id].iloc[0]
    _render_alert_detail(row, alerts_df)


# ─────────────────────────────────────────────────────────────────────────────

def _render_alert_detail(row: pd.Series, alerts_df: pd.DataFrame) -> None:
    sev       = row["severity"]
    sev_emoji = SEVERITY_EMOJI.get(sev, "⚪")
    sev_color = SEVERITY_COLOR.get(sev, "#8b949e")

    if_score   = float(row.get("if_score",   0))
    stat_score = float(row.get("stat_score", 0))
    rule_score = float(row.get("rule_score", 0))

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<h3 style="color:{sev_color};margin-bottom:4px;">'
        f'{sev_emoji} {row["alert_id"]} — {row["user"]}</h3>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'**Date:** {row["date"]} &nbsp;|&nbsp; '
        f'**Activity:** `{row["primary_activity"]}` &nbsp;|&nbsp; '
        f'**Severity:** <span style="color:{sev_color};">{sev}</span>',
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Two-column layout: branch breakdown left, investigation right ─────────
    col_main, col_inv = st.columns([3, 1])

    with col_main:
        # ── 3-branch score cards ──────────────────────────────────────────────
        st.markdown("#### Detection Branch Scores")
        bc1, bc2, bc3 = st.columns(3)
        branch_cols = [bc1, bc2, bc3]
        for col, (name, key, weight, color, desc) in zip(branch_cols, _BRANCH_META):
            score  = float(row.get(key, 0))
            contrib = round(score * weight * 100, 1)
            col.markdown(
                f'<div class="branch-card">'
                f'<div class="branch-title">{name}</div>'
                f'<div class="branch-score" style="color:{color}">{score:.3f}</div>'
                f'<div class="branch-contrib">Weight {int(weight*100)}% → '
                f'<b style="color:{color}">{contrib} pts</b></div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            col.caption(desc)

        # ── Risk score formula breakdown ──────────────────────────────────────
        st.markdown("#### Risk Score Formula")
        risk = row["risk_score"]
        formula_rows = ""
        for name, key, weight, color, _ in _BRANCH_META:
            score   = float(row.get(key, 0))
            contrib = score * weight * 100
            bar_w   = int(score * 100)
            formula_rows += (
                f'<div class="formula-row">'
                f'<span class="formula-label">{name} × {int(weight*100)}%</span>'
                f'<div class="formula-bar-wrap">'
                f'<div class="formula-bar" style="width:{bar_w}%;background:{color}"></div>'
                f'</div>'
                f'<span class="formula-val">{score:.3f}</span>'
                f'<span class="formula-contrib">+{contrib:.1f} pts</span>'
                f'</div>'
            )
        st.markdown(
            f'<div style="background:#161b22;border:1px solid #30363d;'
            f'border-radius:8px;padding:12px 16px;">'
            f'{formula_rows}'
            f'<div style="padding-top:8px;font-size:13px;color:#e6edf3;">'
            f'<b>Final Risk Score: '
            f'<span style="color:{sev_color};font-size:18px;">{risk:.1f}</span>'
            f' / 100</b></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Charts: bars + radar side by side ────────────────────────────────
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        ch1, ch2 = st.columns([3, 2])
        with ch1:
            st.plotly_chart(
                branch_score_bars(if_score, stat_score, rule_score),
                use_container_width=True,
                theme=None,
                config={"displayModeBar": False},
            )
        with ch2:
            st.plotly_chart(
                branch_score_radar(if_score, stat_score, rule_score),
                use_container_width=True,
                theme=None,
                config={"displayModeBar": False},
            )

        # ── Explanation + rule flags ──────────────────────────────────────────
        st.markdown("#### Explanation")
        st.info(row["explanation"])

        rule_flags = row["rule_flags"] if isinstance(row["rule_flags"], list) else []
        if rule_flags:
            st.markdown("**Triggered detection rules**")
            for flag in rule_flags:
                st.markdown(f"&nbsp;&nbsp;• `{flag}`")

        # ── Supporting events ─────────────────────────────────────────────────
        n_events  = int(row["n_supporting_events"])
        event_ids = row["supporting_event_ids"]
        if not isinstance(event_ids, list):
            event_ids = []
        st.markdown(f"**Supporting events:** {n_events}")
        if event_ids:
            with st.expander(f"Show {len(event_ids)} event IDs"):
                st.write(event_ids)

    # ── Investigation panel ───────────────────────────────────────────────────
    with col_inv:
        st.markdown("#### Investigation")
        current_status  = row["status"]  if row["status"]  in ["open", "investigating", "reviewed"] else "open"
        current_verdict = row["verdict"] if row["verdict"] in ["", "benign", "suspicious", "confirmed_threat", "inconclusive"] else ""

        st.markdown(f"Status: `{current_status}`")
        if current_verdict:
            st.markdown(f"Verdict: `{current_verdict}`")

        new_status = st.selectbox(
            "Update status",
            ["open", "investigating", "reviewed"],
            index=["open", "investigating", "reviewed"].index(current_status),
            key=f"status_{row['alert_id']}",
        )
        new_verdict = st.selectbox(
            "Verdict",
            ["", "confirmed_threat", "suspicious", "benign", "inconclusive"],
            index=["", "confirmed_threat", "suspicious", "benign", "inconclusive"].index(
                current_verdict if current_verdict in ["", "confirmed_threat", "suspicious", "benign", "inconclusive"] else ""
            ),
            key=f"verdict_{row['alert_id']}",
        )
        note = st.text_area(
            "Analyst note",
            value=row.get("analyst_note") or "",
            key=f"note_{row['alert_id']}",
        )

        if st.button("💾 Save", key=f"save_{row['alert_id']}"):
            idx = alerts_df[alerts_df["alert_id"] == row["alert_id"]].index[0]
            alerts_df.at[idx, "status"]       = new_status
            alerts_df.at[idx, "verdict"]      = new_verdict
            alerts_df.at[idx, "analyst_note"] = note
            state.set("alerts_df", alerts_df)
            st.success("✅ Investigation record updated.")
            st.rerun()

        # ── Ground-truth label (if available) ────────────────────────────────
        label = int(row.get("label", 0))
        if label == 1:
            st.markdown(
                '<div style="background:#1a2a1a;border:1px solid #3fb950;'
                'border-radius:6px;padding:8px 10px;margin-top:10px;'
                'font-size:12px;color:#3fb950;">✅ Ground-truth: Anomaly</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="background:#1a1a2a;border:1px solid #484f58;'
                'border-radius:6px;padding:8px 10px;margin-top:10px;'
                'font-size:12px;color:#8b949e;">Ground-truth: Normal</div>',
                unsafe_allow_html=True,
            )
