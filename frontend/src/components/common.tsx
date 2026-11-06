import type { ReactNode } from "react";
import { AlertCircle, LoaderCircle } from "lucide-react";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function Card({
  title,
  description,
  actions,
  children,
  className = "",
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || description || actions) && (
        <div className="card-heading">
          <div>
            {title && <h2>{title}</h2>}
            {description && <p>{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function MetricCard({
  label,
  value,
  hint,
  icon,
  tone = "blue",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon: ReactNode;
  tone?: "blue" | "green" | "amber" | "red" | "violet";
}) {
  return (
    <div className="metric-card card">
      <div className={`metric-icon ${tone}`}>{icon}</div>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><AlertCircle size={21} /></div>
      <strong>{title}</strong>
      <p>{message}</p>
      {action}
    </div>
  );
}

export function Loading({ label = "Loading data…" }: { label?: string }) {
  return <div className="loading"><LoaderCircle className="spin" size={18} />{label}</div>;
}

export function ErrorMessage({ children }: { children: ReactNode }) {
  return <div className="error-message"><AlertCircle size={17} />{children}</div>;
}

export function formatNumber(value: number | null | undefined): string {
  return value == null ? "—" : new Intl.NumberFormat().format(value);
}

export function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "—";
}
