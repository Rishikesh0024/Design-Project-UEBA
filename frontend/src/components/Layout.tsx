import { useState, type ReactNode } from "react";
import {
  Activity,
  Bell,
  BrainCircuit,
  ChevronDown,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  Search,
  Settings,
  ShieldCheck,
  UploadCloud,
  Users,
} from "lucide-react";
import type { Dataset, User } from "../api/client";

export type PageName =
  | "Dashboard"
  | "Dataset Upload"
  | "Activity Explorer"
  | "Behaviour Profiles"
  | "Anomaly Detection"
  | "Alerts"
  | "Evaluation";

const navigation = [
  { label: "Dashboard", icon: LayoutDashboard },
  { label: "Dataset Upload", icon: UploadCloud },
  { label: "Activity Explorer", icon: Search },
  { label: "Behaviour Profiles", icon: Users },
  { label: "Anomaly Detection", icon: BrainCircuit },
  { label: "Alerts", icon: Bell },
  { label: "Evaluation", icon: FlaskConical },
] as const;

type Props = {
  page: PageName;
  onNavigate: (page: PageName) => void;
  user: User;
  datasets: Dataset[];
  datasetId: number | null;
  onDatasetChange: (id: number | null) => void;
  onLogout: () => void;
  isBypass?: boolean;
  apiOnline?: boolean | null;
  children: ReactNode;
};

export default function Layout({
  page,
  onNavigate,
  user,
  datasets,
  datasetId,
  onDatasetChange,
  onLogout,
  isBypass,
  apiOnline,
  children,
}: Props) {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={23} /></div>
          <div>
            <strong>UEBA</strong>
            <span>Security analytics</span>
          </div>
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav className="primary-nav" aria-label="Primary navigation">
          {navigation.map(({ label, icon: Icon }) => (
            <button
              className={`nav-item ${page === label ? "active" : ""}`}
              key={label}
              onClick={() => onNavigate(label)}
              aria-current={page === label ? "page" : undefined}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
              {label === "Alerts" && <span className="nav-indicator" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className={`system-status ${apiOnline === false ? "offline" : ""}`}>
            <i /> {apiOnline === false ? "API offline (Dev view)" : "API workspace"}
          </div>
          {isBypass && <span className="dev-bypass-pill">Dev bypass active</span>}
          <div className="sidebar-foot">Behaviour monitoring<br />and investigation</div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-context">
            <span>Workspace</span><b>/</b><strong>{page}</strong>
          </div>
          <div className="topbar-actions">
            <label className="dataset-select">
              <Activity size={15} />
              <select
                aria-label="Select active dataset"
                value={datasetId ?? ""}
                onChange={(event) =>
                  onDatasetChange(event.target.value ? Number(event.target.value) : null)
                }
              >
                <option value="">Select dataset</option>
                {datasets.map((dataset) => (
                  <option value={dataset.id} key={dataset.id}>
                    {dataset.is_demo ? "[DEMO] " : ""}{dataset.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} />
            </label>
            <details className="profile-menu">
              <summary aria-label="Open profile menu">
                <span className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</span>
                <span className="profile-name">{user.full_name}</span>
                <ChevronDown size={15} />
              </summary>
              <div className="profile-dropdown">
                <div className="profile-meta">
                  <strong>{user.full_name}</strong>
                  <span>{user.email}</span>
                </div>
                <button onClick={() => setSettingsOpen(true)}>
                  <Settings size={16} /> Settings
                </button>
                <button className="logout-item" onClick={onLogout}>
                  <LogOut size={16} /> Logout
                </button>
              </div>
            </details>
          </div>
        </header>
        <main className="content-area">{children}</main>
      </div>

      {settingsOpen && (
        <div className="modal-backdrop" role="presentation" onClick={() => setSettingsOpen(false)}>
          <section
            className="modal settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <div><h2 id="settings-title">Account settings</h2><p>Signed-in workspace account</p></div>
              <button className="icon-button" onClick={() => setSettingsOpen(false)} aria-label="Close settings">×</button>
            </div>
            <div className="settings-row"><span>Name</span><strong>{user.full_name}</strong></div>
            <div className="settings-row"><span>Email</span><strong>{user.email}</strong></div>
            <div className="settings-row"><span>Role</span><strong className="capitalize">{user.role}</strong></div>
            <p className="muted small">Account and access policy are managed by the API.</p>
          </section>
        </div>
      )}
    </div>
  );
}
