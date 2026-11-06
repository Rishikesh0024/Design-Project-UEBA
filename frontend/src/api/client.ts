import { DEV_AUTH_BYPASS } from "../config/auth";

export const API_URL =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
const DEMO_API_URL = API_URL.replace(/\/api\/v1\/?$/, "/api");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  return localStorage.getItem("ueba_access_token");
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem("ueba_access_token", token);
  else localStorage.removeItem("ueba_access_token");
}

function getEmptyFallbackForPath(path: string): unknown {
  const cleanPath = path.split("?")[0];
  if (
    cleanPath === "/alerts/paged"
  ) {
    return { items: [], total: 0 };
  }
  if (
    cleanPath === "/alerts/summary"
  ) {
    return {
      total_alerts: 0,
      average_risk_score: 0,
      severity_counts: { critical: 0, high: 0, medium: 0, low: 0 },
      score_distribution: [
        { range: "0–25", count: 0 },
        { range: "25–50", count: 0 },
        { range: "50–75", count: 0 },
        { range: "75–100", count: 0 },
      ],
    };
  }
  if (/^\/evaluation\/\d+\/graph\/snapshots$/.test(cleanPath)) {
    return { items: [] };
  }
  if (/^\/evaluation\/\d+\/graph$/.test(cleanPath)) {
    return {
      snapshot_date: null,
      snapshot_count: 0,
      node_counts: { user: 0, resource: 0, device: 0 },
      relationship_count: 0,
      graph_density: null,
      displayed_relationship_count: 0,
      truncated: false,
      source: "No backend data available",
      nodes: [],
      edges: [],
    };
  }
  if (/^\/evaluation\/\d+\/score-fusion$/.test(cleanPath)) {
    return { model_run_id: null, weights: null, scores: [], total: 0, truncated: false };
  }
  if (
    cleanPath === "/datasets" ||
    cleanPath.endsWith("/alerts") ||
    cleanPath.endsWith("/reviews") ||
    cleanPath.endsWith("/events") ||
    cleanPath.startsWith("/profiles") ||
    cleanPath.startsWith("/detection/runs") ||
    cleanPath.startsWith("/evaluation") ||
    cleanPath.includes("/activity-over-time")
  ) {
    return [];
  }
  if (
    cleanPath.startsWith("/activity/events") ||
    cleanPath.startsWith("/detection/scores")
  ) {
    return { items: [], total: 0 };
  }
  if (cleanPath.startsWith("/detection/summary")) {
    return { scored_windows: 0, normal_windows: 0, anomalous_windows: 0 };
  }
  if (cleanPath.startsWith("/analytics/dashboard")) {
    return {
      total_events: 0,
      unique_users: 0,
      total_alerts: 0,
      high_risk_alerts: 0,
      dataset_name: null,
      last_run: null,
    };
  }
  return null;
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  baseUrl = API_URL,
): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body instanceof URLSearchParams) {
    headers.set("Content-Type", "application/x-www-form-urlencoded");
  } else if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers,
    });
  } catch (err) {
    const isNetworkError =
      err instanceof TypeError &&
      (err.message === "Failed to fetch" ||
        err.message.includes("NetworkError") ||
        err.message.includes("fetch failed"));
    if (isNetworkError) {
      if (DEV_AUTH_BYPASS && (!options.method || options.method.toUpperCase() === "GET")) {
        const fallback = getEmptyFallbackForPath(path);
        if (fallback !== null) return fallback as T;
      }
      throw new ApiError(
        `Backend API unreachable at ${baseUrl}. Ensure the backend server is running.`,
        0,
      );
    }
    throw err;
  }

  if (!response.ok) {
    // If DEV_AUTH_BYPASS is active and the API returns 401 on a GET request,
    // gracefully return safe empty fallback data instead of throwing "Not authenticated"
    if (response.status === 401 && DEV_AUTH_BYPASS) {
      if (!options.method || options.method.toUpperCase() === "GET") {
        const fallback = getEmptyFallbackForPath(path);
        if (fallback !== null) return fallback as T;
      }
    }

    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item: { msg?: string }) => item.msg).join("; ")
          : `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function demoApi<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  return api<T>(path, options, DEMO_API_URL);
}

export type User = {
  id: number;
  email: string;
  full_name: string;
  role: string;
};

export type Dataset = {
  id: number;
  name: string;
  version: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  unique_users: number;
  date_from: string | null;
  date_to: string | null;
  has_labels: boolean;
  is_demo: boolean;
  created_at: string;
  schema_info?: Record<string, unknown> | null;
  quality_report?: Record<string, unknown> | null;
};

export type DemoDataset = {
  key: string;
  demo_id: string;
  name: string;
  description: string;
  seed: number;
  dataset_type: string;
  source_label: string;
  format: string;
  record_count: number;
  user_count: number;
  activity_types: string[];
  timestamp_from: string;
  timestamp_to: string;
};

export type DemoPreview = {
  key: string;
  demo_id: string;
  name: string;
  dataset_type: string;
  source_label: string;
  format: string;
  record_count: number;
  user_count: number;
  activity_types: string[];
  timestamp_range: { start: string; end: string };
  timestamp_from: string;
  timestamp_to: string;
  columns: { name: string; type: string }[];
  sample_records: Record<string, string | number>[];
  activity_summary: { activity: string; count: number }[];
  user_summary: {
    user_id: string;
    role: string;
    department: string;
    record_count: number;
    labelled_suspicious_records: number;
  }[];
  schema: Record<string, unknown>;
};

export type ActivityEvent = {
  id: number;
  dataset_id: number;
  event_id: string;
  user_id: string;
  activity: string;
  timestamp: string;
  pc: string | null;
  resource: string | null;
  label: number;
};

export type AlertEvidence = {
  id: number;
  event_id: string;
  activity: string | null;
  timestamp: string | null;
  resource: string | null;
};

export type Alert = {
  id: number;
  alert_uid: string;
  dataset_id: number;
  user_id: string;
  window_date: string;
  primary_activity: string;
  temporal_score: number;
  relational_score: number;
  contextual_score: number;
  risk_score: number;
  threshold_value: number;
  severity: string;
  status: string;
  verdict: string | null;
  rule_flags: string[] | null;
  explanation: string | null;
  label: number;
  created_at: string;
  evidence: AlertEvidence[];
};

export type EvaluationGraphNode = {
  id: string;
  type: "user" | "resource" | "device";
  label: string;
};

export type EvaluationGraphEdge = {
  id: string;
  source: string;
  target: string;
  type: "user-resource" | "user-device";
  label: string;
  event_count: number;
};

export type EvaluationGraph = {
  snapshot_date: string | null;
  snapshot_count: number;
  node_counts: { user: number; resource: number; device: number };
  relationship_count: number;
  graph_density: number | null;
  displayed_relationship_count: number;
  truncated: boolean;
  source: string;
  nodes: EvaluationGraphNode[];
  edges: EvaluationGraphEdge[];
};

export type Profile = {
  id: number;
  dataset_id: number;
  user_id: string;
  role: string | null;
  department: string | null;
  total_events: number;
  active_days: number;
  baseline: Record<string, unknown> | null;
  last_activity: string | null;
};

export type RiskScore = {
  user_id: string;
  window_date: string;
  temporal_score: number;
  relational_score: number;
  contextual_score: number;
  risk_score: number;
  threshold_value: number;
  severity: string;
  is_anomaly: boolean;
  label: number;
};

export type ModelRun = {
  id: number;
  dataset_id?: number;
  branch: string;
  version: string;
  status: string;
  train_config: Record<string, unknown> | null;
  eval_metrics: Record<string, number | number[] | number[][] | null> | null;
  train_rows: number;
  eval_rows: number;
  created_at: string;
  finished_at: string | null;
};
