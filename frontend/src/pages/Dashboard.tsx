import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { Summary, TopRow } from "../api/types";
import { MahallaMap } from "../components/MahallaMap";
import { Empty, ErrorBox, Skeleton, ZoneBadge } from "../components/ui";
import { useAuth } from "../lib/auth";
import { fmtMinutes, fmtPct, fmtWeeks } from "../lib/format";
import { usePolyclinicMap } from "./PolyclinicMap";

export function Kpi({ label, value, tone, hint }: { label: string; value: string | number; tone?: string; hint?: string }) {
  return (
    <div className="card-tight">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${tone ?? "text-slate-900"}`}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const nav = useNavigate();
  const summary = useQuery({ queryKey: ["summary"], queryFn: () => api<Summary>("/api/dashboard/summary"), refetchInterval: 15000 });
  const trend = useQuery({ queryKey: ["trend"], queryFn: () => api<{ week_start: string; red: number; yellow: number }[]>("/api/dashboard/trend") });
  const top = useQuery({ queryKey: ["top"], queryFn: () => api<TopRow[]>("/api/dashboard/top"), refetchInterval: 15000 });
  const map = usePolyclinicMap();
  const s = summary.data;

  return (
    <div className="space-y-6">
      <div>
        <h1>Bosh sahifa</h1>
        <p className="mt-1 text-sm text-slate-500">{user?.polyclinic_name}</p>
      </div>

      {summary.error ? <ErrorBox error={summary.error} /> : !s ? <Skeleton className="h-24" /> : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 xl:grid-cols-7">
          <Kpi label="Faol homiladorlar" value={s.active_pregnancies} />
          <Kpi label="Qizil zona" value={s.red} tone="text-zred" />
          <Kpi label="Sariq zona" value={s.yellow} tone="text-amber-600" />
          <Kpi label="Yashil zona" value={s.green} tone="text-zgreen" />
          <Kpi label="Ochiq ogohlantirishlar" value={s.open_alerts} />
          <Kpi label="SLA buzilgan" value={s.sla_breaches} />
          <Kpi label="Javob vaqti (mediana)" value={fmtMinutes(s.median_ack_minutes)} />
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <section className="card">
          <div className="mb-4 flex items-center justify-between">
            <h2>Mahalla xaritasi</h2>
            <Link to="/map" className="text-sm font-medium text-brand-700 hover:underline">To'liq ekran →</Link>
          </div>
          {map.error ? <ErrorBox error={map.error} /> : !map.data ? <Skeleton className="h-[440px]" /> : (
            <MahallaMap height={440}
              areas={map.data.mahallas.map((m) => ({ key: String(m.id), boundary: m.boundary, label: m.name }))}
              dots={map.data.points.map((p) => ({ key: p.patient_id, lat: p.lat, lon: p.lon, zone: p.zone, label: p.code,
                onClick: () => nav(`/patients/${p.patient_id}`) }))} />
          )}
        </section>

        <section className="card">
          <h2 className="mb-4">Eng yuqori xavf · 10 nafar</h2>
          {top.isLoading ? <Skeleton className="h-96" /> : !top.data?.length ? <Empty text="Faol homiladorlar yo'q" /> : (
            <ul className="divide-y divide-slate-100">
              {top.data.map((r) => (
                <li key={r.pregnancy_id}>
                  <Link to={`/patients/${r.patient_id}`} className="flex items-start gap-3 py-2 hover:bg-slate-50">
                    <ZoneBadge zone={r.zone} />
                    <div className="min-w-0 flex-1">
                      <div className="flex justify-between gap-2">
                        <span className="font-mono text-sm font-medium">{r.code}</span>
                        <span className="text-xs tabular-nums text-slate-500">{fmtPct(r.risk)}</span>
                      </div>
                      <div className="truncate text-xs text-slate-500">{fmtWeeks(r.gestational_weeks)} · {r.main_reason ?? "—"}</div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="card">
        <h2 className="mb-1">Haftalik dinamika</h2>
        <p className="mb-4 text-xs text-slate-500">Qizil / sariq baholangan homiladorlar soni, oxirgi 12 hafta</p>
        {trend.isLoading ? <Skeleton className="h-56" /> : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trend.data} margin={{ left: -20, right: 8, top: 8 }}>
              <CartesianGrid stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="week_start" tickFormatter={(v: string) => v.slice(5)} fontSize={11} stroke="#94a3b8" />
              <YAxis allowDecimals={false} fontSize={11} stroke="#94a3b8" />
              <RTooltip />
              <Line type="monotone" dataKey="red" name="Qizil" stroke="#DC2626" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="yellow" name="Sariq" stroke="#F59E0B" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </section>
    </div>
  );
}
