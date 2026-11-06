import { useEffect, useState } from "react";
import { CircleCheck, CircleDashed, Play, RefreshCw } from "lucide-react";
import { api, type Dataset, type ModelRun, type RiskScore } from "../api/client";
import { Card, EmptyState, ErrorMessage, Loading, PageHeader } from "../components/common";

type Job = { id: number; status: string; progress: number; message: string | null; result: Record<string, unknown> | null };

export default function DetectionPage({ datasetId, dataset }: { datasetId: number | null; dataset: Dataset | null }) {
  const [runs, setRuns] = useState<ModelRun[]>([]);
  const [scores, setScores] = useState<RiskScore[]>([]);
  const [trainFraction, setTrainFraction] = useState(0.7);
  const [minimum, setMinimum] = useState(25);
  const [weights, setWeights] = useState({ temporal: 40, relational: 30, contextual: 30 });
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadResults(id: number) {
    const [nextRuns, nextScores] = await Promise.all([
      api<ModelRun[]>(`/detection/runs/${id}`),
      api<{ items: RiskScore[] }>(`/detection/scores/${id}?limit=500`),
    ]);
    setRuns(nextRuns); setScores(nextScores.items);
  }

  useEffect(() => {
    let active = true;
    if (!datasetId) return () => { active = false; };
    Promise.all([
      api<ModelRun[]>(`/detection/runs/${datasetId}`),
      api<{ items: RiskScore[] }>(`/detection/scores/${datasetId}?limit=500`),
    ]).then(([nextRuns, nextScores]) => {
      if (active) { setRuns(nextRuns); setScores(nextScores.items); }
    }).catch((reason: Error) => active && setError(reason.message));
    return () => { active = false; };
  }, [datasetId]);

  useEffect(() => {
    if (!job || !["pending", "running"].includes(job.status)) return;
    const timer = window.setInterval(() => {
      void api<Job>(`/detection/jobs/${job.id}`).then(async (nextJob) => {
        setJob(nextJob);
        if (nextJob.status === "completed" && datasetId) {
          await loadResults(datasetId);
          setBusy(false);
        } else if (nextJob.status === "failed") {
          setBusy(false);
          setError(nextJob.message ?? "Detection failed.");
        }
      }).catch((reason: Error) => { setBusy(false); setError(reason.message); });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [job, datasetId]);

  async function runDetection() {
    if (!datasetId) return;
    setBusy(true); setError(""); setJob(null);
    try {
      const weightsTotal = weights.temporal + weights.relational + weights.contextual;
      if (weightsTotal === 0) throw new Error("At least one score fusion weight must be non-zero.");
      const response = await api<Job>("/detection/run", {
        method: "POST",
        body: JSON.stringify({
          dataset_id: datasetId,
          train_fraction: trainFraction,
          min_risk_score: minimum,
          fusion_weights: {
            w_temporal: weights.temporal / weightsTotal,
            w_relational: weights.relational / weightsTotal,
            w_contextual: weights.contextual / weightsTotal,
          },
        }),
      });
      setJob(response);
    } catch (reason) {
      setBusy(false);
      setError(reason instanceof Error ? reason.message : "Could not start detection.");
    }
  }

  if (!datasetId) return <><PageHeader title="Anomaly detection" description="Run the unified three-branch scoring pipeline on a selected dataset." /><Card><EmptyState title="Select a dataset" message="Detection runs use persisted activity records from the selected dataset." /></Card></>;
  const latestRun = runs[0];
  return (
    <>
      <PageHeader eyebrow="DETECTION WORKBENCH" title="Anomaly detection" description="Configure the held-out window, branch fusion, and risk floor, then run detection against stored activity." actions={<span className={`status-badge ${latestRun ? "ready" : "uploaded"}`}>{latestRun ? "Model run available" : "No model run"}</span>} />
      {error && <ErrorMessage>{error}</ErrorMessage>}
      <div className="detection-layout">
        <Card title="Detection execution" description={dataset?.status === "ready" ? "Dataset validated and ready for analysis." : `Dataset must be ready before detection. Current status: ${dataset?.status ?? "unknown"}.`}>
          <div className="config-grid">
            <label className="field-label">Training window <strong>{Math.round(trainFraction * 100)}%</strong><input type="range" min="50" max="85" step="5" value={trainFraction * 100} onChange={(event) => setTrainFraction(Number(event.target.value) / 100)} /></label>
            <label className="field-label">Minimum alert risk <strong>{minimum}</strong><input type="range" min="0" max="80" step="5" value={minimum} onChange={(event) => setMinimum(Number(event.target.value))} /></label>
          </div>
          <h3 className="section-title">Score fusion weights</h3>
          <div className="weight-list">
            {(["temporal", "relational", "contextual"] as const).map((branch) => <label key={branch} className="weight-row"><span className={`branch-dot ${branch}`} />{branch[0].toUpperCase() + branch.slice(1)}<input type="range" min="0" max="100" step="5" value={weights[branch]} onChange={(event) => setWeights((value) => ({ ...value, [branch]: Number(event.target.value) }))} /><strong>{weights[branch]}%</strong></label>)}
          </div>
          <div className="model-branch-grid">
            <div><CircleCheck size={16} /><strong>Temporal</strong><span>Empirical next-event sequence surprise</span></div>
            <div><CircleCheck size={16} /><strong>Relational</strong><span>Historical user-resource edge novelty</span></div>
            <div><CircleCheck size={16} /><strong>Personal / peer</strong><span>Median and MAD baselines with role fallback</span></div>
          </div>
          <div className="model-limitation"><CircleDashed size={16} /><span>This backend currently uses empirical branch scorers. The proposed Causal Transformer, HGT relation decoder, ADWIN drift monitor, and controlled threshold-update gate are <b>not implemented</b>; scores are not represented as those models.</span></div>
          <button className="button primary" disabled={busy || dataset?.status !== "ready"} onClick={() => void runDetection()}>{busy ? <><RefreshCw className="spin" size={16} /> Running…</> : <><Play size={16} /> Run detection</>}</button>
        </Card>
        <Card title="Branch status" description="Latest completed run metadata">
          <div className="branch-status-list">{[
            ["Temporal branch", "Empirical transition surprise", latestRun ? "Ready" : "Idle", Boolean(latestRun)],
            ["Relational branch", "Observed user-resource graph", latestRun ? "Ready" : "Idle", Boolean(latestRun)],
            ["Personal / peer context", "Robust rolling baselines", latestRun ? "Ready" : "Idle", Boolean(latestRun)],
            ["Fusion and thresholding", "Calibrated weighted score", latestRun ? "Ready" : "Idle", Boolean(latestRun)],
            ["Role-aware threshold", "95th percentile; global fallback for low samples", latestRun ? "Ready" : "Idle", Boolean(latestRun)],
            ["ADWIN drift monitor", "Not implemented in this backend", "Unavailable", false],
            ["Controlled update gate", "Analyst reviews are recorded; no automatic baseline updates", "Manual", false],
          ].map(([title, detail, state, isReady]) => <div key={String(title)}><span className={`status-led ${isReady ? "on" : ""}`} /><span><strong>{title}</strong><small>{detail}</small></span><b>{state}</b></div>)}</div>
          {latestRun && <div className="run-meta"><span>Version</span><strong>{latestRun.version}</strong><span>Completed</span><strong>{latestRun.finished_at ? new Date(latestRun.finished_at).toLocaleString() : "—"}</strong><span>Training / evaluation windows</span><strong>{latestRun.train_rows.toLocaleString()} / {latestRun.eval_rows.toLocaleString()}</strong></div>}
        </Card>
      </div>
      {job && <Card title="Execution progress" description={job.message ?? "Detection job"}><div className="progress-track"><i style={{ width: `${job.progress}%` }} /></div><div className="progress-caption"><span>{job.status}</span><strong>{job.progress}%</strong></div></Card>}
      <div className="dashboard-grid">
        {(["temporal_score", "relational_score", "contextual_score"] as const).map((key) => {
          const label = key.replace("_score", "");
          const average = scores.length ? scores.reduce((sum, item) => sum + item[key], 0) / scores.length : null;
          return <Card key={key} title={`${label[0].toUpperCase()}${label.slice(1)} branch`} description="Mean held-out normalized surprise score"><div className={`branch-score-value ${label}`}>{average == null ? "—" : average.toFixed(3)}</div><div className="branch-mini-count">{scores.length.toLocaleString()} scored user-day windows</div></Card>;
        })}
      </div>
      <Card title="Combined detection results" description={`${scores.filter((score) => score.is_anomaly).length} anomalies flagged from ${scores.length} returned held-out windows`}>
        {scores.length ? <div className="table-scroll"><table><thead><tr><th>User</th><th>Date</th><th>Temporal</th><th>Relational</th><th>Contextual</th><th>Combined risk</th><th>Threshold</th><th>Status</th></tr></thead><tbody>{scores.slice(0, 100).map((score, index) => <tr key={`${score.user_id}-${score.window_date}-${index}`}><td>{score.user_id}</td><td>{score.window_date}</td><td>{score.temporal_score.toFixed(3)}</td><td>{score.relational_score.toFixed(3)}</td><td>{score.contextual_score.toFixed(3)}</td><td><strong>{score.risk_score.toFixed(1)}</strong></td><td>{score.threshold_value.toFixed(1)}</td><td><span className={`status-badge ${score.is_anomaly ? "failed" : "ready"}`}>{score.is_anomaly ? "Anomaly" : "Normal"}</span></td></tr>)}</tbody></table></div> : <EmptyState title="No completed detection scores" message="Run detection to score held-out activity windows." />}
      </Card>
      {busy && !job && <Loading label="Submitting detection job…" />}
    </>
  );
}
