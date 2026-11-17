import { Component, type ReactNode } from "react";
import type { Zone } from "../api/types";
import { ZONE_LABEL } from "../i18n/uz";

const ZONE_CLS: Record<Zone, string> = {
  red: "bg-zred text-white",
  yellow: "bg-zyellow text-slate-900",
  green: "bg-zgreen text-white",
};

export function ZoneBadge({ zone, size = "sm" }: { zone: Zone; size?: "sm" | "lg" }) {
  const cls = size === "lg" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full font-semibold ${cls} ${ZONE_CLS[zone]}`}>
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {ZONE_LABEL[zone]}
    </span>
  );
}

export function SyntheticBadge() {
  return (
    <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
      Sintetik ma'lumot (demo)
    </span>
  );
}

export function Skeleton({ className = "h-24" }: { className?: string }) {
  return <div className={`animate-pulse rounded-xl bg-slate-100 ${className}`} />;
}

export function Empty({ text }: { text: string }) {
  return <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{text}</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      {error instanceof Error ? error.message : "Xatolik yuz berdi"}
    </div>
  );
}

export function SourceTag({ source }: { source: "ai" | "template" }) {
  return source === "ai" ? (
    <span className="rounded bg-violet-100 px-1.5 py-0.5 text-xs font-semibold text-violet-800">AI (Gemini)</span>
  ) : (
    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-semibold text-slate-700">Shablon</span>
  );
}

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error)
      return (
        <div className="mx-auto max-w-lg p-8 text-center">
          <h1 className="text-lg font-semibold">Sahifada xatolik yuz berdi</h1>
          <p className="mt-2 text-sm text-slate-500">{this.state.error.message}</p>
          <button className="btn-primary mt-4" onClick={() => window.location.reload()}>
            Qayta yuklash
          </button>
        </div>
      );
    return this.props.children;
  }
}
