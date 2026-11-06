"""
ueba_app/utils/charts.py
-------------------------
Reusable Plotly chart builders.
All charts use a consistent dark-navy cybersecurity colour palette.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ── Colour palette ────────────────────────────────────────────────────────────
BG       = "#0d1117"
GRID     = "#21262d"
TEXT     = "#e6edf3"
ACCENT   = "#58a6ff"
SEVERITY_COLORS = {
    "Critical": "#ff4444",
    "High":     "#ff8c00",
    "Medium":   "#ffd700",
    "Low":      "#4caf50",
}
ACTIVITY_COLORS = {
    "logon":  "#58a6ff",
    "logoff": "#79c0ff",
    "file":   "#ffa657",
    "email":  "#d2a8ff",
    "web":    "#56d364",
    "device": "#ff7b72",
}

_LAYOUT = dict(
    paper_bgcolor=BG,
    plot_bgcolor=BG,
    font=dict(color=TEXT, family="Inter, sans-serif", size=11),
    margin=dict(l=36, r=16, t=36, b=36),
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
    legend=dict(font=dict(size=11)),
)

# Fixed chart heights — prevents Plotly from using its 450 px default
_H_WIDE  = 280   # timeline / bar charts that span 3 columns
_H_SMALL = 260   # donut / severity bar in the narrow column
_H_USERS = 300   # horizontal bar for top-users


def _apply(fig: go.Figure) -> go.Figure:
    fig.update_layout(**_LAYOUT)
    return fig


# ─────────────────────────────────────────────────────────────────────────────

def activity_over_time(events_df: pd.DataFrame) -> go.Figure:
    """Daily event volume stacked by activity type."""
    df = events_df.copy()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    agg = df.groupby(["date", "activity"]).size().reset_index(name="count")

    fig = px.bar(
        agg, x="date", y="count", color="activity",
        color_discrete_map=ACTIVITY_COLORS,
        title="Daily Activity Volume",
        labels={"date": "", "count": "Events", "activity": "Type"},
    )
    fig.update_layout(barmode="stack", legend_title_text="", height=_H_WIDE)
    return _apply(fig)


def event_type_pie(events_df: pd.DataFrame) -> go.Figure:
    counts = events_df["activity"].value_counts().reset_index()
    counts.columns = ["activity", "count"]
    fig = px.pie(
        counts, names="activity", values="count",
        color="activity", color_discrete_map=ACTIVITY_COLORS,
        title="Event Types",
        hole=0.45,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label",
                      textfont_size=10)
    fig.update_layout(height=_H_SMALL, showlegend=False,
                      margin=dict(l=10, r=10, t=36, b=10))
    return _apply(fig)


def severity_distribution(alerts_df: pd.DataFrame) -> go.Figure:
    order = ["Critical", "High", "Medium", "Low"]
    counts = (
        alerts_df["severity"]
        .value_counts()
        .reindex(order, fill_value=0)
        .reset_index()
    )
    counts.columns = ["severity", "count"]
    fig = px.bar(
        counts, x="severity", y="count",
        color="severity", color_discrete_map=SEVERITY_COLORS,
        title="Severity",
        labels={"severity": "", "count": "Alerts"},
    )
    fig.update_layout(showlegend=False, height=_H_SMALL,
                      margin=dict(l=36, r=10, t=36, b=30))
    return _apply(fig)


def top_users_by_risk(scored_df: pd.DataFrame, n: int = 10) -> go.Figure:
    top = (
        scored_df.groupby("user")["risk_score"]
        .max()
        .nlargest(n)
        .reset_index()
    )
    fig = px.bar(
        top, x="risk_score", y="user", orientation="h",
        color="risk_score",
        color_continuous_scale=[[0, "#4caf50"], [0.5, "#ffd700"], [1, "#ff4444"]],
        title=f"Top {n} Users by Peak Risk Score",
        labels={"risk_score": "Risk Score", "user": ""},
    )
    fig.update_layout(yaxis=dict(autorange="reversed"),
                      coloraxis_showscale=False, height=_H_USERS)
    return _apply(fig)


def alerts_over_time(alerts_df: pd.DataFrame) -> go.Figure:
    df = alerts_df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date
    agg = df.groupby(["date", "severity"]).size().reset_index(name="count")
    order = ["Critical", "High", "Medium", "Low"]
    fig = px.bar(
        agg, x="date", y="count", color="severity",
        color_discrete_map=SEVERITY_COLORS,
        category_orders={"severity": order},
        title="Alerts Over Time",
        labels={"date": "", "count": "Alerts", "severity": "Severity"},
    )
    fig.update_layout(barmode="stack", height=_H_WIDE, legend_title_text="")
    return _apply(fig)


def anomaly_score_histogram(scored_df: pd.DataFrame) -> go.Figure:
    fig = px.histogram(
        scored_df, x="anomaly_score", nbins=40,
        color_discrete_sequence=[ACCENT],
        title="Anomaly Score Distribution",
        labels={"anomaly_score": "Anomaly Score"},
    )
    fig.add_vline(x=0.45, line_dash="dash", line_color="#ff4444",
                  annotation_text="Threshold", annotation_position="top right")
    fig.update_layout(height=260)
    return _apply(fig)


def user_activity_timeline(events_df: pd.DataFrame, user: str) -> go.Figure:
    df = events_df[events_df["user"] == user].copy()
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    agg = df.groupby(["date", "activity"]).size().reset_index(name="count")
    fig = px.bar(
        agg, x="date", y="count", color="activity",
        color_discrete_map=ACTIVITY_COLORS,
        title=f"Activity Timeline — {user}",
        labels={"date": "", "count": "Events"},
    )
    fig.update_layout(barmode="stack", height=260, legend_title_text="")
    return _apply(fig)


def branch_score_bars(if_score: float, stat_score: float, rule_score: float) -> go.Figure:
    """Horizontal bar chart showing the three branch scores for one alert."""
    branches = ["Isolation Forest (45%)", "Statistical MAD (35%)", "Rule-Based (20%)"]
    scores   = [if_score, stat_score, rule_score]
    weights  = [0.45, 0.35, 0.20]
    colors   = ["#58a6ff", "#d2a8ff", "#ffa657"]
    contrib  = [round(s * w * 100, 1) for s, w in zip(scores, weights)]

    fig = go.Figure()
    for i, (branch, score, color, c) in enumerate(zip(branches, scores, colors, contrib)):
        fig.add_trace(go.Bar(
            x=[score], y=[branch], orientation="h",
            marker_color=color,
            text=f"{score:.3f}  ({c} pts)",
            textposition="outside",
            textfont=dict(color=TEXT, size=11),
            name=branch,
            showlegend=False,
        ))
    fig.update_layout(
        title=dict(text="Branch Score Breakdown", font=dict(size=13, color=TEXT)),
        xaxis=dict(range=[0, 1.25], gridcolor=GRID, zerolinecolor=GRID,
                   tickformat=".2f", title="Score (0–1)"),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(color=TEXT, family="Inter, sans-serif", size=11),
        margin=dict(l=10, r=80, t=40, b=30),
        height=200,
        barmode="overlay",
    )
    return fig


def branch_score_radar(if_score: float, stat_score: float, rule_score: float) -> go.Figure:
    """Radar / spider chart for the three branch scores."""
    categories = ["Isolation Forest", "Statistical MAD", "Rule-Based", "Isolation Forest"]
    values     = [if_score, stat_score, rule_score, if_score]  # close the polygon
    fig = go.Figure(go.Scatterpolar(
        r=values, theta=categories,
        fill="toself",
        fillcolor="rgba(88,166,255,0.15)",
        line=dict(color=ACCENT, width=2),
        marker=dict(color=ACCENT, size=6),
    ))
    fig.update_layout(
        polar=dict(
            bgcolor=BG,
            radialaxis=dict(
                visible=True, range=[0, 1],
                gridcolor=GRID, linecolor=GRID,
                tickfont=dict(color="#8b949e", size=9),
                tickvals=[0.25, 0.5, 0.75, 1.0],
            ),
            angularaxis=dict(
                gridcolor=GRID, linecolor=GRID,
                tickfont=dict(color=TEXT, size=11),
            ),
        ),
        paper_bgcolor=BG,
        font=dict(color=TEXT, family="Inter, sans-serif", size=11),
        margin=dict(l=30, r=30, t=40, b=30),
        height=260,
        showlegend=False,
        title=dict(text="Branch Scores", font=dict(size=13, color=TEXT)),
    )
    return fig


def branch_distributions(scored_df: pd.DataFrame) -> go.Figure:
    """Box plots of IF / stat / rule scores across all eval windows."""
    eval_df = scored_df[~scored_df["in_train"]].copy()
    rule_norm = (eval_df["n_rule_flags"] / 5.0).clip(0, 1)

    traces = [
        ("Isolation Forest", eval_df["if_score"],   "#58a6ff", "rgba(88,166,255,0.15)"),
        ("Statistical MAD",  eval_df["stat_score"],  "#d2a8ff", "rgba(210,168,255,0.15)"),
        ("Rule-Based",       rule_norm,              "#ffa657", "rgba(255,166,87,0.15)"),
    ]
    fig = go.Figure()
    for name, data, color, fill in traces:
        fig.add_trace(go.Box(
            y=data, name=name,
            marker_color=color,
            line_color=color,
            fillcolor=fill,
            boxmean=True,
            jitter=0.3,
            pointpos=0,
            marker=dict(size=3, opacity=0.4),
        ))
    fig.update_layout(
        title=dict(text="Branch Score Distributions — Evaluation Window",
                   font=dict(size=13, color=TEXT)),
        yaxis=dict(range=[0, 1.05], gridcolor=GRID, zerolinecolor=GRID,
                   title="Score (0–1)"),
        xaxis=dict(gridcolor=GRID),
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(color=TEXT, family="Inter, sans-serif", size=11),
        margin=dict(l=36, r=16, t=48, b=36),
        height=300,
        showlegend=False,
    )
    return fig


def branch_scatter(scored_df: pd.DataFrame) -> go.Figure:
    """IF score vs stat score scatter, coloured by anomaly flag."""
    eval_df = scored_df[~scored_df["in_train"]].copy()
    eval_df["anomaly_label"] = eval_df["is_anomaly"].map({True: "Anomaly", False: "Normal"})
    fig = px.scatter(
        eval_df, x="if_score", y="stat_score",
        color="anomaly_label",
        color_discrete_map={"Anomaly": "#ff4444", "Normal": "#58a6ff"},
        hover_data=["user", "risk_score"],
        labels={"if_score": "Isolation Forest Score",
                "stat_score": "Statistical MAD Score",
                "anomaly_label": ""},
        title="IF Score vs Statistical Score",
        opacity=0.7,
    )
    fig.update_traces(marker=dict(size=6))
    fig.update_layout(height=300, legend_title_text="")
    return _apply(fig)


def confusion_matrix_heatmap(cm: dict) -> go.Figure:
    matrix = cm["matrix"]
    labels = cm["labels"]
    # Annotate with count + percentage of total
    total = sum(v for row in matrix for v in row) or 1
    text = [[f"<b>{v}</b><br>{v/total*100:.1f}%" for v in row] for row in matrix]
    fig = go.Figure(go.Heatmap(
        z=matrix,
        x=[f"Predicted {l}" for l in labels],
        y=[f"Actual {l}" for l in labels],
        colorscale=[[0, "#0d1117"], [0.001, "#0d2a4a"], [0.5, "#1f6feb"], [1, "#58a6ff"]],
        text=text,
        texttemplate="%{text}",
        textfont=dict(size=16, color=TEXT),
        showscale=False,
        hoverongaps=False,
    ))
    fig.update_layout(
        title=dict(text="Confusion Matrix", font=dict(size=14, color=TEXT)),
        height=340,
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(color=TEXT, family="Inter, sans-serif", size=12),
        margin=dict(l=10, r=10, t=48, b=10),
        xaxis=dict(side="bottom", tickfont=dict(size=12), gridcolor=GRID),
        yaxis=dict(autorange="reversed", tickfont=dict(size=12), gridcolor=GRID),
    )
    return fig


def pr_curve_placeholder(pr_auc: float) -> go.Figure:
    """Semicircular gauge for PR-AUC."""
    val = round(pr_auc * 100, 1)
    if val >= 75:
        bar_color = "#4caf50"
    elif val >= 50:
        bar_color = "#ffd700"
    else:
        bar_color = "#ff4444"
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=val,
        number={"suffix": "%", "font": {"size": 36, "color": TEXT}},
        title={"text": "PR-AUC", "font": {"size": 14, "color": TEXT}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": TEXT, "tickfont": {"size": 11}},
            "bar":  {"color": bar_color, "thickness": 0.25},
            "bgcolor": GRID,
            "borderwidth": 0,
            "steps": [
                {"range": [0,  50], "color": "#1a0a0a"},
                {"range": [50, 75], "color": "#1a1500"},
                {"range": [75, 100], "color": "#0a1a0a"},
            ],
            "threshold": {
                "line": {"color": TEXT, "width": 2},
                "thickness": 0.75,
                "value": val,
            },
        },
    ))
    fig.update_layout(
        paper_bgcolor=BG,
        font=dict(color=TEXT, family="Inter, sans-serif"),
        margin=dict(l=20, r=20, t=60, b=20),
        height=340,
    )
    return fig
