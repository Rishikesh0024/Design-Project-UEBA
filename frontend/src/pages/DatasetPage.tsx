import { useCallback, useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, Eye, FileText, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { api, demoApi, type ActivityEvent, type Dataset, type DemoDataset, type DemoPreview } from "../api/client";
import { Card, EmptyState, ErrorMessage, formatDate, formatNumber, PageHeader } from "../components/common";

type Props = {
  datasets: Dataset[];
  datasetId: number | null;
  refreshDatasets: () => Promise<void>;
  onSelectDataset: (id: number | null) => void;
};

const delay = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds));

export default function DatasetPage({ datasets, datasetId, refreshDatasets, onSelectDataset }: Props) {
  const [name, setName] = useState("");
  const [version, setVersion] = useState("r4.2");
  const [files, setFiles] = useState<File[]>([]);
  const [selected, setSelected] = useState<Dataset | null>(null);
  const [selectedEvents, setSelectedEvents] = useState<ActivityEvent[]>([]);
  const [preview, setPreview] = useState<DemoPreview | null>(null);
  const [demoCatalog, setDemoCatalog] = useState<DemoDataset[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeDemoLoad, setActiveDemoLoad] = useState<string | null>(null);
  const [demoProgress, setDemoProgress] = useState("Preparing synthetic dataset…");

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true);
    setCatalogError("");
    try {
      setDemoCatalog(await demoApi<DemoDataset[]>("/datasets/demo"));
    } catch (reason) {
      console.error("Could not load the UEBA demo dataset catalog.", reason);
      setCatalogError(reason instanceof Error ? reason.message : "Could not load the demo catalog.");
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  useEffect(() => { void loadCatalog(); }, [loadCatalog]);

  useEffect(() => {
    const pending = datasets.some((dataset) => ["uploaded", "validating", "processing"].includes(dataset.status));
    if (!pending) return;
    const timer = window.setInterval(() => void refreshDatasets(), 2500);
    return () => window.clearInterval(timer);
  }, [datasets, refreshDatasets]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!files.length) {
      setError("Select at least one CSV file.");
      return;
    }
    setBusy(true); setError(""); setMessage("");
    try {
      const body = new FormData();
      body.append("name", name.trim() || files[0].name.replace(/\.csv$/i, ""));
      body.append("version", version);
      files.forEach((file) => body.append("files", file));
      const created = await api<Dataset>("/datasets", { method: "POST", body });
      setMessage(`Upload accepted. ${files.length} file${files.length === 1 ? "" : "s"} queued for validation and preprocessing.`);
      setFiles([]); setName("");
      await refreshDatasets();
      onSelectDataset(created.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed.");
    } finally { setBusy(false); }
  }

  async function inspect(dataset: Dataset) {
    setSelected(null); setSelectedEvents([]); setError("");
    try {
      const [details, events] = await Promise.all([
        api<Dataset>(`/datasets/${dataset.id}`),
        api<{ items: ActivityEvent[] }>(`/activity/events?dataset_id=${dataset.id}&limit=8`),
      ]);
      setSelected(details);
      setSelectedEvents(events.items);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load dataset details.");
    }
  }

  async function inspectDemo(demo: DemoDataset) {
    setPreview(null); setError("");
    try {
      setPreview(await demoApi<DemoPreview>(`/datasets/demo/${demo.demo_id}/preview`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not preview the demo dataset.");
    }
  }

  async function waitForImport(datasetIdToPoll: number) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const dataset = await api<Dataset>(`/datasets/${datasetIdToPoll}`);
      await refreshDatasets();
      if (dataset.status === "ready") {
        onSelectDataset(dataset.id);
        setMessage(`${dataset.name} imported successfully: ${formatNumber(dataset.valid_rows)} records · Dataset ID ${dataset.id} · Version ${dataset.version}. Select Anomaly Detection to run empirical scoring.`);
        setActiveDemoLoad(null);
        return;
      }
      if (dataset.status === "failed" || dataset.status === "invalid") {
        const detail = dataset.quality_report?.error;
        throw new Error(typeof detail === "string" ? detail : `Dataset processing ${dataset.status}.`);
      }
      setDemoProgress(dataset.status === "processing" ? "Validating records and running preprocessing…" : "Waiting for preprocessing to start…");
      await delay(1000);
    }
    throw new Error("Demo dataset processing is taking longer than expected. Check Dataset history for its latest status.");
  }

  async function loadDemo(demo: DemoDataset) {
    setActiveDemoLoad(demo.key); setDemoProgress("Generating synthetic dataset…"); setError(""); setMessage("");
    try {
      const created = await demoApi<Dataset>(`/datasets/demo/${demo.demo_id}/load`, { method: "POST" });
      await refreshDatasets();
      await waitForImport(created.id);
    } catch (reason) {
      setActiveDemoLoad(null);
      setError(reason instanceof Error ? reason.message : "Could not load demo dataset.");
    }
  }

  async function resetDemo(dataset: Dataset) {
    if (!window.confirm(`Reset ${dataset.name}? Its processed demo records and derived results will be rebuilt. Uploaded datasets are not affected.`)) return;
    setActiveDemoLoad(dataset.version); setDemoProgress("Clearing prior demo results and reprocessing…"); setError(""); setMessage("");
    try {
      const reset = await api<Dataset>(`/datasets/${dataset.id}/reset-demo`, { method: "POST" });
      await refreshDatasets();
      await waitForImport(reset.id);
    } catch (reason) {
      setActiveDemoLoad(null);
      setError(reason instanceof Error ? reason.message : "Could not reset demo dataset.");
    }
  }

  async function removeDataset(dataset: Dataset) {
    if (!window.confirm(`Remove "${dataset.name}" and its stored events and analysis results? This cannot be undone.`)) return;
    setError(""); setMessage("");
    try {
      await api<void>(`/datasets/${dataset.id}`, { method: "DELETE" });
      if (datasetId === dataset.id) onSelectDataset(null);
      await refreshDatasets();
      setMessage(`${dataset.name} was removed.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not remove dataset.");
    }
  }

  return (
    <>
      <PageHeader eyebrow="DATA MANAGEMENT" title="Dataset upload" description="Upload your activity streams or use reproducible synthetic demonstrations to explore the UEBA workflow." />
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {message && <div className="success-message dataset-result"><CheckCircle2 size={17} />{message}</div>}

      <div className="dataset-layout">
        <Card title="Upload your own dataset" description="Upload CERT activity streams or compatible CSVs. The existing validation and preprocessing workflow is preserved.">
          <form onSubmit={(event) => void upload(event)} className="upload-form">
            <label className="field-label">Dataset name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. CERT Insider Threat r4.2" /></label>
            <label className="field-label">CERT release
              <select value={version} onChange={(event) => setVersion(event.target.value)}>
                <option value="r4.2">CERT r4.2</option><option value="r6.2">CERT r6.2</option><option value="custom">Custom CSV schema</option>
              </select>
            </label>
            <label className="file-drop">
              <UploadCloud size={24} />
              <strong>Choose activity CSV files</strong>
              <span>Original event IDs are retained for traceability. Up to 2 GB total.</span>
              <input type="file" accept=".csv,text/csv" multiple onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />
            </label>
            {files.length > 0 && <div className="selected-files">{files.map((file) => <span key={`${file.name}-${file.size}`}><FileText size={14} />{file.name}<small>{(file.size / 1024 / 1024).toFixed(1)} MB</small></span>)}</div>}
            <div className="upload-note"><CheckCircle2 size={16} /><span>Schema checks, missing-value reporting, duplicate detection, and preprocessing run after upload.</span></div>
            <button className="button primary" disabled={busy || !files.length}>{busy ? <><RefreshCw className="spin" size={16} /> Uploading…</> : "Upload and validate"}</button>
          </form>
        </Card>
        <Card title="CERT event coverage" description="Supported event categories">
          <div className="coverage-list">
            {["Logon / Logoff", "File access", "Email", "HTTP / Web", "Removable device", "Role metadata"].map((item, index) => <div key={item}><span className="coverage-check">✓</span><span>{item}</span><small>{index === 5 ? "role / users CSV" : "CSV stream"}</small></div>)}
          </div>
          <p className="small muted">Column aliases are auto-detected. Rows without a user or valid timestamp are counted in the quality report rather than silently discarded.</p>
        </Card>
      </div>

      <Card title="Try UEBA with Demo Dataset" description="Explore the UEBA platform using a ready-to-use demonstration dataset. No file upload required.">
        <div className="demo-grid">
          {demoCatalog.map((demo) => {
            const loaded = datasets.find((dataset) => dataset.is_demo && dataset.version === `demo-synthetic-v1-seed-${demo.seed}`);
            return (
              <article className="demo-card" key={demo.key}>
                <div className="demo-card-heading"><div><h3>{demo.name}</h3><span className="demo-label">{demo.source_label}</span></div><span className="demo-format">{demo.format}</span></div>
                <p>{demo.description}</p>
                <div className="demo-stats"><span><strong>{formatNumber(demo.record_count)}</strong> records</span><span><strong>{formatNumber(demo.user_count)}</strong> users</span></div>
                <div className="demo-activities">{demo.activity_types.map((activity) => <span key={activity}>{activity}</span>)}</div>
                {loaded && <div className="demo-loaded"><span className={`status-badge ${loaded.status}`}>{loaded.status}</span><small>Dataset #{loaded.id} · {formatNumber(loaded.valid_rows)} records</small></div>}
                <div className="demo-actions">
                  <button className="button subtle" onClick={() => void inspectDemo(demo)}><Eye size={14} /> Preview dataset</button>
                  <button className="button primary" disabled={activeDemoLoad !== null} onClick={() => void loadDemo(demo)}>{activeDemoLoad === demo.key ? <><RefreshCw className="spin" size={14} /> Loading…</> : "Load demo dataset"}</button>
                </div>
              </article>
            );
          })}
          {!demoCatalog.length && (
            <div className="demo-catalog-state">
              <EmptyState
                title={catalogError ? "Could not load demo catalog" : catalogLoading ? "Loading demo datasets" : "No demo datasets available"}
                message={catalogError || (catalogLoading ? "Requesting the current catalog from the UEBA backend…" : "The backend returned an empty demo catalog. Check the backend configuration and retry.")}
              />
              {!catalogLoading && <button className="button subtle" onClick={() => void loadCatalog()}><RefreshCw size={14} /> Retry catalog request</button>}
            </div>
          )}
        </div>
        {activeDemoLoad && <div className="demo-progress" role="status"><RefreshCw className="spin" size={15} /><div><strong>{demoProgress}</strong><small>Processing status is reported from the backend; no estimated percentage is shown.</small></div><progress aria-label="Demo dataset processing progress" /></div>}
        <p className="small muted demo-integrity-note">All included records are generated synthetic demonstrations, not genuine CERT data. Suspicious labels indicate known scenario records for demonstration and evaluation only.</p>
      </Card>

      <Card title="Dataset history" description="Uploaded and demo datasets, processing status, and active selection" actions={<button className="button subtle small-button" onClick={() => void refreshDatasets()}><RefreshCw size={14} /> Refresh</button>}>
        {datasets.length ? (
          <div className="table-scroll"><table><thead><tr><th>Dataset</th><th>Release / version</th><th>Records</th><th>Users</th><th>Coverage</th><th>Status</th><th>Uploaded</th><th>Actions</th></tr></thead>
            <tbody>{datasets.map((dataset) => <tr key={dataset.id}>
              <td><strong>{dataset.name}</strong><small className="cell-sub">{dataset.is_demo ? "SYNTHETIC DEMO" : dataset.has_labels ? "Labels available" : "No labels"} · ID {dataset.id}{datasetId === dataset.id && " · ACTIVE"}</small></td>
              <td>{dataset.version}</td><td>{formatNumber(dataset.valid_rows)}{dataset.total_rows > dataset.valid_rows && <small className="cell-sub">{formatNumber(dataset.total_rows - dataset.valid_rows)} skipped</small>}</td>
              <td>{formatNumber(dataset.unique_users)}</td><td>{dataset.date_from ?? "—"}<small className="cell-sub">to {dataset.date_to ?? "—"}</small></td>
              <td><span className={`status-badge ${dataset.status}`}>{dataset.status}</span></td><td>{formatDate(dataset.created_at)}</td>
              <td className="dataset-row-actions">
                <button className="text-button" onClick={() => void inspect(dataset)}>Details</button>
                <button className="text-button" onClick={() => onSelectDataset(dataset.id)}>{datasetId === dataset.id ? "Active" : "Use"}</button>
                {dataset.is_demo && <button className="text-button" disabled={activeDemoLoad !== null} onClick={() => void resetDemo(dataset)}>Reset demo</button>}
                <button className="text-button danger-text" onClick={() => void removeDataset(dataset)} aria-label={`Remove ${dataset.name}`}><Trash2 size={13} /> Remove</button>
              </td>
            </tr>)}</tbody></table></div>
        ) : <EmptyState title="No datasets available" message="Upload CSV files or load one of the synthetic demo datasets above." />}
      </Card>

      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <section className="modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="modal-heading"><div><h2>{selected.name}</h2><p>{selected.is_demo ? "SYNTHETIC DEMO · " : ""}Dataset schema and validation report</p></div><button className="icon-button" onClick={() => setSelected(null)}>×</button></div>
            <div className="report-grid">
              {Object.entries(selected.quality_report ?? {}).map(([key, value]) => <div className="report-item" key={key}><span>{key.replaceAll("_", " ")}</span><strong>{typeof value === "object" ? JSON.stringify(value) : String(value)}</strong></div>)}
            </div>
            <h3 className="section-title">Detected schema</h3>
            <pre className="json-panel">{JSON.stringify(selected.schema_info ?? {}, null, 2)}</pre>
            <h3 className="section-title">Processed record preview</h3>
            {selectedEvents.length ? (
              <div className="table-scroll"><table><thead><tr><th>Event ID</th><th>User</th><th>Activity</th><th>Timestamp</th><th>Device</th><th>Resource</th><th>Label</th></tr></thead><tbody>
                {selectedEvents.map((event) => <tr key={event.id}><td><code>{event.event_id}</code></td><td>{event.user_id}</td><td>{event.activity}</td><td>{formatDate(event.timestamp)}</td><td>{event.pc ?? "—"}</td><td>{event.resource ?? "—"}</td><td>{event.label}</td></tr>)}
              </tbody></table></div>
            ) : <p className="small muted">No processed event records are available yet.</p>}
            <button className="button primary" onClick={() => { onSelectDataset(selected.id); setSelected(null); }}>Open dataset</button>
          </section>
        </div>
      )}
      {preview && (
        <div className="modal-backdrop" onClick={() => setPreview(null)}>
          <section className="modal wide-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="modal-heading"><div><h2>{preview.name}</h2><p>SYNTHETIC DEMO DATA · {formatNumber(preview.record_count)} records · {preview.user_count} users · {preview.format} · {formatDate(preview.timestamp_from)} to {formatDate(preview.timestamp_to)}</p></div><button className="icon-button" onClick={() => setPreview(null)}>×</button></div>
            <div className="demo-preview-summaries">
              <div><h3>Activity summary</h3>{preview.activity_summary.map((item) => <p key={item.activity}><span>{item.activity}</span><strong>{formatNumber(item.count)}</strong></p>)}</div>
              <div><h3>User and role summary</h3><div className="table-scroll"><table><thead><tr><th>User</th><th>Role</th><th>Department</th><th>Events</th><th>Scenario labels</th></tr></thead><tbody>{preview.user_summary.map((user) => <tr key={user.user_id}><td>{user.user_id}</td><td>{user.role}</td><td>{user.department}</td><td>{user.record_count}</td><td>{user.labelled_suspicious_records}</td></tr>)}</tbody></table></div></div>
            </div>
            <h3 className="section-title">Dataset schema and data types</h3>
            <div className="demo-schema">{preview.columns.map((column) => <span key={column.name}><strong>{column.name}</strong><small>{column.type}</small></span>)}</div>
            <h3 className="section-title">Sample records (normal and labelled scenario examples)</h3>
            <div className="table-scroll"><table><thead><tr>{preview.columns.map((column) => <th key={column.name}>{column.name}</th>)}</tr></thead><tbody>{preview.sample_records.map((record) => <tr key={String(record.event_id)}>{preview.columns.map((column) => <td key={column.name}>{String(record[column.name] ?? "—")}</td>)}</tr>)}</tbody></table></div>
            <h3 className="section-title">Schema notes</h3><pre className="json-panel">{JSON.stringify(preview.schema, null, 2)}</pre>
            <button className="button primary" disabled={activeDemoLoad !== null} onClick={() => {
              const demo = demoCatalog.find((item) => item.key === preview.key);
              setPreview(null);
              if (demo) void loadDemo(demo);
            }}>Load demo dataset</button>
          </section>
        </div>
      )}
    </>
  );
}
