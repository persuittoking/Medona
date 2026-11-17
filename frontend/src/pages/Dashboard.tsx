import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip } from "react-leaflet";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import { api } from "../api/client";
import type { DistrictStat, Summary, TopRow } from "../api/types";
import { Empty, ErrorBox, Skeleton, ZoneBadge } from "../components/ui";
import { useAuth } from "../lib/auth";
import { fmtMinutes, fmtPct, fmtWeeks } from "../lib/format";

function Kpi({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div className="card">
      <div className="text-xs font-medium text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-bold ${tone ?? "text-slate-800"}`}>{value}</div>
    </div>
  );
}

/** Colour by share of RED: green (0%) -> amber -> red (>=20%). */
function shareColor(share: number): string {
  if (share >= 0.15) return "#DC2626";
  if (share >= 0.08) return "#F97316";
  if (share >= 0.03) return "#F59E0B";
  return "#16A34A";
}

export default function Dashboard() {
  const { user } = useAuth();
  const [district, setDistrict] = useState<number | null>(null);
  const qs = district ? `?district_id=${district}` : "";
  const summary = useQuery({ queryKey: ["summary", district], queryFn: () => api<Summary>(`/api/dashboard/summary${qs}`), refetchInterval: 15000 });
  const districts = useQuery({ queryKey: ["districts-stat"], queryFn: () => api<DistrictStat[]>("/api/dashboard/districts"), refetchInterval: 15000 });
  const trend = useQuery({ queryKey: ["trend", district], queryFn: () => api<{ week_start: string; red: number; yellow: number }[]>(`/api/dashboard/trend${qs}`) });
  const top = useQuery({ queryKey: ["top", district], queryFn: () => api<TopRow[]>(`/api/dashboard/top${qs}`), refetchInterval: 15000 });

  const s = summary.data;
  const pts = districts.data ?? [];
  const maxTotal = Math.max(1, ...pts.map((d) => d.total));
  const center: [number, number] = pts.length ? [pts.reduce((a, d) => a + d.lat, 0) / pts.length, pts.reduce((a, d) => a + d.lon, 0) / pts.length] : [41.3, 64.5];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Monitoring paneli</h1>
          <p className="text-sm text-slate-500">{user?.region_name}{user?.district_name ? ` · ${user.district_name}` : ""}</p>
        </div>
        {user?.role === "admin" && pts.length > 1 && (
          <select className="input w-auto" value={district ?? ""} onChange={(e) => setDistrict(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Barcha tumanlar</option>
            {pts.map((d) => <option key={d.district_id} value={d.district_id}>{d.name}</option>)}
          </select>
        )}
      </div>

      {summary.error ? <ErrorBox error={summary.error} /> : !s ? <Skeleton className="h-24" /> : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          <Kpi label="Faol homiladorlar" value={s.active_pregnancies} />
          <Kpi label="Qizil" value={s.red} tone="text-zred" />
          <Kpi label="Sariq" value={s.yellow} tone="text-amber-600" />
          <Kpi label="Yashil" value={s.green} tone="text-zgreen" />
          <Kpi label="Ochiq ogohlantirishlar" value={s.open_alerts} />
          <Kpi label="SLA buzilgan" value={s.sla_breaches} tone={s.sla_breaches ? "text-zred" : undefined} />
          <Kpi label="O'rtacha javob vaqti" value={fmtMinutes(s.median_ack_minutes)} />
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-5">
        <div className="card lg:col-span-3">
          <h2 className="mb-2 font-semibold">Tumanlar xaritasi</h2>
          <p className="mb-2 text-xs text-slate-500">Doira o'lchami — faol homiladorlar soni, rangi — qizil zonadagilar ulushi.</p>
          {districts.isLoading ? <Skeleton className="h-[380px]" /> : (
            <div className="h-[380px] overflow-hidden rounded-lg">
              <MapContainer key={pts.length} {...(pts.length > 1 ? { bounds: pts.map((d) => [d.lat, d.lon] as [number, number]), boundsOptions: { padding: [40, 40] } } : { center, zoom: 9 })} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }}>
                <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                {pts.map((d) => (
                  <CircleMarker
                    key={d.district_id}
                    center={[d.lat, d.lon]}
                    radius={8 + 22 * Math.sqrt(d.total / maxTotal)}
                    pathOptions={{ color: shareColor(d.red_share), fillColor: shareColor(d.red_share), fillOpacity: 0.55, weight: 2 }}
                    eventHandlers={{ click: () => user?.role === "admin" && setDistrict(d.district_id) }}
                  >
                    <Tooltip>
                      <b>{d.name}</b><br />
                      Faol: {d.total} · Qizil: {d.red} ({fmtPct(d.red_share)})<br />
                      Sariq: {d.yellow} · Yashil: {d.green}
                    </Tooltip>
                  </CircleMarker>
                ))}
              </MapContainer>
            </div>
          )}
        </div>

        <div className="card lg:col-span-2">
          <h2 className="mb-2 font-semibold">Haftalik dinamika</h2>
          <p className="mb-2 text-xs text-slate-500">Qizil / sariq baholangan homiladorlar soni (12 hafta)</p>
          {trend.isLoading ? <Skeleton className="h-[340px]" /> : (
            <ResponsiveContainer width="100%" height={340}>
              <LineChart data={trend.data} margin={{ left: -20, right: 8, top: 8 }}>
                <CartesianGrid stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="week_start" tickFormatter={(v: string) => v.slice(5)} fontSize={11} />
                <YAxis allowDecimals={false} fontSize={11} />
                <RTooltip />
                <Legend />
                <Line type="monotone" dataKey="red" name="Qizil" stroke="#DC2626" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="yellow" name="Sariq" stroke="#F59E0B" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="card overflow-x-auto">
        <h2 className="mb-2 font-semibold">Eng yuqori xavfli 10 nafar</h2>
        {top.isLoading ? <Skeleton /> : !top.data?.length ? <Empty text="Faol homiladorlar yo'q" /> : (
          <table className="w-full min-w-[640px]">
            <thead><tr className="border-b">
              <th className="th">Kod</th><th className="th">Zona</th><th className="th">Muddat</th><th className="th">Tuman</th><th className="th">Xavf</th><th className="th">Asosiy sabab</th>
            </tr></thead>
            <tbody>
              {top.data.map((r) => (
                <tr key={r.pregnancy_id} className="border-b last:border-0 hover:bg-slate-50">
                  <td className="td font-mono"><Link className="text-brand-700 hover:underline" to={`/patients/${r.patient_id}`}>{r.code}</Link></td>
                  <td className="td"><ZoneBadge zone={r.zone} /></td>
                  <td className="td">{fmtWeeks(r.gestational_weeks)}</td>
                  <td className="td">{r.district_name}</td>
                  <td className="td">{fmtPct(r.risk)}</td>
                  <td className="td text-slate-600">{r.main_reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
