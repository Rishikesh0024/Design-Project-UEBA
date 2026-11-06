import { useEffect, useState } from "react";
import { AlertTriangle, Activity, ShieldAlert, Users } from "lucide-react";
import { api, type ActivityEvent, type Alert, type Dataset, type Profile } from "../api/client";
import { ActivityBreakdown, ActivityChart, RiskChart, type ActivityPoint } from "../components/Charts";
import { Card, EmptyState, ErrorMessage, formatDate, formatNumber, Loading, MetricCard, PageHeader } from "../components/common";

type Stats = {
  total_events: number;
  unique_users: number;
  total_alerts: number;
  high_risk_alerts: number;
  dataset_name: string | null;
  last_run: string | null;
};
type Risk = { user_id: string; window_date: string; risk_score: number; threshold_value: number; severity: string };
type RiskSummary = { scored_windows: number; normal_windows: number; anomalous_windows: number };

export default function DashboardPage({ datasetId, dataset }: { datasetId: number | null; dataset: Dataset | null }) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [activity, setActivity] = useState<ActivityPoint[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [risks, setRisks] = useState<Risk[]>([]);
  const [riskSummary, setRiskSummary] = useState<RiskSummary | null>(null);
  const [recentEvents, setRecentEvents] = useState<ActivityEvent[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    if (!datasetId) {
      setStats(null); setActivity([]); setAlerts([]); setRisks([]);
      setRiskSummary(null);
      setRecentEvents([]); setProfiles([]);
      return () => { active = false; };
    }
    setLoading(true);
    setError("");
    Promise.all([
      api<Stats>(`/analytics/dashboard?dataset_id=${datasetId}`),
      api<ActivityPoint[]>(`/analytics/activity-over-time?dataset_id=${datasetId}`),
      api<Alert[]>(`/alerts?dataset_id=${datasetId}&limit=6`),
      api<{ items: Risk[] }>(`/detection/scores/${datasetId}?limit=40`),
      api<RiskSummary>(`/detection/summary/${datasetId}`),
      api<{ items: ActivityEvent[] }>(`/activity/events?dataset_id=${datasetId}&limit=6`),
      api<Profile[]>(`/profiles?dataset_id=${datasetId}`),
    ]).then(([nextStats, nextActivity, nextAlerts, nextRisks, nextRiskSummary, nextEvents, nextProfiles]) => {
      if (!active) return;
      setStats(nextStats); setActivity(nextActivity); setAlerts(nextAlerts); setRisks(nextRisks.items);
      setRiskSummary(nextRiskSummary);
      setRecentEvents(nextEvents.items); setProfiles(nextProfiles.slice(0, 7));
    }).catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [datasetId]);

  if (!datasetId) {
    return <><PageHeader eyebrow="OVERVIEW" title="Security dashboard" description="A unified view of observed activity and completed detection runs." /><Card><EmptyState title="Choose a dataset to get started" message="Upload a CERT or compatible CSV dataset, then select it from the workspace header." /></Card></>;
  }
  if (loading && !stats) return <Loading />;
  return (
    <>
      <PageHeader eyebrow="SECURITY OVERVIEW" title="Security dashboard" description={`${dataset?.name ?? "Selected dataset"} · ${dataset?.date_from ?? "—"} to ${dataset?.date_to ?? "—"}`} />
      {error && <ErrorMessage>{error}</ErrorMessage>}
      <div className="metric-grid">
        <MetricCard label="Total activity events" value={formatNumber(stats?.total_events)} hint="Persisted event records" icon={<Activity size={19} />} />
        <MetricCard label="Unique users / entities" value={formatNumber(stats?.unique_users)} hint="Across the selected dataset" icon={<Users size={19} />} tone="green" />
        <MetricCard label="Total alerts" value={formatNumber(stats?.total_alerts)} hint="From completed detection runs" icon={<ShieldAlert size={19} />} tone="amber" />
        <MetricCard label="High-risk alerts" value={formatNumber(stats?.high_risk_alerts)} hint="High and critical severity" icon={<AlertTriangle size={19} />} tone="red" />
      </div>
      <div className="dashboard-grid">
        <ActivityChart data={activity} />
        <ActivityBreakdown data={activity} />
      </div>
      <div className="dashboard-grid lower-grid">
        <RiskChart data={risks} />
        <Card title="Normal versus anomalous" description="Held-out user-day windows from the latest completed run">
          {riskSummary?.scored_windows ? <>
            <div className="normal-anomaly">
              <div><span className="normal-key" /><small>Normal</small><strong>{riskSummary.normal_windows.toLocaleString()}</strong></div>
              <div><span className="anomaly-key" /><small>Anomalous</small><strong>{riskSummary.anomalous_windows.toLocaleString()}</strong></div>
            </div>
            <div className="split-meter"><i style={{ width: `${riskSummary.anomalous_windows / Math.max(riskSummary.scored_windows, 1) * 100}%` }} /></div>
            <p className="small muted">All {riskSummary.scored_windows.toLocaleString()} held-out windows from the latest completed run.</p>
          </> : <EmptyState title="No scored windows" message="Run detection to compare normal and anomalous activity." />}
        </Card>
        <Card title="Recent security activity" description="Latest source events recorded in the dataset">
          {recentEvents.length ? <div className="activity-list">{recentEvents.map((event) => <div className="activity-row" key={event.id}><span className="activity-event-icon"><Activity size={14} /></span><div className="activity-copy"><strong>{event.user_id} <span>· {event.activity}</span></strong><small>{event.event_id} · {new Date(event.timestamp).toLocaleString()}</small></div></div>)}</div> : <EmptyState title="No recent events" message="Ingested activity appears here after dataset processing." />}
        </Card>
        <Card title="Recent alerts" description="Latest ranked findings">
          {alerts.length ? (
            <div className="activity-list">
              {alerts.map((alert) => (
                <div className="activity-row" key={alert.id}>
                  <span className={`severity-dot ${alert.severity}`} />
                  <div className="activity-copy">
                    <strong>{alert.user_id} <span>· {alert.primary_activity}</span></strong>
                    <small>{alert.window_date} · {alert.alert_uid}</small>
                  </div>
                  <span className="risk-pill">{alert.risk_score.toFixed(1)}</span>
                </div>
              ))}
            </div>
          ) : <EmptyState title="No alerts yet" message="A completed detection run will add ranked alerts here." />}
          {stats?.last_run && <div className="card-footer-note">Last completed run · {formatDate(stats.last_run)}</div>}
        </Card>
      </div>
      <Card title="User behaviour summary" description="Profiles currently stored for the selected dataset">
        {profiles.length ? <div className="table-scroll"><table><thead><tr><th>User / entity</th><th>Role</th><th>Total events</th><th>Active days</th><th>Last activity</th><th>Baseline</th></tr></thead><tbody>{profiles.map((profile) => <tr key={profile.user_id}><td><strong>{profile.user_id}</strong></td><td>{profile.role ?? "—"}</td><td>{profile.total_events.toLocaleString()}</td><td>{profile.active_days.toLocaleString()}</td><td>{formatDate(profile.last_activity)}</td><td>{String(profile.baseline?.baseline_source ?? "Not computed")}</td></tr>)}</tbody></table></div> : <EmptyState title="No user profiles yet" message="Profiles are persisted during dataset ingestion." />}
        <div className="summary-inline summary-after"><span>Dataset status <b className="capitalize">{dataset?.status ?? "—"}</b></span><span>Ground-truth labels <b>{dataset?.has_labels ? "Available" : "Not provided"}</b></span></div>
      </Card>
    </>
  );
}
