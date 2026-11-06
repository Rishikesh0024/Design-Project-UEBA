import { useEffect, useMemo, useState } from "react";
import { Download, FileDown } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  type Dataset,
  type EvaluationGraph,
  type ModelRun,
} from "../api/client";
import RelationshipGraph from "../components/RelationshipGraph";
import { Card, EmptyState, ErrorMessage, Loading, PageHeader } from "../components/common";

type MetricValue = number | number[] | number[][] | null;
type ScoreFusion = {
  model_run_id: number | null;
  weights: Record<string, number> | null;
  total: number;
  scores: {
    user_id: string;
    window_date: string;
    temporal_score: number;
    relational_score: number;
    contextual_score: number;
    risk_score: number;
    risk_weights: Record<string, number> | null;
  }[];
  truncated?: boolean;
};

const metricLabels: Record<string, string> = {
  precision: "Precision",
  recall: "Recall",
  f1_score: "F1-score",
  pr_auc: "PR-AUC",
  roc_auc: "ROC-AUC",
  false_positive_rate: "False-positive rate",
  top_k_precision: "Top-K precision",
  detection_delay_days: "Detection delay (days)",
  alert_volume: "Alert volume",
  processing_time_seconds: "Processing time (s)",
  memory_peak_mb: "Peak memory (MB)",
};
const modelColors = ["#527cf1", "#30a77d", "#a276d2", "#e19a40", "#d95063"];

function metricValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return typeof value === "number" ? value.toFixed(Number.isInteger(value) ? 0 : 3) : String(value);
}

function numericMetric(metrics: Record<string, MetricValue> | null | undefined, key: string): number | null {
  const value = metrics?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function curveData(metrics: Record<string, MetricValue> | null, key: string) {
  const value = metrics?.[key];
  if (!Array.isArray(value) || value.length !== 2) return [];
  const [xValues, yValues] = value;
  if (!Array.isArray(xValues) || !Array.isArray(yValues)) return [];
  return xValues.flatMap((x, index) => {
    const y = yValues[index];
    return typeof x === "number" && typeof y === "number"
      ? [{ x, y }]
      : [];
  });
}

function histogram(values: number[], maximum: number, label: string) {
  const bins: { range: string; [key: string]: string | number }[] = Array.from({ length: 10 }, (_, index) => ({
    range: `${(maximum * index / 10).toFixed(maximum === 1 ? 1 : 0)}–${(maximum * (index + 1) / 10).toFixed(maximum === 1 ? 1 : 0)}`,
    [label]: 0,
  }));
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    const index = Math.min(Math.floor((value / maximum) * 10), 9);
    const bin = bins[Math.max(index, 0)];
    bin[label] = Number(bin[label] ?? 0) + 1;
  }
  return bins;
}

function modelDisplayName(branch: string): string {
  const labels: Record<string, string> = {
    contextual: "Personal / Peer Context",
    temporal: "Temporal Causal Transformer",
    relational: "Relational HGT",
    fusion: "Three-branch fusion",
  };
  return labels[branch] ?? branch;
}

function isRecordedHgtRun(run: ModelRun): boolean {
  const config = run.train_config ?? {};
  return run.branch === "relational"
    && (config.model_architecture === "HGT" || config.architecture === "HGT")
    && config.hgt_trained === true;
}

export default function EvaluationPage({
  datasetId,
  dataset,
}: {
  datasetId: number | null;
  dataset?: Dataset | null;
}) {
  const [runs, setRuns] = useState<ModelRun[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [graph, setGraph] = useState<EvaluationGraph | null>(null);
  const [graphError, setGraphError] = useState("");
  const [graphLoading, setGraphLoading] = useState(false);
  const [snapshotDates, setSnapshotDates] = useState<string[]>([]);
  const [snapshotDate, setSnapshotDate] = useState("");
  const [graphSearch, setGraphSearch] = useState("");
  const [scoreFusion, setScoreFusion] = useState<ScoreFusion | null>(null);
  const [fusionLoading, setFusionLoading] = useState(false);

  useEffect(() => {
    let active = true;
    if (!datasetId) {
      setRuns([]);
      setSelectedId(null);
      setGraph(null);
      setSnapshotDates([]);
      setScoreFusion(null);
      return () => { active = false; };
    }
    setLoading(true);
    setError("");
    api<ModelRun[]>(`/evaluation/${datasetId}/runs`)
      .then((data) => {
        if (!active) return;
        setRuns(data);
        setSelectedId((previous) => data.some((run) => run.id === previous)
          ? previous
          : data[0]?.id ?? null);
      })
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    api<{ items: string[] }>(`/evaluation/${datasetId}/graph/snapshots`)
      .then((data) => {
        if (!active) return;
        setSnapshotDates(data.items);
        setSnapshotDate((previous) => data.items.includes(previous) ? previous : "");
      })
      .catch((reason: Error) => active && setGraphError(reason.message));
    return () => { active = false; };
  }, [datasetId]);

  useEffect(() => {
    let active = true;
    if (!datasetId) return () => { active = false; };
    setGraphLoading(true);
    setGraphError("");
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({ edge_limit: "60" });
      if (snapshotDate) params.set("snapshot_date", snapshotDate);
      if (graphSearch.trim()) params.set("user_search", graphSearch.trim());
      api<EvaluationGraph>(`/evaluation/${datasetId}/graph?${params}`)
        .then((data) => active && setGraph(data))
        .catch((reason: Error) => active && setGraphError(reason.message))
        .finally(() => active && setGraphLoading(false));
    }, graphSearch ? 250 : 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [datasetId, snapshotDate, graphSearch]);

  useEffect(() => {
    let active = true;
    if (!datasetId || !selectedId) {
      setScoreFusion(null);
      return () => { active = false; };
    }
    setFusionLoading(true);
    api<ScoreFusion>(`/evaluation/${datasetId}/score-fusion?model_run_id=${selectedId}`)
      .then((data) => active && setScoreFusion(data))
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setFusionLoading(false));
    return () => { active = false; };
  }, [datasetId, selectedId]);

  const selected = runs.find((run) => run.id === selectedId) ?? null;
  const metrics = selected?.eval_metrics as Record<string, MetricValue> | null ?? null;
  const metricRows = useMemo(() => {
    if (!metrics) return [];
    return Object.entries(metricLabels)
      .filter(([key]) => Object.hasOwn(metrics, key))
      .map(([key, label]) => ({ key, label, value: metrics[key] }));
  }, [metrics]);
  const rocData = useMemo(() => curveData(metrics, "roc_curve"), [metrics]);
  const prData = useMemo(() => curveData(metrics, "precision_recall_curve"), [metrics]);
  const confusion = metrics?.confusion_matrix;
  const confusionData = Array.isArray(confusion) && confusion.length === 2
    ? confusion as number[][]
    : null;

  const fusionWeights = scoreFusion?.weights
    ?? scoreFusion?.scores[0]?.risk_weights
    ?? null;
  const fusionSeries = useMemo(() => {
    if (!scoreFusion?.scores.length) return [];
    const raw = scoreFusion.scores;
    return [
      { key: "temporal_score", name: "Temporal empirical score", max: 1 },
      { key: "relational_score", name: "Relational empirical score", max: 1 },
      { key: "contextual_score", name: "Personal / peer context", max: 1 },
      { key: "risk_score", name: "Combined risk score", max: 100 },
    ].map(({ key, name, max }) => {
      const points = histogram(raw.map((row) => row[key as keyof typeof row] as number), max, "count");
      return { key, name, max, points };
    });
  }, [scoreFusion]);

  const contributionData = useMemo(() => {
    if (!scoreFusion?.scores.length || !fusionWeights) return [];
    const weights = [
      ["Temporal", "w_temporal", "temporal_score"],
      ["Relational", "w_relational", "relational_score"],
      ["Personal / peer context", "w_contextual", "contextual_score"],
    ] as const;
    return weights.map(([name, weightKey, scoreKey], index) => {
      const weight = fusionWeights[weightKey] ?? 0;
      const meanScore = scoreFusion.scores.reduce((sum, row) => sum + row[scoreKey], 0) / scoreFusion.scores.length;
      return {
        name,
        weight: weight * 100,
        contribution: meanScore * weight * 100,
        fill: modelColors[index],
      };
    });
  }, [scoreFusion, fusionWeights]);

  const comparisonRows = useMemo(
    () => runs.map((run) => ({
      ...run,
      displayName: modelDisplayName(run.branch),
      experiment: `#${run.id}`,
      precision: numericMetric(run.eval_metrics, "precision"),
      recall: numericMetric(run.eval_metrics, "recall"),
      f1: numericMetric(run.eval_metrics, "f1_score"),
    })),
    [runs],
  );
  const comparisonChart = comparisonRows.filter((run) =>
    run.precision !== null || run.recall !== null || run.f1 !== null
  );
  const inferenceRows = runs.flatMap((run) => {
    const time = numericMetric(run.eval_metrics, "processing_time_seconds");
    return time === null ? [] : [{ experiment: `#${run.id}`, time, branch: run.branch }];
  });
  const hgtRuns = runs.filter(isRecordedHgtRun);
  const lossRows: { epoch: number; training?: number; validation?: number }[] = [];

  function exportCsv() {
    if (!selected || !metrics) return;
    const lines = [
      ["dataset_id", datasetId],
      ["dataset_name", dataset?.name ?? ""],
      ["dataset_version", dataset?.version ?? ""],
      ["experiment_id", selected.id],
      ["model_version", selected.version],
      ["branch", selected.branch],
      ...Object.entries(metrics).map(([key, value]) => [key, Array.isArray(value) ? JSON.stringify(value) : value]),
    ].map((row) => row.map((cell) => `"${String(cell ?? "").replaceAll('"', '""')}"`).join(","));
    const url = URL.createObjectURL(new Blob([lines.join("\r\n")], { type: "text/csv" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `ueba-evaluation-${selected.id}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (!datasetId) {
    return <><PageHeader title="Evaluation" description="Research metrics are shown only for completed, labeled experiments." /><Card><EmptyState title="Select a dataset" message="Choose a dataset with completed detection experiments." /></Card></>;
  }

  return (
    <>
      <PageHeader
        eyebrow="RESEARCH & VALIDATION"
        title="Evaluation"
        description="Historical measured results, observed dataset relationships, and explicit model-readiness status."
        actions={<>
          <button className="button subtle" disabled={!selected || !metrics} onClick={exportCsv}><Download size={15} /> Export CSV</button>
          <button className="button subtle" onClick={() => window.print()}><FileDown size={15} /> Export PDF</button>
        </>}
      />
      {error && <ErrorMessage>{error}</ErrorMessage>}
      {loading && <Loading label="Loading completed experiments…" />}

      <Card title="Evaluation report selection" description="Select a persisted experiment and inspect its recorded dataset/version and held-out results.">
        <div className="evaluation-selectors">
          <label className="field-label">Experiment / model
            <select value={selectedId ?? ""} onChange={(event) => setSelectedId(event.target.value ? Number(event.target.value) : null)}>
              <option value="">Select a completed experiment</option>
              {runs.map((run) => <option value={run.id} key={run.id}>#{run.id} · {modelDisplayName(run.branch)} · {run.version}</option>)}
            </select>
          </label>
          <div className="report-dataset-meta"><span>Dataset</span><strong>{dataset?.name ?? `Dataset ${datasetId}`}</strong></div>
          <div className="report-dataset-meta"><span>Dataset / release version</span><strong>{dataset?.version ?? "Not recorded"}</strong></div>
          <div className="report-dataset-meta"><span>Experiment status</span><strong>{selected ? `${selected.status} · ${selected.finished_at ? new Date(selected.finished_at).toLocaleString() : "completed"}` : "No evaluation results available"}</strong></div>
        </div>
      </Card>

      <Card title="HGT relational model status" description="A graph view of observed events does not imply a trained Heterogeneous Graph Transformer.">
        {hgtRuns.length ? <div className="model-limitation">A recorded HGT run exists. HGT metrics are available only when that run contains held-out evaluation results.</div> : <div className="model-limitation">Model not yet trained — no HGT model artifact or trained HGT experiment is recorded for this dataset. The graph below visualizes observed event relationships only.</div>}
        <div className="model-status-grid">
          <div><span>Personal / Peer Context</span><strong>{runs.some((run) => run.branch === "contextual") ? "Branch scores recorded; no standalone experiment" : "No evaluation results available"}</strong></div>
          <div><span>Temporal Causal Transformer</span><strong>Model not yet trained</strong></div>
          <div><span>Relational HGT</span><strong>{hgtRuns.length ? "Trained experiment recorded" : "Model not yet trained"}</strong></div>
          <div><span>Three-branch fused model</span><strong>{runs.some((run) => run.branch === "fusion") ? "Empirical fusion experiment recorded" : "No evaluation results available"}</strong></div>
          <div><span>HGT relation prediction</span><strong>{hgtRuns.length ? "No recorded relation-prediction metrics" : "No evaluation results available"}</strong></div>
        </div>
      </Card>

      <Card title="Observed heterogeneous relationship graph" description="Built from ingested activity events. Nodes and links represent processed user/resource/device interactions, not model predictions.">
        <RelationshipGraph
          graph={graph}
          loading={graphLoading}
          snapshotDate={snapshotDate}
          onSnapshotChange={setSnapshotDate}
          snapshotDates={snapshotDates}
          userSearch={graphSearch}
          onUserSearchChange={setGraphSearch}
          error={graphError}
        />
      </Card>

      {runs.length > 0 && !metrics && <Card title="Recorded experiment history" description="Completed runs remain available for score inspection. Metrics are omitted when held-out labeled evaluation was unavailable.">
        <div className="table-scroll"><table><thead><tr><th>Experiment</th><th>Branch / model</th><th>Version</th><th>Status</th><th>Completed</th><th>Train / eval windows</th><th>Evaluation metrics</th></tr></thead><tbody>{runs.map((run) => (
          <tr key={run.id} className={selectedId === run.id ? "selected-row" : ""} onClick={() => setSelectedId(run.id)}>
            <td>#{run.id}</td><td>{modelDisplayName(run.branch)}</td><td>{run.version}</td><td>{run.status}</td>
            <td>{run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}</td>
            <td>{run.train_rows.toLocaleString()} / {run.eval_rows.toLocaleString()}</td>
            <td>{run.eval_metrics ? "Available" : "No evaluation results available"}</td>
          </tr>
        ))}</tbody></table></div>
      </Card>}

      {selected && metrics ? (
        <>
          <Card title="Experiment history" description="Completed runs with usable held-out ground-truth labels; choose a row to inspect that historical result.">
            <div className="table-scroll"><table><thead><tr><th>Experiment</th><th>Branch / model</th><th>Version</th><th>Completed</th><th>Train / eval windows</th><th>Precision</th><th>Recall</th><th>F1</th><th>PR-AUC</th></tr></thead><tbody>{runs.map((run) => {
              const m = run.eval_metrics;
              return <tr key={run.id} className={selectedId === run.id ? "selected-row" : ""} onClick={() => setSelectedId(run.id)}>
                <td>#{run.id}</td><td>{modelDisplayName(run.branch)}</td><td>{run.version}</td>
                <td>{run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}</td>
                <td>{run.train_rows.toLocaleString()} / {run.eval_rows.toLocaleString()}</td>
                <td>{metricValue(numericMetric(m, "precision"))}</td><td>{metricValue(numericMetric(m, "recall"))}</td>
                <td>{metricValue(numericMetric(m, "f1_score"))}</td><td>{metricValue(numericMetric(m, "pr_auc"))}</td>
              </tr>;
            })}</tbody></table></div>
          </Card>

          <div className="metric-grid evaluation-kpis">{metricRows.filter((row) => typeof row.value === "number").slice(0, 4).map((row) => <div className="card eval-card" key={row.key}><span>{row.label}</span><strong>{metricValue(row.value)}</strong><small>Measured held-out experiment #{selected.id}</small></div>)}</div>

          <div className="dashboard-grid">
            <Card title={isRecordedHgtRun(selected) ? "HGT AUC-ROC curve" : `Measured ROC curve · ${modelDisplayName(selected.branch)}`} description="Held-out ground-truth ROC points stored with this experiment; empirical fused-model metrics are not HGT-specific.">
              <div className="chart-wrap">
                {rocData.length ? <ResponsiveContainer width="100%" height="100%"><LineChart data={rocData} margin={{ left: 0, right: 12, top: 10 }}>
                  <CartesianGrid stroke="#edf1f7" /><XAxis type="number" dataKey="x" domain={[0, 1]} name="False-positive rate" tick={{ fill: "#8290a5", fontSize: 10 }} /><YAxis type="number" dataKey="y" domain={[0, 1]} name="True-positive rate" tick={{ fill: "#8290a5", fontSize: 10 }} /><Tooltip /><Legend /><Line type="linear" dataKey="y" name={`ROC · AUC ${metricValue(metrics.roc_auc)}`} stroke="#527cf1" dot={false} isAnimationActive={false} />
                </LineChart></ResponsiveContainer> : <div className="chart-empty">No evaluation results available: this historical run has no recorded ROC curve.</div>}
              </div>
            </Card>
            <Card title="Precision–Recall curve" description="Measured held-out precision and recall points from the persisted experiment.">
              <div className="chart-wrap">
                {prData.length ? <ResponsiveContainer width="100%" height="100%"><LineChart data={prData} margin={{ left: 0, right: 12, top: 10 }}>
                  <CartesianGrid stroke="#edf1f7" /><XAxis type="number" dataKey="x" domain={[0, 1]} name="Recall" tick={{ fill: "#8290a5", fontSize: 10 }} /><YAxis type="number" dataKey="y" domain={[0, 1]} name="Precision" tick={{ fill: "#8290a5", fontSize: 10 }} /><Tooltip /><Legend /><Line type="linear" dataKey="y" name={`Precision–Recall · AP ${metricValue(metrics.pr_auc)}`} stroke="#30a77d" dot={false} isAnimationActive={false} />
                </LineChart></ResponsiveContainer> : <div className="chart-empty">No evaluation results available: this historical run has no recorded precision–recall points.</div>}
              </div>
            </Card>
          </div>

          <div className="dashboard-grid">
            <Card title="Confusion matrix" description="Actual versus predicted held-out labels; rows are actual, columns are predicted.">
              {confusionData ? <div className="confusion-matrix"><div /><strong>Predicted normal</strong><strong>Predicted anomaly</strong><strong>Actual normal</strong><b>{confusionData[0][0]}</b><b>{confusionData[0][1]}</b><strong>Actual anomaly</strong><b>{confusionData[1][0]}</b><b>{confusionData[1][1]}</b></div> : <EmptyState title="No evaluation results available" message="This experiment did not persist a confusion matrix." />}
            </Card>
            <Card title="Recorded training and validation loss" description="Only epoch values persisted in the selected experiment configuration are charted.">
              <div className="chart-wrap">
                {lossRows.length ? <ResponsiveContainer width="100%" height="100%"><LineChart data={lossRows}><CartesianGrid stroke="#edf1f7" /><XAxis dataKey="epoch" label={{ value: "Epoch", position: "insideBottom", offset: -3 }} /><YAxis /><Tooltip /><Legend /><Line type="monotone" dataKey="training" name="Training loss" stroke="#527cf1" dot={false} /><Line type="monotone" dataKey="validation" name="Validation loss" stroke="#30a77d" dot={false} /></LineChart></ResponsiveContainer> : <div className="chart-empty">{selected.branch === "relational" && !isRecordedHgtRun(selected) ? "Model not yet trained — no HGT training or validation epochs are recorded." : "No training or validation epoch history was recorded for this experiment."}</div>}
              </div>
            </Card>
          </div>

          <Card title="Measured experiment comparison" description="Metrics below are taken directly from each completed experiment. Missing model branches are not assigned placeholder scores.">
            {comparisonChart.length ? <>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%"><BarChart data={comparisonChart} margin={{ left: -18, right: 6, top: 10 }}>
                  <CartesianGrid stroke="#edf1f7" vertical={false} /><XAxis dataKey="experiment" tickLine={false} axisLine={false} tick={{ fill: "#8290a5", fontSize: 10 }} /><YAxis domain={[0, 1]} tickLine={false} axisLine={false} tick={{ fill: "#8290a5", fontSize: 11 }} /><Tooltip labelFormatter={(_value, payload) => payload?.[0]?.payload?.displayName ?? "Recorded model"} /><Legend /><Bar dataKey="precision" name="Precision" fill="#527cf1" /><Bar dataKey="recall" name="Recall" fill="#30a77d" /><Bar dataKey="f1" name="F1-score" fill="#a276d2" />
                </BarChart></ResponsiveContainer>
              </div>
              <div className="table-scroll"><table><thead><tr><th>Model / branch</th><th>Experiment</th><th>Precision</th><th>Recall</th><th>F1</th><th>PR-AUC</th><th>False-positive rate</th><th>Top-K precision</th><th>Detection delay</th><th>Processing time</th></tr></thead><tbody>{comparisonRows.map((run) => <tr key={run.id}>
                <td>{run.displayName}</td><td>#{run.id} · {run.version}</td><td>{metricValue(run.precision)}</td><td>{metricValue(run.recall)}</td><td>{metricValue(run.f1)}</td><td>{metricValue(numericMetric(run.eval_metrics, "pr_auc"))}</td><td>{metricValue(numericMetric(run.eval_metrics, "false_positive_rate"))}</td><td>{metricValue(numericMetric(run.eval_metrics, "top_k_precision"))}</td><td>{metricValue(numericMetric(run.eval_metrics, "detection_delay_days"))}</td><td>{metricValue(numericMetric(run.eval_metrics, "processing_time_seconds"))}</td>
              </tr>)}</tbody></table></div>
            </> : <EmptyState title="No evaluation results available" message="Completed labeled experiments are required before model metrics can be compared." />}
          </Card>

          <Card title="Inference time across experiments" description="Persisted processing time from completed experiment metrics.">
            <div className="chart-wrap">{inferenceRows.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={inferenceRows}><CartesianGrid stroke="#edf1f7" vertical={false} /><XAxis dataKey="experiment" /><YAxis unit=" s" /><Tooltip /><Bar dataKey="time" name="Processing time (seconds)" fill="#527cf1" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer> : <div className="chart-empty">No recorded inference-time results available.</div>}</div>
          </Card>
        </>
      ) : <Card><EmptyState title="No evaluation results available" message="Completed experiments with held-out labeled data are required for evaluation metrics. Historical runs without usable labels are not included." /></Card>}

      <Card title="Score fusion and interaction surprise" description="Actual held-out branch and combined scores persisted for the selected experiment. Relational scores here are empirical edge-novelty values, not HGT inference.">
        {fusionLoading ? <Loading label="Loading persisted branch scores…" /> : scoreFusion?.scores.length ? <>
          {scoreFusion.truncated && <p className="small muted">Distribution is based on the first 5,000 persisted held-out score windows.</p>}
          <div className="dashboard-grid">
            {fusionSeries.map((series) => <Card title={`${series.name} distribution`} key={series.key}>
              <div className="chart-wrap compact-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={series.points}><CartesianGrid stroke="#edf1f7" vertical={false} /><XAxis dataKey="range" tick={{ fontSize: 9 }} /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" name="Observed windows" fill={series.key === "relational_score" ? "#30a77d" : series.key === "contextual_score" ? "#a276d2" : series.key === "risk_score" ? "#e19a40" : "#527cf1"} /></BarChart></ResponsiveContainer></div>
            </Card>)}
          </div>
          <div className="dashboard-grid">
            <Card title="Recorded fusion weights" description={`Weights from experiment #${scoreFusion.model_run_id}`}>
              {fusionWeights ? <div className="chart-wrap compact-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={Object.entries(fusionWeights).map(([name, value], index) => ({ name: name.replace("w_", ""), value: value * 100, fill: modelColors[index % modelColors.length] }))}><CartesianGrid stroke="#edf1f7" vertical={false} /><XAxis dataKey="name" /><YAxis unit="%" /><Tooltip /><Bar dataKey="value" name="Fusion weight">{Object.entries(fusionWeights).map(([name], index) => <Cell key={name} fill={modelColors[index % modelColors.length]} />)}</Bar></BarChart></ResponsiveContainer></div> : <div className="chart-empty">No recorded fusion weights available.</div>}
            </Card>
            <Card title="Mean branch contribution" description="Mean normalized branch score × its persisted fusion weight × 100.">
              {contributionData.length ? <div className="chart-wrap compact-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={contributionData}><CartesianGrid stroke="#edf1f7" vertical={false} /><XAxis dataKey="name" tick={{ fontSize: 9 }} /><YAxis /><Tooltip /><Legend /><Bar dataKey="contribution" name="Mean score contribution" fill="#527cf1">{contributionData.map((item) => <Cell key={item.name} fill={item.fill} />)}</Bar></BarChart></ResponsiveContainer></div> : <div className="chart-empty">No score and fusion-weight records available.</div>}
            </Card>
          </div>
        </> : <EmptyState title="No evaluation results available" message="No persisted held-out score windows exist for this experiment." />}
        {scoreFusion && <p className="small muted">{scoreFusion.total.toLocaleString()} held-out score windows recorded. This analysis describes the empirical fusion implementation and does not indicate that a Transformer or HGT was trained.</p>}
      </Card>

      {selected && <Card title="Experiment configuration" description="Recorded configuration and implementation details from the selected run.">
        <pre className="json-panel">{JSON.stringify(selected.train_config ?? {}, null, 2)}</pre>
        <p className="small muted">Top-K uses the top 5% of scored evaluation windows (K = {metrics?.top_k ?? "—"}). Delay is measured from the first labeled evaluation day.</p>
      </Card>}
      {!runs.length && !loading && <Card title="Research component evaluation status" description="Model scores are omitted until the corresponding architecture has been trained and evaluated.">
        <div className="coverage-list">
          {[
            ["Personal / Peer Context", "No evaluation results available"],
            ["Temporal Causal Transformer", "Model not yet trained"],
            ["Relational HGT", "Model not yet trained"],
            ["Three-branch fused architecture", "No evaluation results available"],
            ["HGT relation prediction", "No evaluation results available"],
          ].map(([label, status]) => <div key={label}><span className="coverage-check muted-check">·</span><span>{label}</span><small>{status}</small></div>)}
        </div>
      </Card>}
    </>
  );
}
