"""pages/evaluation.py — Detection metrics and model evaluation."""

from __future__ import annotations
import pandas as pd
import streamlit as st

from ueba_app.utils import state
from ueba_app.utils.charts import (
    confusion_matrix_heatmap, pr_curve_placeholder,
    branch_distributions, branch_scatter,
)

_CARD_CSS = """
<style>
.eval-metric-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 14px 10px 10px 10px;
    text-align: center;
    min-height: 80px;
}
.eval-metric-label {
    font-size: 11px;
    color: #8b949e;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
}
.eval-metric-value {
    font-size: 26px;
    font-weight: 700;
    color: #e6edf3;
    line-height: 1.1;
}
.eval-metric-value.accent { color: #58a6ff; }
.eval-metric-value.green  { color: #4caf50; }
.eval-metric-value.yellow { color: #ffd700; }
.eval-metric-value.red    { color: #ff4444; }
.sev-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    margin: 2px 4px;
}
</style>
"""

_SEV_COLORS = {
    "Critical": ("#ff4444", "#2a0a0a"),
    "High":     ("#ff8c00", "#2a1500"),
    "Medium":   ("#ffd700", "#2a2200"),
    "Low":      ("#4caf50", "#0a2a0a"),
}


def _card(label: str, value: str, css_class: str = "") -> str:
    return (
        f'<div class="eval-metric-card">'
        f'<div class="eval-metric-label">{label}</div>'
        f'<div class="eval-metric-value {css_class}">{value}</div>'
        f'</div>'
    )


def render() -> None:
    st.markdown(_CARD_CSS, unsafe_allow_html=True)
    st.title("📊 Evaluation")

    if not state.detection_ready():
        st.info("Run **Anomaly Detection** first.")
        return

    results = state.get("eval_results")
    scored  = state.get("scored_df")

    if results is None:
        st.warning("Evaluation results not available.")
        return

    with st.expander("ℹ️ Evaluation methodology"):
        st.markdown("""
**Chronological split** — the training window uses the first N% of dates;
evaluation uses the remaining dates. No future data leaks into training.

**Unit of analysis** — one (user, date) window per user per active day.
A window is labelled positive if any event in it carries `label == 1`.

**Risk score** is a prioritization ranking (0–100), not a calibrated
probability of malicious intent.

**Limitations** — the synthetic demo dataset has planted anomalies that
are somewhat idealized. Real-world performance will differ.
        """)

    # ── No labels path ────────────────────────────────────────────────────────
    if not results.get("has_labels"):
        st.warning(results.get("note", "No ground-truth labels available."))
        _descriptive_panel(results.get("descriptive", {}))
        return

    m = results["metrics"]

    # ── Row 1: ratio metrics ──────────────────────────────────────────────────
    st.markdown("### Detection Metrics — Evaluation Window")
    cols = st.columns(4)
    cards = [
        ("Precision",           f"{m['precision']:.3f}",           "accent"),
        ("Recall",              f"{m['recall']:.3f}",              "green"),
        ("F1-Score",            f"{m['f1_score']:.3f}",            "accent"),
        ("False-Positive Rate", f"{m['false_positive_rate']:.3f}", "yellow"),
    ]
    for col, (label, value, cls) in zip(cols, cards):
        col.markdown(_card(label, value, cls), unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Row 2: count metrics ──────────────────────────────────────────────────
    cols2 = st.columns(4)
    count_cards = [
        ("True Positives",  str(m["true_positives"]),  "green"),
        ("False Positives", str(m["false_positives"]), "red"),
        ("True Negatives",  str(m["true_negatives"]),  "green"),
        ("False Negatives", str(m["false_negatives"]), "yellow"),
    ]
    for col, (label, value, cls) in zip(cols2, count_cards):
        col.markdown(_card(label, value, cls), unsafe_allow_html=True)

    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Confusion matrix + PR-AUC gauge ──────────────────────────────────────
    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.plotly_chart(
            confusion_matrix_heatmap(results["confusion_matrix"]),
            use_container_width=True,
            theme=None,
            height=340,
            config={"displayModeBar": False},
        )
    with col_r:
        st.plotly_chart(
            pr_curve_placeholder(m["pr_auc"]),
            use_container_width=True,
            theme=None,
            height=340,
            config={"displayModeBar": False},
        )

    st.divider()
    _descriptive_panel(results.get("descriptive", {}))

    # ── Branch score analysis ─────────────────────────────────────────────────
    st.divider()
    st.markdown("### Branch Score Analysis — Evaluation Window")
    st.caption(
        "How each of the three detection branches contributed across all "
        "evaluation windows. Anomalous windows are shown in red in the scatter plot."
    )
    ba_col1, ba_col2 = st.columns([1, 1])
    with ba_col1:
        st.plotly_chart(
            branch_distributions(scored),
            use_container_width=True,
            theme=None,
            config={"displayModeBar": False},
        )
    with ba_col2:
        st.plotly_chart(
            branch_scatter(scored),
            use_container_width=True,
            theme=None,
            config={"displayModeBar": False},
        )

    # ── Branch weight contribution table ─────────────────────────────────────
    eval_df = scored[~scored["in_train"]].copy()
    rule_norm = (eval_df["n_rule_flags"] / 5.0).clip(0, 1)
    branch_summary = pd.DataFrame({
        "Branch":        ["Isolation Forest", "Statistical MAD", "Rule-Based"],
        "Weight":        ["45%", "35%", "20%"],
        "Mean Score":    [
            f"{eval_df['if_score'].mean():.3f}",
            f"{eval_df['stat_score'].mean():.3f}",
            f"{rule_norm.mean():.3f}",
        ],
        "Max Score":     [
            f"{eval_df['if_score'].max():.3f}",
            f"{eval_df['stat_score'].max():.3f}",
            f"{rule_norm.max():.3f}",
        ],
        "Mean Contribution (pts)": [
            f"{eval_df['if_score'].mean() * 0.45 * 100:.1f}",
            f"{eval_df['stat_score'].mean() * 0.35 * 100:.1f}",
            f"{rule_norm.mean() * 0.20 * 100:.1f}",
        ],
    })
    st.dataframe(branch_summary, use_container_width=True, hide_index=True)

    st.divider()

    # ── Per-user breakdown ────────────────────────────────────────────────────
    st.markdown("### Per-User Anomaly Summary — Evaluation Window")
    eval_df = scored[~scored["in_train"]].copy()
    eval_df["rule_score"] = (eval_df["n_rule_flags"] / 5.0).clip(0, 1)

    agg_kwargs = dict(
        mean_risk=("risk_score", "mean"),
        mean_if=("if_score", "mean"),
        mean_stat=("stat_score", "mean"),
        mean_rule=("rule_score", "mean"),
        anomaly_days=("is_anomaly", "sum"),
        total_days=("date", "count"),
    )
    if "label" in eval_df.columns:
        agg_kwargs["label_days"] = ("label", "sum")

    summary = (
        eval_df.groupby("user")
        .agg(**agg_kwargs)
        .reset_index()
        .sort_values("mean_risk", ascending=False)
    )
    for col in ["mean_risk", "mean_if", "mean_stat", "mean_rule"]:
        summary[col] = summary[col].round(3)

    rename = {
        "user":        "User",
        "mean_risk":   "Mean Risk",
        "mean_if":     "IF Score",
        "mean_stat":   "Stat Score",
        "mean_rule":   "Rule Score",
        "anomaly_days": "Anomaly Days",
        "total_days":  "Total Days",
        "label_days":  "Labelled Days",
    }
    summary = summary.rename(columns={k: v for k, v in rename.items() if k in summary.columns})

    st.dataframe(
        summary, use_container_width=True, hide_index=True,
        column_config={
            "Mean Risk":  st.column_config.ProgressColumn("Mean Risk",  min_value=0, max_value=100, format="%.1f"),
            "IF Score":   st.column_config.ProgressColumn("IF Score",   min_value=0, max_value=1,   format="%.3f"),
            "Stat Score": st.column_config.ProgressColumn("Stat Score", min_value=0, max_value=1,   format="%.3f"),
            "Rule Score": st.column_config.ProgressColumn("Rule Score", min_value=0, max_value=1,   format="%.3f"),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────

def _descriptive_panel(desc: dict) -> None:
    if not desc:
        return
    st.markdown("### Descriptive Anomaly Statistics")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(_card("Windows Evaluated",   str(desc.get("total_windows", "—")),    "accent"), unsafe_allow_html=True)
    c2.markdown(_card("Anomalies Flagged",   str(desc.get("anomalies_flagged", "—")), "red"),   unsafe_allow_html=True)
    c3.markdown(_card("Anomaly Rate",        f"{desc.get('anomaly_rate', 0) * 100:.1f}%", "yellow"), unsafe_allow_html=True)
    c4.markdown(_card("Mean Risk Score",     str(desc.get("risk_score_mean", "—")),  "accent"), unsafe_allow_html=True)
    c5.markdown(_card("95th-pct Risk Score", str(desc.get("risk_score_p95",  "—")),  "accent"), unsafe_allow_html=True)

    sev = desc.get("severity_counts", {})
    if sev:
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        st.markdown("**Severity Breakdown**")
        order = ["Critical", "High", "Medium", "Low"]
        badges = ""
        for s in order:
            cnt = sev.get(s, 0)
            fg, bg = _SEV_COLORS.get(s, ("#e6edf3", "#21262d"))
            badges += (
                f'<span class="sev-badge" style="color:{fg};background:{bg};border:1px solid {fg}33">'
                f'{s}: {cnt}</span>'
            )
        st.markdown(badges, unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
