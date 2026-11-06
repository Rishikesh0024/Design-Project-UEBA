import { lazy, Suspense, useCallback, useEffect, useState, type FormEvent } from "react";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { api, ApiError, getToken, setToken, type Dataset, type User } from "./api/client";
import Layout, { type PageName } from "./components/Layout";
import { ErrorMessage } from "./components/common";
import { DEV_AUTH_BYPASS, DEV_BYPASS_USER } from "./config/auth";

const AlertsPage = lazy(() => import("./pages/AlertsPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const DatasetPage = lazy(() => import("./pages/DatasetPage"));
const DetectionPage = lazy(() => import("./pages/DetectionPage"));
const EvaluationPage = lazy(() => import("./pages/EvaluationPage"));
const ExplorerPage = lazy(() => import("./pages/ExplorerPage"));
const ProfilesPage = lazy(() => import("./pages/ProfilesPage"));

type AuthResponse = { access_token: string; token_type: string };

type Route =
  | { kind: "page"; page: PageName }
  | { kind: "login" }
  | { kind: "register" };

const pagePaths: Record<PageName, string> = {
  Dashboard: "/dashboard",
  "Dataset Upload": "/dataset-upload",
  "Activity Explorer": "/activity-explorer",
  "Behaviour Profiles": "/behaviour-profiles",
  "Anomaly Detection": "/anomaly-detection",
  Alerts: "/alerts",
  Evaluation: "/evaluation",
};

const routePaths = new Map<string, Route>([
  ...Object.entries(pagePaths).map(([page, path]) => [path, { kind: "page", page: page as PageName }] as const),
  ["/login", { kind: "login" }],
  ["/register", { kind: "register" }],
]);

function routeForPath(path: string): Route | null {
  const clean = path.replace(/\/+$/, "") || "/";
  if (clean === "/") return null;
  return routePaths.get(clean) ?? null;
}

function pathForRoute(route: Route): string {
  if (route.kind === "login") return "/login";
  if (route.kind === "register") return "/register";
  return pagePaths[route.page];
}

function defaultRoute(): Route {
  return DEV_AUTH_BYPASS ? { kind: "page", page: "Dashboard" } : { kind: "login" };
}

export default function App() {
  const [route, setRoute] = useState<Route>(() => {
    const matched = routeForPath(window.location.pathname);
    return matched ?? defaultRoute();
  });

  const [user, setUser] = useState<User | null>(() => {
    if (route.kind === "login" || route.kind === "register") {
      return null;
    }
    return DEV_AUTH_BYPASS ? DEV_BYPASS_USER : null;
  });

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState<number | null>(() => {
    const stored = localStorage.getItem("ueba_dataset_id");
    return stored ? Number(stored) : null;
  });
  const [authLoading, setAuthLoading] = useState(!DEV_AUTH_BYPASS && Boolean(getToken()));
  const [workspaceError, setWorkspaceError] = useState("");
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);

  function navigate(nextRoute: Route, replace = false) {
    const method = replace ? "replaceState" : "pushState";
    window.history[method](null, "", pathForRoute(nextRoute));
    setRoute(nextRoute);
  }

  const refreshDatasets = useCallback(async () => {
    try {
      const rows = await api<Dataset[]>("/datasets");
      setDatasets(rows);
      setApiOnline(true);
      setWorkspaceError("");
    } catch (reason) {
      setDatasets([]);
      if (reason instanceof ApiError && reason.status === 0) {
        setApiOnline(false);
      }
      if (!DEV_AUTH_BYPASS) {
        setWorkspaceError(reason instanceof Error ? reason.message : "Could not load datasets.");
      }
    }
  }, []);

  useEffect(() => {
    const syncRoute = () => {
      const matched = routeForPath(window.location.pathname);
      const next = matched ?? defaultRoute();
      setRoute(next);
      if (!matched) {
        window.history.replaceState(null, "", pathForRoute(next));
      }
      // If navigating to a workspace page in bypass mode and user is null, restore bypass user
      if (DEV_AUTH_BYPASS && next.kind === "page") {
        setUser((prev) => prev ?? DEV_BYPASS_USER);
      }
    };
    syncRoute();
    window.addEventListener("popstate", syncRoute);
    return () => window.removeEventListener("popstate", syncRoute);
  }, []);

  useEffect(() => {
    if (DEV_AUTH_BYPASS) return;
    if (!getToken()) {
      setAuthLoading(false);
      return;
    }
    let active = true;
    api<User>("/auth/me")
      .then((account) => {
        if (!active) return;
        setUser(account);
        setApiOnline(true);
        if (route.kind !== "page") navigate({ kind: "page", page: "Dashboard" }, true);
      })
      .catch(() => {
        setToken(null);
        if (active) setUser(null);
      })
      .finally(() => active && setAuthLoading(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!user) return;
    void refreshDatasets();
  }, [user, refreshDatasets]);

  useEffect(() => {
    if (!DEV_AUTH_BYPASS && !authLoading && !user && route.kind === "page") {
      navigate({ kind: "login" }, true);
    }
  }, [authLoading, route, user]);

  useEffect(() => {
    if (datasetId) localStorage.setItem("ueba_dataset_id", String(datasetId));
    else localStorage.removeItem("ueba_dataset_id");
  }, [datasetId]);

  async function authenticate(email: string, password: string, fullName?: string) {
    setWorkspaceError("");
    try {
      if (fullName) {
        await api<User>("/auth/register", {
          method: "POST",
          body: JSON.stringify({ email, password, full_name: fullName, role: "analyst" }),
        });
      }
      const body = new URLSearchParams({ username: email, password });
      const response = await api<AuthResponse>("/auth/login", { method: "POST", body });
      setToken(response.access_token);
      setUser(await api<User>("/auth/me"));
      setApiOnline(true);
      navigate({ kind: "page", page: "Dashboard" }, true);
    } catch (reason) {
      if (DEV_AUTH_BYPASS) {
        // In bypass mode, allow signing back in directly even if backend is offline
        setUser(DEV_BYPASS_USER);
        navigate({ kind: "page", page: "Dashboard" }, true);
      } else {
        setWorkspaceError(reason instanceof Error ? reason.message : "Authentication failed.");
      }
    }
  }

  function logout() {
    setToken(null);
    setUser(null);
    setDatasets([]);
    setDatasetId(null);
    navigate({ kind: "login" }, false);
  }

  if (authLoading) return <div className="auth-loading">Checking analyst session…</div>;

  if (route.kind === "login" || route.kind === "register") {
    return (
      <AuthScreen
        register={route.kind === "register"}
        onAuthenticate={authenticate}
        onSwitch={() => navigate({ kind: route.kind === "register" ? "login" : "register" })}
        error={workspaceError}
      />
    );
  }

  if (!DEV_AUTH_BYPASS && !user) return null;

  const dataset = datasets.find((item) => item.id === datasetId) ?? null;
  const activePage: PageName = route.kind === "page" ? route.page : "Dashboard";

  let content;
  switch (activePage) {
    case "Dashboard": content = <DashboardPage datasetId={datasetId} dataset={dataset} />; break;
    case "Dataset Upload": content = <DatasetPage datasets={datasets} datasetId={datasetId} refreshDatasets={refreshDatasets} onSelectDataset={setDatasetId} />; break;
    case "Activity Explorer": content = <ExplorerPage datasetId={datasetId} />; break;
    case "Behaviour Profiles": content = <ProfilesPage datasetId={datasetId} />; break;
    case "Anomaly Detection": content = <DetectionPage datasetId={datasetId} dataset={dataset} />; break;
    case "Alerts": content = <AlertsPage datasetId={datasetId} />; break;
    case "Evaluation": content = <EvaluationPage datasetId={datasetId} dataset={dataset} />; break;
  }

  return (
    <Layout
      page={activePage}
      onNavigate={(page) => navigate({ kind: "page", page })}
      user={user ?? DEV_BYPASS_USER}
      datasets={datasets}
      datasetId={datasetId}
      onDatasetChange={setDatasetId}
      onLogout={logout}
      isBypass={DEV_AUTH_BYPASS}
      apiOnline={apiOnline}
    >
      {workspaceError && <ErrorMessage>{workspaceError}</ErrorMessage>}
      <Suspense fallback={<div className="loading">Opening workspace page…</div>}>{content}</Suspense>
    </Layout>
  );
}

function AuthScreen({
  register,
  onAuthenticate,
  onSwitch,
  error,
}: {
  register: boolean;
  onAuthenticate: (email: string, password: string, fullName?: string) => Promise<void>;
  onSwitch: () => void;
  error: string;
}) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    await onAuthenticate(email, password, register ? fullName : undefined);
    setBusy(false);
  }

  return (
    <div className="auth-screen">
      <div className="auth-aside">
        <div className="brand auth-brand">
          <div className="brand-mark"><ShieldCheck size={23} /></div>
          <div><strong>UEBA</strong><span>Security analytics</span></div>
        </div>
        <div className="auth-aside-copy">
          <div className="eyebrow">USER & ENTITY BEHAVIOUR ANALYTICS</div>
          <h1>Understand behaviour.<br /><span>Find what matters.</span></h1>
          <p>One workspace for activity investigation, robust user baselines, risk detection, and accountable alert review.</p>
        </div>
        <div className="auth-aside-footer">
          <span className="system-status"><i /> Secure API connection</span>
          <small>PostgreSQL-backed workspace</small>
        </div>
      </div>
      <div className="auth-main">
        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          <div className="auth-mobile-brand"><ShieldCheck size={24} /> UEBA</div>
          <div className="eyebrow">{register ? "CREATE WORKSPACE ACCOUNT" : "WELCOME BACK"}</div>
          <h2>{register ? "Create your account" : "Sign in to UEBA"}</h2>
          <p>{register ? "Create an analyst account to access your workspace." : "Use your analyst account to continue."}</p>
          {error && <ErrorMessage>{error}</ErrorMessage>}
          {register && (
            <label className="field-label">
              Full name
              <input required value={fullName} onChange={(event) => setFullName(event.target.value)} autoComplete="name" />
            </label>
          )}
          <label className="field-label">
            Work email
            <input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
          </label>
          <label className="field-label">
            Password
            <input
              required
              type="password"
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={register ? "new-password" : "current-password"}
            />
          </label>
          <button className="button primary auth-submit" disabled={busy}>
            {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
            <ArrowRight size={16} />
          </button>
          <div className="auth-switch">
            {register ? "Already have an account?" : "New to this workspace?"}
            <button type="button" onClick={onSwitch}>
              {register ? "Sign in" : "Create account"}
            </button>
          </div>
          <div className="auth-disclaimer">
            Access is authenticated through the UEBA API. Dataset and analyst review records are stored in the configured PostgreSQL database.
          </div>
        </form>
      </div>
    </div>
  );
}
