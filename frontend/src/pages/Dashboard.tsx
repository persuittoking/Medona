import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { ExternalNotification, Summary, TopRow } from "../api/types";
import { MahallaMap } from "../components/MahallaMap";
import { SubjectSwitch } from "../components/SubjectSwitch";
import { Empty, ErrorBox, Skeleton, ZoneBadge } from "../components/ui";
import { useAuth } from "../lib/auth";
import { fmtAge, fmtMinutes, fmtPct, fmtWeeks } from "../lib/format";
import { useSubject } from "../lib/subject";
import { pointsFor, toDots, usePolyclinicMap } from "./PolyclinicMap";

const ACTIVE_LABEL = { pregnancy: "Faol homiladorlar", child: "Kuzatuvdagi bolalar", all: "Jami kuzatuvda" } as const;

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
  const [subject, setSubject] = useSubject();
  const summary = useQuery({ queryKey: ["summary", subject], queryFn: () => api<Summary>(`/api/dashboard/summary?subject=${subject}`), refetchInterval: 15000 });
  const trend = useQuery({ queryKey: ["trend", subject], queryFn: () => api<{ week_start: string; red: number; yellow: number }[]>(`/api/dashboard/trend?subject=${subject}`) });
  const top = useQuery({ queryKey: ["top", subject], queryFn: () => api<TopRow[]>(`/api/dashboard/top?subject=${subject}`), refetchInterval: 15000 });
  const extNotifs = useQuery({ queryKey: ["external-notifications"], queryFn: () => api<ExternalNotification[]>("/api/external/notifications?limit=5"), refetchInterval: 15000 });
  const map = usePolyclinicMap(subject);
  const s = summary.data;
  const canEnterExternal = user?.role === "nurse" || user?.role === "doctor";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1>Bosh sahifa</h1>
          <p className="mt-1 text-sm text-slate-500">{user?.polyclinic_name}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canEnterExternal && (
            <Link to="/external-visit" className="btn-ghost btn-sm ring-1 ring-slate-300">
              + Boshqa poliklinika bemori
            </Link>
          )}
          <SubjectSwitch value={subject} onChange={setSubject} counts={s?.counts} />
        </div>
      </div>

      {extNotifs.data && extNotifs.data.length > 0 && (
        <div className="rounded-card border border-indigo-200 bg-indigo-50/70 p-3 text-sm text-indigo-950">
          <div className="font-semibold">📥 Tashqi natija kelib tushdi</div>
          <ul className="mt-1 space-y-1 text-xs">
            {extNotifs.data.map((n) => (
              <li key={`${n.kind}-${n.id}`} className="flex flex-wrap items-center gap-2">
                <Link
                  to={n.kind === "child" ? `/children/${n.newborn_id}` : `/patients/${n.patient_id}`}
                  className="font-mono font-semibold text-brand-800 hover:underline"
                >
                  {n.code}
                </Link>
                <span>· {n.mahalla}</span>
                <span className="rounded bg-white px-1.5 py-0.5 font-medium text-indigo-800 ring-1 ring-indigo-200">
                  {n.badge_uz}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.error ? <ErrorBox error={summary.error} /> : !s ? <Skeleton className="h-24" /> : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 xl:grid-cols-7">
          <Kpi label={ACTIVE_LABEL[subject]} value={s.active} />
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
              dots={toDots(pointsFor(map.data.points, subject), nav)} />
          )}
        </section>

        <section className="card">
          <h2 className="mb-4">Eng yuqori xavf · 10 nafar</h2>
          {top.isLoading ? <Skeleton className="h-96" /> : !top.data?.length ? <Empty text="Kuzatuvda hech kim yo'q" /> : (
            <ul className="divide-y divide-slate-100">
              {top.data.map((r) => (
                <li key={`${r.subject}-${r.pregnancy_id ?? r.newborn_id}`}>
                  <Link to={r.subject === "child" ? `/children/${r.newborn_id}` : `/patients/${r.patient_id}`}
                    className="flex items-start gap-3 py-2 hover:bg-slate-50">
                    <ZoneBadge zone={r.zone} />
                    <div className="min-w-0 flex-1">
                      <div className="flex justify-between gap-2">
                        <span className="font-mono text-sm font-medium">{r.code}</span>
                        {r.subject === "pregnancy" && <span className="text-xs tabular-nums text-slate-500">{fmtPct(r.risk)}</span>}
                      </div>
                      <div className="truncate text-xs text-slate-500">
                        {r.subject === "child" ? `Bola · ${fmtAge(r.child_age_days ?? 0)}` : `Homilador · ${fmtWeeks(r.gestational_weeks ?? 0)}`} · {r.main_reason ?? "—"}
                      </div>
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
        <p className="mb-4 text-xs text-slate-500">Qizil / sariq baholanganlar soni ({subject === "child" ? "bolalar" : subject === "all" ? "homiladorlar va bolalar" : "homiladorlar"}), oxirgi 12 hafta</p>
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
