import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Clock3 } from "lucide-react";
import { api, type ActivityEvent, type Profile } from "../api/client";
import { Card, EmptyState, ErrorMessage, formatDate, Loading, PageHeader } from "../components/common";

type Props = { datasetId: number | null };
type EventPage = { items: ActivityEvent[]; total: number };

export default function ExplorerPage({ datasetId }: Props) {
  const [user, setUser] = useState("");
  const [eventId, setEventId] = useState("");
  const [activity, setActivity] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(0);
  const [results, setResults] = useState<EventPage>({ items: [], total: 0 });
  const [selected, setSelected] = useState<ActivityEvent | null>(null);
  const [userEvents, setUserEvents] = useState<{ event_id: string; activity: string; timestamp: string; pc: string | null; resource: string | null; label: number }[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const pageSize = 100;

  const query = useMemo(() => {
    if (!datasetId) return "";
    const params = new URLSearchParams({ dataset_id: String(datasetId), limit: String(pageSize), offset: String(page * pageSize) });
    if (user.trim()) params.set("user_id", user.trim());
    if (eventId.trim()) params.set("event_id", eventId.trim());
    if (activity) params.append("activity", activity);
    if (from) params.set("date_from", new Date(`${from}T00:00:00`).toISOString());
    if (to) params.set("date_to", new Date(`${to}T23:59:59`).toISOString());
    return params.toString();
  }, [datasetId, user, eventId, activity, from, to, page]);

  useEffect(() => {
    let active = true;
    if (!datasetId) return () => { active = false; };
    setLoading(true); setError("");
    api<EventPage>(`/activity/events?${query}`)
      .then((response) => active && setResults(response))
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [datasetId, query]);

  useEffect(() => setPage(0), [datasetId, user, eventId, activity, from, to]);

  async function inspect(event: ActivityEvent) {
    setSelected(event); setProfile(null); setUserEvents([]); setError("");
    try {
      const [nextProfile, relatedEvents] = await Promise.all([
        api<Profile>(`/profiles/user/detail?dataset_id=${datasetId}&user_id=${encodeURIComponent(event.user_id)}`),
        api<{ event_id: string; activity: string; timestamp: string; pc: string | null; resource: string | null; label: number }[]>(`/profiles/user/events?dataset_id=${datasetId}&user_id=${encodeURIComponent(event.user_id)}&limit=12`),
      ]);
      setProfile(nextProfile);
      setUserEvents(relatedEvents);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load event context.");
    }
  }

  if (!datasetId) return <><PageHeader title="Activity explorer" description="Investigate event-level activity and trace events to their original source IDs." /><Card><EmptyState title="Select a dataset" message="Choose an active dataset in the header to search its activity events." /></Card></>;
  return (
    <>
      <PageHeader eyebrow="INVESTIGATION" title="Activity explorer" description="Search by user or source event ID, filter the event timeline, and inspect evidence in context." />
      {error && <ErrorMessage>{error}</ErrorMessage>}
      <Card title="Search and filters">
        <div className="filter-grid">
          <label className="field-label">User ID<input value={user} onChange={(event) => setUser(event.target.value)} placeholder="Search user…" /></label>
          <label className="field-label">Original event ID<input value={eventId} onChange={(event) => setEventId(event.target.value)} placeholder="e.g. E0000123" /></label>
          <label className="field-label">Activity type<select value={activity} onChange={(event) => setActivity(event.target.value)}><option value="">All activity types</option><option value="logon">Logon</option><option value="logoff">Logoff</option><option value="file">File</option><option value="email">Email</option><option value="web">Web / HTTP</option><option value="device">Removable device</option></select></label>
          <label className="field-label">From date<input type="date" value={from} onChange={(event) => setFrom(event.target.value)} /></label>
          <label className="field-label">To date<input type="date" value={to} onChange={(event) => setTo(event.target.value)} /></label>
        </div>
      </Card>
      <Card title="Chronological activity" description={`${results.total.toLocaleString()} matching events · newest first`}>
        {loading ? <Loading label="Searching persisted events…" /> : results.items.length ? (
          <>
            <div className="table-scroll"><table><thead><tr><th>Event ID</th><th>Timestamp</th><th>User</th><th>Activity</th><th>Workstation</th><th>Resource</th><th>Label</th><th /></tr></thead>
              <tbody>{results.items.map((row) => <tr key={row.id}><td><code>{row.event_id}</code></td><td>{formatDate(row.timestamp)}</td><td><strong>{row.user_id}</strong></td><td><span className="activity-tag">{row.activity}</span></td><td>{row.pc ?? "—"}</td><td className="truncate-cell" title={row.resource ?? ""}>{row.resource ?? "—"}</td><td>{row.label ? <span className="label-yes">Positive</span> : "—"}</td><td><button className="text-button" onClick={() => void inspect(row)}>Inspect</button></td></tr>)}</tbody>
            </table></div>
            <div className="pagination">
              <span>Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, results.total)} of {results.total.toLocaleString()}</span>
              <div><button className="button subtle small-button" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}><ChevronLeft size={15} /> Previous</button><button className="button subtle small-button" disabled={(page + 1) * pageSize >= results.total} onClick={() => setPage((value) => value + 1)}>Next <ChevronRight size={15} /></button></div>
            </div>
          </>
        ) : <EmptyState title="No matching events" message={loading ? "Loading" : "Adjust the filters or select another dataset."} />}
      </Card>
      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <section className="modal wide-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="modal-heading"><div><div className="eyebrow">ORIGINAL EVENT TRACE</div><h2>{selected.event_id}</h2><p>{formatDate(selected.timestamp)} · {selected.activity}</p></div><button className="icon-button" onClick={() => setSelected(null)}>×</button></div>
            <div className="detail-grid">
              <div><span>User</span><strong>{selected.user_id}</strong></div><div><span>Workstation</span><strong>{selected.pc ?? "—"}</strong></div><div><span>Resource</span><strong className="break-anywhere">{selected.resource ?? "—"}</strong></div><div><span>Ground truth</span><strong>{selected.label ? "Positive label" : "Unlabelled / normal"}</strong></div>
            </div>
            <div className="investigation-grid">
              <div><h3 className="section-title">Associated user activity</h3>{userEvents.length ? <div className="timeline">{userEvents.map((item) => <div className="timeline-item" key={item.event_id}><i /><div><strong>{item.activity}</strong><span>{formatDate(item.timestamp)} · <code>{item.event_id}</code></span></div></div>)}</div> : <p className="muted">No associated user events returned.</p>}</div>
              <div><h3 className="section-title">Observed profile</h3>{profile ? <div className="profile-summary"><div><span>Role</span><strong>{profile.role ?? "Not provided"}</strong></div><div><span>Total events</span><strong>{profile.total_events.toLocaleString()}</strong></div><div><span>Active days</span><strong>{profile.active_days.toLocaleString()}</strong></div><div><span>Last activity</span><strong>{formatDate(profile.last_activity)}</strong></div></div> : <div className="muted"><Clock3 size={15} /> Loading profile context…</div>}</div>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
