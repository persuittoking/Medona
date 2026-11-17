import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { PatientRow } from "../api/types";
import { Empty, ErrorBox, Skeleton, ZoneBadge } from "../components/ui";
import { useAuth } from "../lib/auth";
import { fmtDate, fmtPct, fmtWeeks } from "../lib/format";

export default function Patients() {
  const { user } = useAuth();
  const [zone, setZone] = useState("");
  const [trimester, setTrimester] = useState("");
  const [overdue, setOverdue] = useState(false);
  const [q, setQ] = useState("");
  const params = new URLSearchParams();
  if (zone) params.set("zone", zone);
  if (trimester) params.set("trimester", trimester);
  if (overdue) params.set("overdue", "true");
  if (q.trim()) params.set("q", q.trim());
  const list = useQuery({ queryKey: ["patients", params.toString()], queryFn: () => api<PatientRow[]>(`/api/patients?${params}`) });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1>Bemorlar</h1>
          <p className="mt-1 text-sm text-slate-500">{user?.polyclinic_name} · faol homiladorlar</p>
        </div>
        <span className="text-sm text-slate-500">{list.data ? `${list.data.length} nafar` : ""}</span>
      </div>

      <div className="card-tight grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <input className="input" placeholder="Bemor kodi bo'yicha qidirish" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input" value={zone} onChange={(e) => setZone(e.target.value)} aria-label="Zona">
          <option value="">Barcha zonalar</option><option value="red">Qizil</option><option value="yellow">Sariq</option><option value="green">Yashil</option>
        </select>
        <select className="input" value={trimester} onChange={(e) => setTrimester(e.target.value)} aria-label="Trimestr">
          <option value="">Barcha trimestrlar</option><option value="1">1-trimestr</option><option value="2">2-trimestr</option><option value="3">3-trimestr</option>
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-brand-700" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} />
          Tashrifi kechikkanlar
        </label>
      </div>

      {list.error ? <ErrorBox error={list.error} /> : list.isLoading ? <Skeleton className="h-64" /> : !list.data?.length ? <Empty text="Filtr bo'yicha bemor topilmadi" /> : (
        <>
          {/* mobile cards */}
          <div className="space-y-2 md:hidden">
            {list.data.map((p) => (
              <Link key={p.pregnancy_id} to={`/patients/${p.patient_id}`} className="card block active:bg-slate-50">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-semibold">{p.code}</span>
                  <ZoneBadge zone={p.zone} />
                </div>
                <div className="mt-1 text-sm text-slate-600">
                  {p.name_masked} · {p.age} yosh · {fmtWeeks(p.gestational_weeks)}
                </div>
                <div className="mt-1 flex justify-between text-xs text-slate-500">
                  <span>Oxirgi tashrif: {fmtDate(p.last_visit_date)}{p.overdue && <b className="ml-1 text-zred">kechikkan</b>}</span>
                  <span>Xavf {fmtPct(p.risk)}</span>
                </div>
              </Link>
            ))}
          </div>
          {/* desktop table */}
          <div className="card hidden overflow-x-auto p-0 md:block">
            <table className="w-full">
              <thead className="border-b bg-slate-50"><tr>
                <th className="th">Kod</th><th className="th">Ism</th><th className="th">Yosh</th><th className="th">Muddat</th><th className="th">Zona</th>
                <th className="th">Xavf</th><th className="th">Oxirgi tashrif</th><th className="th">Mahalla</th>
              </tr></thead>
              <tbody>
                {list.data.map((p) => (
                  <tr key={p.pregnancy_id} className="border-b last:border-0 hover:bg-slate-50">
                    <td className="td font-mono"><Link className="text-brand-700 hover:underline" to={`/patients/${p.patient_id}`}>{p.code}</Link></td>
                    <td className="td">{p.name_masked}</td>
                    <td className="td">{p.age}</td>
                    <td className="td">{fmtWeeks(p.gestational_weeks)}</td>
                    <td className="td"><ZoneBadge zone={p.zone} /></td>
                    <td className="td">{fmtPct(p.risk)}</td>
                    <td className="td">{fmtDate(p.last_visit_date)}{p.overdue && <span className="ml-1 text-xs font-semibold text-zred">kechikkan</span>}</td>
                    <td className="td text-slate-600">{p.mahalla}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
