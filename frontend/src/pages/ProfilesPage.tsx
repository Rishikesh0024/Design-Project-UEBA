import { useEffect, useState } from "react";
import { Activity, UserRound } from "lucide-react";
import { api, type Alert, type Profile, type RiskScore } from "../api/client";
import { Card, EmptyState, ErrorMessage, formatDate, Loading, PageHeader } from "../components/common";

export default function ProfilesPage({ datasetId }: { datasetId: number | null }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selected, setSelected] = useState<Profile | null>(null);
  const [events, setEvents] = useState<{ event_id: string; activity: string; timestamp: string; resource: string | null }[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [risk, setRisk] = useState<RiskScore[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    if (!datasetId) return () => { active = false; };
    setLoading(true);
    api<Profile[]>(`/profiles?dataset_id=${datasetId}`)
      .then((rows) => { if (active) { setProfiles(rows); setSelected(rows[0] ?? null); } })
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [datasetId]);

  useEffect(() => {
    let active = true;
    if (!datasetId || !selected) return () => { active = false; };
    setError("");
    Promise.all([
      api<{ event_id: string; activity: string; timestamp: string; resource: string | null }[]>(`/profiles/user/events?dataset_id=${datasetId}&user_id=${encodeURIComponent(selected.user_id)}&limit=100`),
      api<Alert[]>(`/profiles/user/alerts?dataset_id=${datasetId}&user_id=${encodeURIComponent(selected.user_id)}`),
      api<{ items: RiskScore[] }>(`/detection/scores/${datasetId}?user_id=${encodeURIComponent(selected.user_id)}&limit=500`),
    ]).then(([nextEvents, nextAlerts, riskScores]) => {
      if (!active) return;
      setEvents(nextEvents); setAlerts(nextAlerts);
      setRisk(riskScores.items.filter((item) => item.user_id === selected.user_id).sort((a, b) => a.window_date.localeCompare(b.window_date)));
    }).catch((reason: Error) => active && setError(reason.message));
    return () => { active = false; };
  }, [datasetId, selected]);

  if (!datasetId) return <><PageHeader title="Behaviour profiles" description="Observed activity, robust baselines, and model-generated assessments." /><Card><EmptyState title="Select a dataset" message="User and entity profiles are generated from persisted dataset records." /></Card></>;
  return (
    <>
      <PageHeader eyebrow="USER & ENTITY CONTEXT" title="Behaviour profiles" description="Compare observed activity with personal and role-level baselines. Assessments are model-generated, not observed facts." />
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {loading ? <Loading label="Loading stored user profiles…" /> : profiles.length ? (
        <div className="profile-layout">
          <Card title="Users and entities" description={`${profiles.length} profiles in this dataset`} className="profile-list-card">
            <div className="profile-list">{profiles.map((profile) => <button key={profile.user_id} className={`profile-list-item ${selected?.user_id === profile.user_id ? "selected" : ""}`} onClick={() => setSelected(profile)}><span className="avatar soft"><UserRound size={17} /></span><span><strong>{profile.user_id}</strong><small>{profile.role ?? "Role not provided"} · {profile.total_events.toLocaleString()} events</small></span></button>)}</div>
          </Card>
          {selected && <div className="profile-detail">
            <Card title={selected.user_id} description={`${selected.role ?? "Role not provided"}${selected.department ? ` · ${selected.department}` : ""}`} actions={<span className="observed-badge">OBSERVED PROFILE</span>}>
              <div className="profile-kpis"><div><span>Total events</span><strong>{selected.total_events.toLocaleString()}</strong></div><div><span>Active days</span><strong>{selected.active_days.toLocaleString()}</strong></div><div><span>Last activity</span><strong>{formatDate(selected.last_activity)}</strong></div><div><span>Related alerts</span><strong>{alerts.length}</strong></div></div>
            </Card>
            <Card title="Personal and role baselines" description="Rolling robust statistics from the training period; median and MAD are shown where available.">
              {selected.baseline ? <div className="table-scroll"><table><thead><tr><th>Feature</th><th>Personal median</th><th>Personal MAD</th><th>Baseline source</th></tr></thead><tbody>{Object.entries(selected.baseline).filter(([, value]) => typeof value === "object" && value !== null).map(([feature, value]) => {
                const item = value as { median?: number; mad?: number; source?: string };
                return <tr key={feature}><td>{feature.replaceAll("_", " ")}</td><td>{item.median?.toFixed(2) ?? "—"}</td><td>{item.mad?.toFixed(2) ?? "—"}</td><td>{item.source ?? "user / role fallback"}</td></tr>;
              })}</tbody></table></div> : <EmptyState title="Baseline not computed" message="Run anomaly detection to build the user and role baselines." />}
            </Card>
            <Card title="Historical risk trend" description="Model-generated fused risk score per held-out user-day window">
              {risk.length ? <>
                <div className="risk-trend">{risk.map((row) => <div className="risk-trend-row" key={row.window_date}><span>{row.window_date}</span><div className="risk-track"><i style={{ width: `${Math.min(row.risk_score, 100)}%` }} /></div><strong>{row.risk_score.toFixed(1)}</strong><small>{row.threshold_value.toFixed(1)} threshold</small></div>)}</div>
                <div className="table-scroll profile-score-table"><table><thead><tr><th>Date</th><th>Temporal</th><th>Relational</th><th>Contextual</th><th>Combined deviation</th><th>Threshold</th><th>Assessment</th></tr></thead><tbody>{risk.map((row) => <tr key={`score-${row.window_date}`}><td>{row.window_date}</td><td>{row.temporal_score.toFixed(3)}</td><td>{row.relational_score.toFixed(3)}</td><td>{row.contextual_score.toFixed(3)}</td><td><strong>{row.risk_score.toFixed(1)}</strong></td><td>{row.threshold_value.toFixed(1)}</td><td><span className={`status-badge ${row.is_anomaly ? "failed" : "ready"}`}>{row.is_anomaly ? "Model flagged" : "Below threshold"}</span></td></tr>)}</tbody></table></div>
                <p className="small muted">Observed events and role metadata are stored separately from these model-generated assessment scores.</p>
              </> : <p className="muted">No completed detection scores are available yet.</p>}
            </Card>
            <div className="profile-lower-grid">
              <Card title="Recent observed activity" description="Latest 100 source events"><div className="table-scroll compact-table"><table><thead><tr><th>Timestamp</th><th>Event</th><th>Activity</th><th>Resource</th></tr></thead><tbody>{events.slice(0, 20).map((event) => <tr key={event.event_id}><td>{formatDate(event.timestamp)}</td><td><code>{event.event_id}</code></td><td>{event.activity}</td><td>{event.resource ?? "—"}</td></tr>)}</tbody></table></div></Card>
              <Card title="Related alerts" description="Persisted analyst investigation items">{alerts.length ? alerts.map((alert) => <div className="related-alert" key={alert.id}><span className={`severity-dot ${alert.severity}`} /><div><strong>{alert.alert_uid}</strong><small>{alert.window_date} · {alert.primary_activity}</small></div><b>{alert.risk_score.toFixed(1)}</b></div>) : <div className="muted"><Activity size={15} /> No associated alerts.</div>}</Card>
            </div>
          </div>}
        </div>
      ) : <Card><EmptyState title="No profiles found" message="Profiles are created when dataset ingestion completes." /></Card>}
    </>
  );
}
