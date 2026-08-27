import { AlertTriangle, Check, ChevronRight, Info, LoaderCircle, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

export function PageHeader({ eyebrow, title, description, actions }: {
  eyebrow?: string; title: string; description?: string; actions?: ReactNode;
}) {
  return <header className="page-header">
    <div>
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h1>{title}</h1>
      {description && <p className="page-description">{description}</p>}
    </div>
    {actions && <div className="page-actions">{actions}</div>}
  </header>;
}

export function Card({ title, description, actions, children, className = "" }: {
  title?: string; description?: string; actions?: ReactNode; children: ReactNode; className?: string;
}) {
  return <section className={`card ${className}`}>
    {(title || actions) && <header className="card-header">
      <div>{title && <h2>{title}</h2>}{description && <p>{description}</p>}</div>
      {actions}
    </header>}
    {children}
  </section>;
}

export function Notice({ tone = "info", title, children }: { tone?: "info" | "warning" | "danger" | "success"; title: string; children: ReactNode }) {
  const Icon = tone === "warning" || tone === "danger" ? AlertTriangle : tone === "success" ? Check : Info;
  return <div className={`notice notice-${tone}`} role={tone === "danger" ? "alert" : "status"}>
    <Icon aria-hidden="true" size={19} />
    <div><strong>{title}</strong><div>{children}</div></div>
  </div>;
}

export function Loading({ label = "불러오는 중" }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle className="spin" aria-hidden="true" /> <span>{label}</span></div>;
}

export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><ShieldCheck aria-hidden="true" /><h3>{title}</h3><p>{children}</p>{action}</div>;
}

export function DefinitionList({ items }: { items: Array<{ label: string; value: ReactNode }> }) {
  return <dl className="definition-list">{items.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>;
}

export function StepRow({ label, detail, status }: { label: string; detail: string; status: string }) {
  const done = ["SUCCEEDED", "COMPLETED", "RESOLVED"].includes(status);
  return <div className="step-row">
    <span className={`step-icon ${done ? "step-done" : ""}`}>{done ? <Check size={15} /> : <ChevronRight size={15} />}</span>
    <div><strong>{label}</strong><p>{detail}</p></div>
  </div>;
}

export function friendlyError(error: unknown): string {
  return error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.";
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium", timeStyle: "short",
  }).format(date);
}

export function shortId(value?: string | null): string {
  if (!value) return "—";
  return value.length > 14 ? `${value.slice(0, 7)}…${value.slice(-5)}` : value;
}

export function textValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "예" : "아니요";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}
