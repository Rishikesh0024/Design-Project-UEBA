import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { ChevronLeft, ChevronRight, Save, ShieldAlert } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type Alert } from "../api/client";
import { Card, EmptyState, ErrorMessage, formatDate, Loading, PageHeader } from "../components/common";

type Severity = "critical" | "high" | "medium" | "low";
type Review = { id: number; status: string; verdict: string | null; note: string | null; reviewed_at: string };
type AlertSummary = {
  total_alerts: number;
  average_risk_score: number;
  severity_counts: Record<Severity, number>;
  score_distribution: { range: string; count: number }[];
};
type Investigation = {
  alert: Alert;
  entity: {
    user_id: string;
    role: string | null;
    department: string | null;
    total_events: number | null;
    baseline: Record<string, unknown> | null;
  };
  fusion_weights: Record<string, number> | null;
  reviews: Review[];
};

const riskLevels: { key: Severity; label: string; color: string }[] = [
  { key: "critical", label: "Critical", color: "#d95063" },
  { key: "high", label: "High", color: "#dc8b3c" },
  { key: "medium", label: "Medium", color: "#d1a132" },
  { key: "low", label: "Low", color: "#2da87b" },
];
const PAGE_SIZE = 20;

function toQueryDate(value: string): string {
  return value ? new Date(value).toISOString() : "";
}

function exportInvestigation(alert: Alert) {
  document.getElementById(`alert-investigation-${alert.id}`)?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
  window.history.replaceState(null, "", `/alerts#investigation-${alert.id}`);
}

export default function AlertsPage({ datasetId }: { datasetId: number | null }) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [userSearch, setUserSearch] = useState("");
  const [alertSearch, setAlertSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(0);
  const [reviewStatus, setReviewStatus] = useState("investigating");
  const [verdict, setVerdict] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    if (!datasetId) {
      setAlerts([]);
      setSummary(null);
      setTotal(0);
      setSelectedId(null);
      return () => { active = false; };
    }
    setLoading(true);
    setError("");
    const filterParams = new URLSearchParams({ dataset_id: String(datasetId) });
    const start = toQueryDate(dateFrom);
    const end = toQueryDate(dateTo);
    if (start) filterParams.set("date_from", start);
    if (end) filterParams.set("date_to", end);
    const params = new URLSearchParams(filterParams);
    if (severity) params.set("severity", severity);
    if (status) params.set("status", status);
    if (userSearch.trim()) params.set("user_id", userSearch.trim());
    if (alertSearch.trim()) params.set("alert_id", alertSearch.trim());
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(page * PAGE_SIZE));
    Promise.all([
      api<AlertSummary>(`/alerts/summary?${filterParams}`),
      api<{ items: Alert[]; total: number }>(`/alerts/paged?${params}`),
    ]).then(([nextSummary, response]) => {
      if (!active) return;
      setSummary(nextSummary);
      setAlerts(response.items);
      setTotal(response.total);
      setSelectedId((previous) =>
        response.items.some((alert) => alert.id === previous)
          ? previous
          : response.items[0]?.id ?? null,
      );
    }).catch((reason: Error) => {
      if (active) setError(reason.message);
    }).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [datasetId, severity, status, userSearch, alertSearch, dateFrom, dateTo, page]);

  const selected = alerts.find((alert) => alert.id === selectedId) ?? null;

  useEffect(() => {
    let active = true;
    if (!selected) {
      setInvestigation(null);
      return () => { active = false; };
    }
    setReviewStatus(selected.status);
    setVerdict(selected.verdict ?? "");
    setNote("");
    api<Investigation>(`/alerts/${selected.id}/investigation`)
      .then((detail) => active && setInvestigation(detail))
      .catch((reason: Error) => active && setError(reason.message));
    return () => { active = false; };
  }, [selectedId]);

  const distribution = useMemo(
    () => riskLevels.map(({ key, label, color }) => ({
      name: label,
      value: summary?.severity_counts[key] ?? 0,
      color,
    })),
    [summary],
  );
  const pageCount = Math.ceil(total / PAGE_SIZE);

  async function saveReview() {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      await api<Alert>(`/alerts/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          status: reviewStatus,
          verdict: verdict || null,
          note: note.trim() || null,
        }),
      });
      setNote("");
      const detail = await api<Investigation>(`/alerts/${selected.id}/investigation`);
      setInvestigation(detail);
      setAlerts((current) => current.map((alert) => alert.id === selected.id
        ? { ...alert, status: reviewStatus, verdict: verdict || null }
        : alert));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save analyst review.");
    } finally {
      setSaving(false);
    }
  }

  if (!datasetId) {
    return <><PageHeader title="Alerts" description="Prioritize, review, and investigate risk events." /><Card><EmptyState title="Select a dataset" message="Alerts are associated with a completed detection run." /></Card></>;
  }

  return (
    <>
      <PageHeader
        eyebrow="THREAT INVESTIGATION"
        title="Alerts"
        description="Review observed risk, ranked findings, branch evidence, thresholds, and analyst decisions."
        actions={<span className="total-alerts"><ShieldAlert size={16} />{total.toLocaleString()} matching alerts</span>}
      />
      {error && <ErrorMessage>{error}</ErrorMessage>}

      <Card title="Risk score overview" description="Persisted alert scores for the selected dataset and time range. Select a risk card to filter the ranked alerts.">
        <div className="filter-toolbar alert-date-filters">
          <label className="field-label">From<input aria-label="Overview start date" type="datetime-local" value={dateFrom} onChange={(event) => { setDateFrom(event.target.value); setPage(0); }} /></label>
          <label className="field-label">To<input aria-label="Overview end date" type="datetime-local" value={dateTo} onChange={(event) => { setDateTo(event.target.value); setPage(0); }} /></label>
          <label className="field-label">Risk level
            <select value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(0); }}>
              <option value="">All risk levels</option>
              {riskLevels.map(({ key, label }) => <option value={key} key={key}>{label}</option>)}
            </select>
          </label>
          <button className="button subtle" onClick={() => { setDateFrom(""); setDateTo(""); setSeverity(""); setPage(0); }}>Clear filters</button>
        </div>
        <div className="metric-grid alert-risk-kpis">
          <button className="card alert-risk-card overall" onClick={() => setSeverity("")}>
            <span>Overall Risk Score · average</span>
            <strong>{summary?.average_risk_score.toFixed(1) ?? "0.0"}</strong>
            <small>{summary?.total_alerts.toLocaleString() ?? "0"} persisted alerts</small>
          </button>
          {riskLevels.map(({ key, label, color }) => (
            <button
              className={`card alert-risk-card ${key}${severity === key ? " active" : ""}`}
              key={key}
              onClick={() => { setSeverity(severity === key ? "" : key); setPage(0); }}
              style={{ "--risk-color": color } as CSSProperties}
            >
              <span>{label} Risk Alerts</span>
              <strong>{(summary?.severity_counts[key] ?? 0).toLocaleString()}</strong>
              <small>Risk level · select to filter</small>
            </button>
          ))}
        </div>
        <div className="dashboard-grid alert-overview-charts">
          <Card title="Risk level distribution" description="Alert counts grouped by persisted detection severity">
            <div className="chart-wrap donut-wrap">
              {summary?.total_alerts ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={distribution} dataKey="value" nameKey="name" innerRadius={56} outerRadius={82} paddingAngle={3}>
                      {distribution.map((item) => <Cell key={item.name} fill={item.color} />)}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : <div className="chart-empty">No alert results for this time range.</div>}
            </div>
            <div className="risk-legend">{distribution.map((item) => <button key={item.name} onClick={() => { setSeverity(item.name.toLowerCase()); setPage(0); }}><i style={{ background: item.color }} />{item.name}<strong>{item.value.toLocaleString()}</strong></button>)}</div>
          </Card>
          <Card title="Score distribution" description="Observed combined risk scores, grouped in 25-point ranges">
            <div className="chart-wrap">
              {summary?.total_alerts ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={summary.score_distribution} margin={{ left: -18, right: 6, top: 10 }}>
                    <CartesianGrid stroke="#edf1f7" vertical={false} />
                    <XAxis dataKey="range" tickLine={false} axisLine={false} tick={{ fill: "#8290a5", fontSize: 11 }} />
                    <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: "#8290a5", fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" name="Alerts" fill="#527cf1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : <div className="chart-empty">Run detection to view observed score distribution.</div>}
            </div>
          </Card>
        </div>
      </Card>

      <Card title="Ranked security alerts" description="Highest combined risk first. Search, filter, paginate, or open an investigation.">
        <div className="filter-toolbar alert-filter-toolbar">
          <label className="search-field"><input aria-label="Search user or entity" value={userSearch} onChange={(event) => { setUserSearch(event.target.value); setPage(0); }} placeholder="Search user / entity ID…" /></label>
          <label className="search-field"><input aria-label="Search alert ID" value={alertSearch} onChange={(event) => { setAlertSearch(event.target.value); setPage(0); }} placeholder="Search alert ID…" /></label>
          <label className="field-label">Status<select value={status} onChange={(event) => { setStatus(event.target.value); setPage(0); }}><option value="">All statuses</option><option value="open">Open</option><option value="investigating">Investigating</option><option value="reviewed">Reviewed</option><option value="closed">Closed</option></select></label>
        </div>
        {loading ? <Loading label="Loading ranked alerts…" /> : alerts.length ? (
          <>
            <div className="table-scroll">
              <table className="ranked-alert-table">
                <thead><tr>
                  <th>Rank</th><th>Alert ID</th><th>User / Entity ID</th><th>Risk Level</th>
                  <th>Combined Risk Score</th><th>Temporal Score</th><th>Relational Score</th>
                  <th>Personal / Peer Context Score</th><th>Detection Reason</th><th>Timestamp</th><th>Status</th><th>Action</th>
                </tr></thead>
                <tbody>{alerts.map((alert, index) => (
                  <tr key={alert.id} className={selectedId === alert.id ? "selected-row" : ""} onClick={() => setSelectedId(alert.id)}>
                    <td>#{page * PAGE_SIZE + index + 1}</td>
                    <td><strong>{alert.alert_uid}</strong></td>
                    <td>{alert.user_id}</td>
                    <td><span className={`severity-label ${alert.severity}`}>{alert.severity}</span></td>
                    <td><strong>{alert.risk_score.toFixed(1)}</strong><small className="cell-sub">Threshold {alert.threshold_value.toFixed(1)}</small></td>
                    <td>{alert.temporal_score.toFixed(3)}</td>
                    <td>{alert.relational_score.toFixed(3)}</td>
                    <td>{alert.contextual_score.toFixed(3)}</td>
                    <td className="alert-reason">{alert.explanation ?? alert.primary_activity}</td>
                    <td>{formatDate(alert.created_at)}</td>
                    <td><span className={`status-badge ${alert.status}`}>{alert.status}</span></td>
                    <td><button className="button subtle alert-action" onClick={(event) => { event.stopPropagation(); setSelectedId(alert.id); window.setTimeout(() => exportInvestigation(alert), 0); }}>Investigate</button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <div className="pagination">
              <span>{total ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} of ${total.toLocaleString()}` : "0 alerts"}</span>
              <div><button className="button subtle" disabled={page === 0} onClick={() => setPage((value) => Math.max(value - 1, 0))}><ChevronLeft size={14} />Previous</button><span>Page {page + 1} of {Math.max(pageCount, 1)}</span><button className="button subtle" disabled={page + 1 >= pageCount} onClick={() => setPage((value) => value + 1)}>Next<ChevronRight size={14} /></button></div>
            </div>
          </>
        ) : <EmptyState title="No alerts match these filters" message="Run detection or adjust your filters to review available findings." />}
      </Card>

      {selected && <div id={`alert-investigation-${selected.id}`} className="investigation-grid alert-investigation">
        <div className="investigation-main">
          <Card title={`Investigation · ${selected.alert_uid}`} description={`${selected.user_id} · ${selected.window_date} · ${selected.primary_activity}`}>
            <div className="detail-grid">
              <div><span>User / entity</span><strong>{investigation?.entity.user_id ?? selected.user_id}</strong></div>
              <div><span>Role / department</span><strong>{[investigation?.entity.role, investigation?.entity.department].filter(Boolean).join(" · ") || "Not recorded"}</strong></div>
              <div><span>Observed profile events</span><strong>{investigation?.entity.total_events?.toLocaleString() ?? "Not recorded"}</strong></div>
              <div><span>Evidence event IDs</span><strong>{selected.evidence?.length ?? 0}</strong></div>
              <div><span>Baseline source</span><strong>{String(investigation?.entity.baseline?.baseline_source ?? "Not recorded")}</strong></div>
            </div>
            <div className="alert-score-grid">{[
              ["Temporal · empirical transition surprise", selected.temporal_score, "temporal"],
              ["Relational · historical edge novelty", selected.relational_score, "relational"],
              ["Personal / peer context · robust statistics", selected.contextual_score, "contextual"],
            ].map(([label, value, tone]) => <div className="alert-score-card" key={String(label)}><span className={`branch-dot ${tone}`} />{label}<strong>{Number(value).toFixed(3)}</strong></div>)}</div>
            <div className="combined-risk"><div><span>Combined risk score</span><strong>{selected.risk_score.toFixed(1)} / 100</strong></div><div className="risk-meter"><i style={{ width: `${Math.min(Math.max(selected.risk_score, 0), 100)}%` }} /></div><small>Observed score {selected.risk_score.toFixed(1)} · applicable threshold {selected.threshold_value.toFixed(1)}</small></div>
            {investigation?.fusion_weights && <p className="small muted">Recorded fusion weights: {Object.entries(investigation.fusion_weights).map(([key, weight]) => `${key.replace("w_", "")} ${weight}`).join(" · ")}</p>}
            <div className="model-limitation">These persisted scores are from empirical transition, edge-novelty, and robust-statistics methods. They are not outputs of a trained Causal Transformer or HGT model.</div>
            <div className="explanation-box"><strong>Detection reason and supporting evidence</strong><p>{selected.explanation ?? "No explanation was stored for this alert."}</p><small>Ground-truth label: {selected.label ? "positive" : "not labelled positive"} · {selected.rule_flags?.length ?? 0} supplementary flags</small></div>
            <h3 className="section-title">Activity timeline and relevant event IDs</h3>
            {selected.evidence?.length ? <div className="table-scroll compact-table"><table><thead><tr><th>Timestamp</th><th>Original event ID</th><th>Activity</th><th>Resource</th></tr></thead><tbody>{[...selected.evidence].sort((a, b) => (a.timestamp ?? "").localeCompare(b.timestamp ?? "")).map((event) => <tr key={event.id}><td>{formatDate(event.timestamp)}</td><td><code>{event.event_id}</code></td><td>{event.activity ?? "—"}</td><td>{event.resource ?? "—"}</td></tr>)}</tbody></table></div> : <p className="muted">No event evidence was attached to this alert.</p>}
          </Card>
        </div>
        <div className="investigation-side">
          <Card title="Analyst review" description="Review updates are audit logged and retained in history.">
            <label className="field-label">Review status<select value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}><option value="open">Open</option><option value="investigating">Investigating</option><option value="reviewed">Reviewed</option><option value="closed">Closed</option></select></label>
            <label className="field-label">Verdict<select value={verdict} onChange={(event) => setVerdict(event.target.value)}><option value="">No verdict</option><option value="confirmed_threat">Confirmed threat</option><option value="suspicious">Suspicious</option><option value="benign">Benign</option><option value="inconclusive">Inconclusive</option></select></label>
            <label className="field-label">Review note<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Document evidence and reasoning…" rows={4} maxLength={4000} /></label>
            <button className="button primary full-button" disabled={saving} onClick={() => void saveReview()}><Save size={16} />{saving ? "Saving…" : "Save review"}</button>
          </Card>
          <Card title="Review history" description="Previous analyst decisions">
            {investigation?.reviews.length ? <div className="review-history">{investigation.reviews.map((review) => <div key={review.id}><span className="history-dot" /><strong>{review.verdict?.replaceAll("_", " ") ?? review.status}</strong><small>{formatDate(review.reviewed_at)}</small>{review.note && <p>{review.note}</p>}</div>)}</div> : <p className="muted">No review history yet.</p>}
          </Card>
        </div>
      </div>}
    </>
  );
}
