import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ChildRow, PatientRow } from "../api/types";
import { SubjectSwitch } from "../components/SubjectSwitch";
import { Empty, ErrorBox, Skeleton, ZoneBadge } from "../components/ui";
import { SEX_LABEL } from "../i18n/uz";
import { useAuth } from "../lib/auth";
import { fmtAge, fmtDate, fmtPct, fmtWeeks } from "../lib/format";
import { showsChildren, showsPregnancies, useStaffSubjectCounts, useSubject } from "../lib/subject";
import { usePolyclinicMap } from "./PolyclinicMap";

function applyMahallaParam(params: URLSearchParams, mahalla: string) {
  if (mahalla === "all") params.set("all_mahallas", "true");
  else if (mahalla) params.set("mahalla_id", mahalla);
}

function PregnancyList({ zone, q, trimester, overdue, mahalla }: { zone: string; q: string; trimester: string; overdue: boolean; mahalla: string }) {
  const params = new URLSearchParams();
  if (zone) params.set("zone", zone);
  if (trimester) params.set("trimester", trimester);
  if (overdue) params.set("overdue", "true");
  if (q.trim()) params.set("q", q.trim());
  applyMahallaParam(params, mahalla);
  const list = useQuery({ queryKey: ["patients", params.toString()], queryFn: () => api<PatientRow[]>(`/api/patients?${params}`) });
  if (list.error) return <ErrorBox error={list.error} />;
  if (list.isLoading) return <Skeleton className="h-64" />;
  if (!list.data?.length) return <Empty text="Filtr bo'yicha homilador topilmadi" />;
  return (
    <>
      <p className="text-xs text-slate-500">{list.data.length} nafar</p>
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
  );
}

function ChildList({ zone, q, overdue, mahalla }: { zone: string; q: string; overdue: boolean; mahalla: string }) {
  const params = new URLSearchParams();
  if (zone) params.set("zone", zone);
  if (q.trim()) params.set("q", q.trim());
  applyMahallaParam(params, mahalla);
  const list = useQuery({ queryKey: ["children", params.toString()], queryFn: () => api<ChildRow[]>(`/api/children?${params}`) });
  if (list.error) return <ErrorBox error={list.error} />;
  if (list.isLoading) return <Skeleton className="h-64" />;
  const rows = (list.data ?? []).filter((c) => !overdue || c.overdue);
  if (!rows.length) return <Empty text="Filtr bo'yicha bola topilmadi" />;
  return (
    <>
      <p className="text-xs text-slate-500">{rows.length} nafar · 0–12 oylik bolalar</p>
      <div className="space-y-2 md:hidden">
        {rows.map((c) => (
          <Link key={c.newborn_id} to={`/children/${c.newborn_id}`} className="card block active:bg-slate-50">
            <div className="flex items-center justify-between">
              <span className="font-mono font-semibold">{c.code}</span>
              <ZoneBadge zone={c.zone} />
            </div>
            <div className="mt-1 text-sm text-slate-600">Bola · {fmtAge(c.age_days)} · {c.sex ? SEX_LABEL[c.sex] : "—"}</div>
            <div className="mt-1 truncate text-xs text-slate-500">{c.main_reason ?? "Xavf belgilari yo'q"}</div>
            <div className="mt-1 text-xs text-slate-500">
              Oxirgi ko'rik: {fmtDate(c.last_check_date)}{c.overdue && <b className="ml-1 text-zred">kechikkan</b>}
            </div>
          </Link>
        ))}
      </div>
      <div className="card hidden overflow-x-auto p-0 md:block">
        <table className="w-full">
          <thead className="border-b bg-slate-50"><tr>
            <th className="th">Bola kodi</th><th className="th">Yoshi</th><th className="th">Jinsi</th><th className="th">Zona</th>
            <th className="th">Asosiy sabab</th><th className="th">Oxirgi ko'rik</th><th className="th">Ona</th>
          </tr></thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.newborn_id} className="border-b last:border-0 hover:bg-slate-50">
                <td className="td font-mono"><Link className="text-brand-700 hover:underline" to={`/children/${c.newborn_id}`}>{c.code}</Link></td>
                <td className="td">{fmtAge(c.age_days)}</td>
                <td className="td">{c.sex ? SEX_LABEL[c.sex] : "—"}</td>
                <td className="td"><ZoneBadge zone={c.zone} /></td>
                <td className="td max-w-xs truncate text-sm text-slate-600">{c.main_reason ?? "—"}</td>
                <td className="td">{fmtDate(c.last_check_date)}{c.overdue && <span className="ml-1 text-xs font-semibold text-zred">kechikkan</span>}</td>
                <td className="td font-mono text-xs"><Link className="text-brand-700 hover:underline" to={`/patients/${c.mother_patient_id}`}>{c.mother_code}</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function Patients() {
  const { user } = useAuth();
  const [subject, setSubject] = useSubject();
  const counts = useStaffSubjectCounts();
  const map = usePolyclinicMap(subject);
  const [zone, setZone] = useState("");
  const [trimester, setTrimester] = useState("");
  const [overdue, setOverdue] = useState(false);
  const [q, setQ] = useState("");
  const [mahalla, setMahalla] = useState<string>(() => (user?.role === "nurse" && user?.mahalla_id ? String(user.mahalla_id) : "all"));
  const both = subject === "all";
  const canEnterExternal = user?.role === "nurse" || user?.role === "doctor";
  const mahallas = map.data?.mahallas ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1>Bemorlar</h1>
          <p className="mt-1 text-sm text-slate-500">
            {user?.polyclinic_name}{user?.mahalla_name ? ` · ${user.mahalla_name}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canEnterExternal && (
            <Link to="/external-visit" className="btn-ghost btn-sm ring-1 ring-slate-300">
              + Boshqa poliklinika bemori
            </Link>
          )}
          <SubjectSwitch value={subject} onChange={setSubject} counts={counts} />
        </div>
      </div>

      <div className="card-tight grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <input className="input" placeholder="Kod bo'yicha qidirish" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input" value={mahalla} onChange={(e) => setMahalla(e.target.value)} aria-label="Mahalla">
          <option value="all">Barcha mahallalar</option>
          {mahallas.map((m) => (
            <option key={m.id} value={String(m.id)}>{m.name}</option>
          ))}
        </select>
        <select className="input" value={zone} onChange={(e) => setZone(e.target.value)} aria-label="Zona">
          <option value="">Barcha zonalar</option><option value="red">Qizil</option><option value="yellow">Sariq</option><option value="green">Yashil</option>
        </select>
        {showsPregnancies(subject) ? (
          <select className="input" value={trimester} onChange={(e) => setTrimester(e.target.value)} aria-label="Trimestr">
            <option value="">Barcha trimestrlar</option><option value="1">1-trimestr</option><option value="2">2-trimestr</option><option value="3">3-trimestr</option>
          </select>
        ) : <div className="hidden lg:block" />}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-brand-700" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} />
          Tashrifi / ko'rigi kechikkanlar
        </label>
      </div>

      {showsPregnancies(subject) && (
        <section className="space-y-2">
          {both && <h2>Homiladorlar</h2>}
          <PregnancyList zone={zone} q={q} trimester={trimester} overdue={overdue} mahalla={mahalla} />
        </section>
      )}
      {showsChildren(subject) && (
        <section className="space-y-2">
          {both && <h2 className="pt-2">Bolalar (0–1 yosh)</h2>}
          <ChildList zone={zone} q={q} overdue={overdue} mahalla={mahalla} />
        </section>
      )}
    </div>
  );
}
