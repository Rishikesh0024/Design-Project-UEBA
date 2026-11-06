"""
tests/test_pipeline.py
-----------------------
Tests for: loader, feature extraction, detector, scorer, evaluation.
Uses a small reproducible in-memory dataset — no external files required.
"""

from __future__ import annotations

import io
import textwrap
from datetime import date

import numpy as np
import pandas as pd
import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_csv(rows: str) -> io.BytesIO:
    return io.BytesIO(textwrap.dedent(rows).strip().encode())


MINIMAL_CSV = """
id,date,user,pc,activity,resource,label
E0000001,01/02/2024 09:00:00,u001,PC-001,Logon,,0
E0000002,01/02/2024 09:30:00,u001,PC-001,File,/docs/a.txt,0
E0000003,01/02/2024 10:00:00,u001,PC-001,Email,colleague@co.com,0
E0000004,01/02/2024 22:00:00,u002,PC-002,Logon,,1
E0000005,01/02/2024 22:30:00,u002,PC-002,File,/sensitive/x.docx,1
E0000006,01/03/2024 09:00:00,u001,PC-001,Logon,,0
E0000007,01/03/2024 09:15:00,u001,PC-001,WWW,http://intranet/,0
E0000008,01/03/2024 23:00:00,u002,PC-002,Device,USB_1,1
"""

BAD_TS_CSV = """
id,date,user,pc,activity
E0000001,NOT_A_DATE,u001,PC-001,Logon
E0000002,01/02/2024 09:00:00,u001,PC-001,File
"""

MISSING_COL_CSV = """
id,date,pc,activity
E0000001,01/02/2024 09:00:00,PC-001,Logon
"""


# ═════════════════════════════════════════════════════════════════════════════
# Module 1 — Loader
# ═════════════════════════════════════════════════════════════════════════════

class TestLoader:
    def test_loads_valid_csv(self):
        from ueba_app.data.loader import load_csv
        df, summary = load_csv(_make_csv(MINIMAL_CSV))
        assert len(df) == 8
        assert summary["unique_users"] == 2
        assert summary["valid_rows"] == 8
        assert summary["skipped_count"] == 0

    def test_canonical_columns_present(self):
        from ueba_app.data.loader import load_csv
        df, _ = load_csv(_make_csv(MINIMAL_CSV))
        for col in ["event_id", "timestamp", "user", "activity"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_timestamps_are_utc_aware(self):
        from ueba_app.data.loader import load_csv
        df, _ = load_csv(_make_csv(MINIMAL_CSV))
        assert df["timestamp"].dt.tz is not None

    def test_chronological_sort(self):
        from ueba_app.data.loader import load_csv
        df, _ = load_csv(_make_csv(MINIMAL_CSV))
        assert df["timestamp"].is_monotonic_increasing

    def test_bad_timestamp_skipped_with_reason(self):
        from ueba_app.data.loader import load_csv
        df, summary = load_csv(_make_csv(BAD_TS_CSV))
        assert summary["skipped_count"] == 1
        assert len(summary["skipped_sample"]) == 1
        assert "unparseable" in summary["skipped_sample"][0]["reason"]

    def test_missing_required_column_raises(self):
        from ueba_app.data.loader import load_csv
        with pytest.raises(ValueError, match="Required columns not found"):
            load_csv(_make_csv(MISSING_COL_CSV))

    def test_event_type_normalisation(self):
        from ueba_app.data.loader import load_csv
        df, _ = load_csv(_make_csv(MINIMAL_CSV))
        assert "web" in df["activity"].values   # WWW → web
        assert "logon" in df["activity"].values

    def test_label_column_preserved(self):
        from ueba_app.data.loader import load_csv
        df, summary = load_csv(_make_csv(MINIMAL_CSV))
        assert "label" in df.columns
        assert df["label"].sum() > 0
        assert summary["has_labels"] is True

    def test_original_event_ids_preserved(self):
        from ueba_app.data.loader import load_csv
        df, _ = load_csv(_make_csv(MINIMAL_CSV))
        assert df["event_id"].iloc[0] == "E0000001"

    def test_user_mapping_override(self):
        csv = _make_csv("""
employee,event_time,machine,event_type
u001,01/02/2024 09:00:00,PC-001,Logon
u001,01/02/2024 10:00:00,PC-001,File
""")
        from ueba_app.data.loader import load_csv
        df, _ = load_csv(csv, user_mapping={
            "user": "employee", "timestamp": "event_time",
            "activity": "event_type", "pc": "machine",
        })
        assert len(df) == 2
        assert "u001" in df["user"].values


# ═════════════════════════════════════════════════════════════════════════════
# Module 2 — Feature extraction
# ═════════════════════════════════════════════════════════════════════════════

class TestFeatures:
    @pytest.fixture
    def events(self):
        from ueba_app.data.loader import load_csv
        df, _ = load_csv(_make_csv(MINIMAL_CSV))
        return df

    def test_daily_features_shape(self, events):
        from ueba_app.data.features import extract_features
        daily, baselines = extract_features(events)
        assert len(daily) > 0
        assert "user" in daily.columns
        assert "date" in daily.columns

    def test_no_future_leakage(self, events):
        from ueba_app.data.features import extract_features
        all_dates = sorted(events["date"].unique())
        train_end = all_dates[0]   # only first day is training
        daily, _ = extract_features(events, train_end_date=train_end)
        # new_resources must be 0 for training rows
        train_rows = daily[daily["in_train"]]
        assert (train_rows["new_resources"] == 0).all()

    def test_after_hours_count(self, events):
        from ueba_app.data.features import extract_features
        daily, _ = extract_features(events)
        # u002 has events at 22:00 and 23:00 — should have after_hours_count > 0
        u2 = daily[daily["user"] == "u002"]
        assert u2["after_hours_count"].sum() > 0

    def test_baseline_computed_for_all_users(self, events):
        from ueba_app.data.features import extract_features
        _, baselines = extract_features(events)
        assert set(baselines["user"]) == set(events["user"].unique())

    def test_deviation_columns_present(self, events):
        from ueba_app.data.features import extract_features, FEATURE_COLS
        daily, _ = extract_features(events)
        for feat in FEATURE_COLS:
            assert f"{feat}_dev" in daily.columns, f"Missing deviation: {feat}_dev"


# ═════════════════════════════════════════════════════════════════════════════
# Module 3 — Detector
# ═════════════════════════════════════════════════════════════════════════════

class TestDetector:
    @pytest.fixture
    def daily_and_baselines(self):
        from ueba_app.data.loader import load_csv
        from ueba_app.data.features import extract_features
        # Use demo data for a more realistic test
        from pathlib import Path
        demo = Path(__file__).parent / "../demo_data/demo_events.csv"
        df, _ = load_csv(demo)
        return extract_features(df)

    def test_fit_and_score(self, daily_and_baselines):
        from ueba_app.models.detector import UEBADetector
        daily, _ = daily_and_baselines
        det = UEBADetector()
        det.fit(daily)
        scored = det.score(daily)
        assert "if_score" in scored.columns
        assert "anomaly_score" in scored.columns
        assert "is_anomaly" in scored.columns

    def test_scores_in_range(self, daily_and_baselines):
        from ueba_app.models.detector import UEBADetector
        daily, _ = daily_and_baselines
        det = UEBADetector()
        det.fit(daily)
        scored = det.score(daily)
        assert scored["if_score"].between(0, 1).all()
        assert scored["anomaly_score"].between(0, 1).all()

    def test_training_only_fit(self, daily_and_baselines):
        """Detector must not use eval rows during fit."""
        from ueba_app.models.detector import UEBADetector
        daily, _ = daily_and_baselines
        det = UEBADetector()
        # Manually mark all rows as eval — fit should raise
        daily_eval = daily.copy()
        daily_eval["in_train"] = False
        with pytest.raises(ValueError, match="No training rows"):
            det.fit(daily_eval)

    def test_rule_flags_list(self, daily_and_baselines):
        from ueba_app.models.detector import UEBADetector
        daily, _ = daily_and_baselines
        det = UEBADetector()
        det.fit(daily)
        scored = det.score(daily)
        assert scored["rule_flags"].apply(lambda x: isinstance(x, list)).all()

    def test_model_persistence(self, daily_and_baselines, tmp_path):
        from ueba_app.models.detector import UEBADetector
        import ueba_app.models.detector as det_mod
        original_dir = det_mod.MODEL_DIR
        det_mod.MODEL_DIR = tmp_path
        try:
            daily, _ = daily_and_baselines
            det = UEBADetector()
            det.fit(daily)
            det.save("test_model")
            loaded = UEBADetector.load("test_model")
            scored = loaded.score(daily)
            assert "anomaly_score" in scored.columns
        finally:
            det_mod.MODEL_DIR = original_dir


# ═════════════════════════════════════════════════════════════════════════════
# Module 4 — Risk scorer
# ═════════════════════════════════════════════════════════════════════════════

class TestScorer:
    @pytest.fixture
    def scored_df(self):
        from ueba_app.data.loader import load_csv
        from ueba_app.data.features import extract_features
        from ueba_app.models.detector import UEBADetector
        from ueba_app.models.scorer import compute_risk_scores
        from pathlib import Path
        demo = Path(__file__).parent / "../demo_data/demo_events.csv"
        df, _ = load_csv(demo)
        daily, baselines = extract_features(df)
        det = UEBADetector()
        det.fit(daily)
        scored = det.score(daily)
        return compute_risk_scores(scored), baselines, df

    def test_risk_score_range(self, scored_df):
        scored, _, _ = scored_df
        assert scored["risk_score"].between(0, 100).all()

    def test_severity_categories(self, scored_df):
        scored, _, _ = scored_df
        valid = {"Critical", "High", "Medium", "Low"}
        assert set(scored["severity"].unique()).issubset(valid)

    def test_alerts_generated(self, scored_df):
        from ueba_app.models.scorer import generate_alerts
        scored, baselines, events = scored_df
        alerts = generate_alerts(scored, events, baselines)
        assert len(alerts) > 0
        assert "explanation" in alerts.columns
        assert "risk_score" in alerts.columns

    def test_explanation_not_empty(self, scored_df):
        from ueba_app.models.scorer import generate_alerts
        scored, baselines, events = scored_df
        alerts = generate_alerts(scored, events, baselines)
        assert alerts["explanation"].str.len().gt(20).all()

    def test_no_duplicate_alerts(self, scored_df):
        from ueba_app.models.scorer import generate_alerts
        scored, baselines, events = scored_df
        alerts = generate_alerts(scored, events, baselines)
        dupes = alerts.duplicated(subset=["user", "date", "primary_activity"])
        assert not dupes.any()


# ═════════════════════════════════════════════════════════════════════════════
# Module 5 — Evaluation
# ═════════════════════════════════════════════════════════════════════════════

class TestEvaluation:
    @pytest.fixture
    def full_scored(self):
        from ueba_app.data.loader import load_csv
        from ueba_app.data.features import extract_features
        from ueba_app.models.detector import UEBADetector
        from ueba_app.models.scorer import compute_risk_scores
        from pathlib import Path
        demo = Path(__file__).parent / "../demo_data/demo_events.csv"
        df, _ = load_csv(demo)
        daily, _ = extract_features(df)
        det = UEBADetector()
        det.fit(daily)
        scored = det.score(daily)
        return compute_risk_scores(scored)

    def test_metrics_with_labels(self, full_scored):
        from ueba_app.models.evaluation import evaluate
        results = evaluate(full_scored)
        assert results["has_labels"] is True
        m = results["metrics"]
        assert 0.0 <= m["precision"] <= 1.0
        assert 0.0 <= m["recall"]    <= 1.0
        assert 0.0 <= m["f1_score"]  <= 1.0
        assert 0.0 <= m["false_positive_rate"] <= 1.0

    def test_confusion_matrix_shape(self, full_scored):
        from ueba_app.models.evaluation import evaluate
        results = evaluate(full_scored)
        cm = results["confusion_matrix"]["matrix"]
        assert len(cm) == 2 and len(cm[0]) == 2

    def test_no_label_leakage(self, full_scored):
        """Training rows must not appear in evaluation."""
        from ueba_app.models.evaluation import evaluate
        # Patch: mark all as training — should return no eval rows
        all_train = full_scored.copy()
        all_train["in_train"] = True
        results = evaluate(all_train)
        assert "error" in results or results.get("has_labels") is False
