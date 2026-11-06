"""pages/detection.py — Run anomaly detection and inspect results."""

from __future__ import annotations
import traceback
import pandas as pd
import streamlit as st

from ueba_app.data.features import extract_features
from ueba_app.models.detector import UEBADetector
from ueba_app.models.scorer import compute_risk_scores, generate_alerts
from ueba_app.models.evaluation import evaluate
from ueba_app.utils import state
from ueba_app.utils.charts import anomaly_score_histogram


def render() -> None:
    st.title("🔍 Anomaly Detection")

    if not state.pipeline_ready():
        st.info("Load a dataset first (Dataset page).")
        return

    _config_panel()

    if state.detection_ready():
        st.divider()
        _results_panel()


def _config_panel() -> None:
    st.subheader("Detection Configuration")

    col1, col2, col3 = st.columns(3)
    contamination = col1.slider(
        "Expected anomaly fraction", 0.01, 0.20, 0.05, 0.01,
        help="IsolationForest contamination parameter.",
    )
    train_pct = col2.slider(
        "Training window (%)", 50, 85, 70, 5,
        help="Percentage of chronological data used for training.",
    )
    min_risk = col3.slider(
        "Minimum risk score for alert", 10, 60, 25, 5,
        help="Windows below this score are not surfaced as alerts.",
    )

    st.markdown("**Rule thresholds**")
    rc1, rc2, rc3 = st.columns(3)
    ah_thresh      = rc1.number_input("After-hours ratio >",  0.0,  1.0,  0.5,  0.05)
    dev_thresh     = rc2.number_input("File/web deviation >", 1.0, 10.0,  3.0,  0.5)
    new_res_thresh = rc3.number_input("New resources ≥",      1,    20,    5,    1)

    if st.button("▶ Run Detection Pipeline", type="primary"):
        _run_pipeline(
            contamination, train_pct / 100.0, float(min_risk),
            float(ah_thresh), float(dev_thresh), int(new_res_thresh),
        )


def _run_pipeline(
    contamination: float,
    train_frac: float,
    min_risk: float,
    ah_thresh: float,
    dev_thresh: float,
    new_res_thresh: int,
) -> None:
    events_df = state.get("events_df")
    users_df  = state.get("users_df")

    progress = st.progress(0, text="Starting…")

    try:
        progress.progress(10, text="Extracting features…")
        all_dates = sorted(events_df["date"].unique())
        split_idx = max(1, int(len(all_dates) * train_frac))
        train_end = all_dates[split_idx - 1]
        daily, baselines = extract_features(events_df, users_df, train_end_date=train_end)

        # Write to session_state directly — avoids any wrapper timing issues
        st.session_state["daily_df"]     = daily
        st.session_state["baselines_df"] = baselines

        progress.progress(35, text="Training Isolation Forest…")
        rules = {
            "after_hours_ratio_threshold": ah_thresh,
            "file_count_dev_threshold":    dev_thresh,
            "web_count_dev_threshold":     dev_thresh,
            "new_resources_threshold":     new_res_thresh,
        }
        detector = UEBADetector(rules=rules)
        detector.model.contamination = contamination
        detector.fit(daily)
        detector.save()
        st.session_state["detector"] = detector

        progress.progress(60, text="Scoring all windows…")
        scored = detector.score(daily)
        scored = compute_risk_scores(scored)
        st.session_state["scored_df"] = scored

        progress.progress(80, text="Generating alerts…")
        alerts = generate_alerts(scored, events_df, baselines, min_risk=min_risk)
        st.session_state["alerts_df"] = alerts

        progress.progress(95, text="Evaluating…")
        eval_results = evaluate(scored)
        st.session_state["eval_results"] = eval_results

        progress.progress(100, text="Done.")

        n_anomalies = int(scored["is_anomaly"].sum())
        n_alerts    = len(alerts)
        st.success(
            f"✅ Detection complete — **{n_anomalies}** anomalous windows, "
            f"**{n_alerts}** alerts generated. "
            f"Navigate to **Alerts** or **Evaluation** in the sidebar."
        )

    except Exception as exc:
        progress.empty()
        st.error(f"❌ Detection failed: {exc}")
        with st.expander("Full traceback"):
            st.code(traceback.format_exc())


def _results_panel() -> None:
    scored_df = state.get("scored_df")
    st.subheader("Detection Results")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Windows scored",    f"{len(scored_df):,}")
    c2.metric("Training windows",  f"{int(scored_df['in_train'].sum()):,}")
    c3.metric("Eval windows",      f"{int((~scored_df['in_train']).sum()):,}")
    c4.metric("Anomalies flagged", f"{int(scored_df['is_anomaly'].sum()):,}")

    st.plotly_chart(
        anomaly_score_histogram(scored_df),
        use_container_width=True,
        theme=None,
        config={"displayModeBar": False},
    )

    st.subheader("Scored Windows (evaluation period)")
    eval_df = scored_df[~scored_df["in_train"]].copy()
    display_cols = [c for c in [
        "user", "date", "total_events", "logon_count", "file_count",
        "device_count", "after_hours_ratio", "if_score", "stat_score",
        "anomaly_score", "risk_score", "severity", "is_anomaly", "label",
    ] if c in eval_df.columns]

    st.dataframe(
        eval_df[display_cols].sort_values("risk_score", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
