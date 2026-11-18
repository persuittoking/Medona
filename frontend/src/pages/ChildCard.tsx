import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { ChildCheck, ChildDetail, Vaccine } from "../api/types";
import { AiSummaryPanel } from "../components/AiSummaryPanel";
import { RiskExplain } from "../components/RiskExplain";
import { Empty, ErrorBox, Skeleton, ZoneBadge } from "../components/ui";
import { ALERT_STATUS_LABEL, CHILD_SIGN_LABEL, DISCLAIMER, FEEDING_LABEL, SEX_LABEL, VACCINE_STATUS_LABEL } from "../i18n/uz";
import { useAuth } from "../lib/auth";
import { fmtAge, fmtDate, fmtDateTime } from "../lib/format";

const STATUS_LABEL: Record<string, string> = { active: "Kuzatuvda", graduated: "1 yoshdan oshgan", deceased: "Vafot etgan", moved: "Ko'chib ketgan" };
const VAX_CLS: Record<Vaccine["status"], string> = {
  given: "bg-green-50 text-green-800 ring-green-200",
  overdue: "bg-red-50 text-red-800 ring-red-200",
  due: "bg-amber-50 text-amber-800 ring-amber-200",
  upcoming: "bg-slate-50 text-slate-600 ring-slate-200",
};

/** Weight-for-age: the child's points over the WHO median and the -2 SD line (sex-specific). */
function GrowthChart({ d }: { d: ChildDetail }) {
  return (
    <div className="card">
      <h3 className="font-semibold">Vazn — yosh grafigi <span className="font-normal text-slate-400">(kg)</span></h3>
      <p className="mb-2 text-xs text-slate-500">
        JSST o'sish standarti ({d.sex === "f" ? "qizlar" : "o'g'il bolalar"}): mediana va −2 SD chizig'i. −2 SD dan past — vazn kam.
      </p>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart margin={{ left: -18, right: 8, top: 6 }}>
          <CartesianGrid stroke="#f1f5f9" vertical={false} />
          <XAxis dataKey="age_months" type="number" domain={[0, 12]} ticks={[0, 2, 4, 6, 8, 10, 12]} fontSize={11}
            tickFormatter={(v: number) => `${v} oy`} allowDuplicatedCategory={false} />
          <YAxis fontSize={11} domain={[2, "auto"]} />
          <Tooltip labelFormatter={(v) => `${v} oy`} formatter={(v: number, name) => [`${v.toFixed(2)} kg`, name]} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line data={d.reference} dataKey="median" name="JSST mediana" stroke="#16A34A" strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          <Line data={d.reference} dataKey="minus2sd" name="−2 SD" stroke="#DC2626" strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          <Line data={d.growth} dataKey="weight_kg" name="Bola vazni" stroke="#0f766e" strokeWidth={2.5} dot={{ r: 3.5 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Vaccines({ list }: { list: Vaccine[] }) {
  const overdue = list.filter((v) => v.status === "overdue").length;
  return (
    <div className="card">
      <h3 className="mb-1 font-semibold">Emlash holati</h3>
      <p className="mb-3 text-xs text-slate-500">
        Milliy emlash kalendari bo'yicha (birinchi yil). Sanalar tug'ilgan kundan hisoblanadi.
        {overdue > 0 && <b className="ml-1 text-zred">{overdue} ta emlash 30 kundan ortiq kechikkan.</b>}
      </p>
      <ul className="grid gap-1.5 sm:grid-cols-2">
        {list.map((v) => (
          <li key={v.code} className="flex items-center justify-between gap-2 text-sm">
            <span><span className="font-mono">{v.code}</span> <span className="text-xs text-slate-400">{fmtDate(v.due_date)}</span></span>
            <span className={`rounded px-1.5 text-xs font-medium ring-1 ${VAX_CLS[v.status]}`}>
              {VACCINE_STATUS_LABEL[v.status]}{v.status === "overdue" ? ` (${v.days_late} kun)` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function CheckRow({ c }: { c: ChildCheck }) {
  const signs = Object.keys(CHILD_SIGN_LABEL).filter((k) => c[k as keyof ChildCheck] === true);
  return (
    <li className="border-l-2 border-brand-100 pb-3 pl-4">
      <div className="text-sm font-semibold">{fmtDate(c.check_date)}{c.age_days != null && ` · ${fmtAge(c.age_days, true)}`}</div>
      <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5 text-sm text-slate-600">
        {c.weight_g != null && <span>Vazn {(c.weight_g / 1000).toFixed(2)} kg</span>}
        {c.length_cm != null && <span>Bo'y {c.length_cm} sm</span>}
        {c.head_circ_cm != null && <span>Bosh aylanasi {c.head_circ_cm} sm</span>}
        {c.resp_rate != null && <span>Nafas {c.resp_rate}/daq</span>}
        {c.temperature_c != null && <span>{c.temperature_c}°C</span>}
        {c.feeding && <span>{FEEDING_LABEL[c.feeding]}</span>}
        {c.diarrhoea_days ? <span>Diareya {c.diarrhoea_days} kun</span> : null}
        {c.cough_days ? <span>Yo'tal {c.cough_days} kun</span> : null}
      </div>
      {signs.length > 0 && <div className="mt-1 text-xs text-red-700">Belgilar: {signs.map((s) => CHILD_SIGN_LABEL[s]).join(", ")}</div>}
      {!!c.vaccines_given?.length && <div className="mt-1 text-xs text-green-700">Emlandi: {c.vaccines_given.join(", ")}</div>}
      {c.notes && <div className="mt-1 text-xs text-slate-500">{c.notes}</div>}
    </li>
  );
}

export default function ChildCard() {
  const { id } = useParams();
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["child", id], queryFn: () => api<ChildDetail>(`/api/children/${id}`) });
  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <div className="space-y-6"><Skeleton className="h-28" /><Skeleton className="h-64" /></div>;
  const d = q.data;
  const ra = d.latest_assessment;
  const canEnter = (user?.role === "nurse" || user?.role === "doctor") && d.status === "active";

  return (
    <div className="space-y-6">
      <Link to="/patients" className="text-sm text-brand-700 hover:underline">← Ro'yxat</Link>

      <div className="card flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-mono text-xl font-bold">{d.code}</h1>
            <ZoneBadge zone={d.zone} size="lg" />
            <span className="rounded bg-sky-50 px-2 py-0.5 text-xs font-semibold text-sky-800 ring-1 ring-sky-200">Bola (0–1 yosh)</span>
            {d.status !== "active" && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{STATUS_LABEL[d.status] ?? d.status}</span>}
          </div>
          <div className="mt-2 grid gap-x-6 gap-y-1 text-sm text-slate-600 sm:grid-cols-2">
            <span>Yoshi: <b>{fmtAge(d.age_days, true)}</b> · tug'ilgan {fmtDate(d.birth_date)}</span>
            <span>Jinsi: <b>{d.sex ? SEX_LABEL[d.sex] : "—"}</b></span>
            <span>Tug'ilish vazni: <b>{d.birth_weight_g} g</b> · {d.gestational_weeks_at_birth} hafta</span>
            <span>Apgar (5 daq): <b>{d.apgar_5 ?? "—"}</b></span>
            <span>Ona: <Link className="font-mono font-semibold text-brand-700 hover:underline" to={`/patients/${d.mother_patient_id}`}>{d.mother_code}</Link></span>
            <span>{d.mahalla} · {d.polyclinic_name}</span>
          </div>
        </div>
        {canEnter && <Link className="btn-primary" to={`/children/${d.newborn_id}/checks/new`}>+ Yangi ko'rik</Link>}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-3 font-semibold">Nega bu zona?</h3>
          {ra ? <RiskExplain risk={ra} /> : <Empty text="Hali baholash yo'q" />}
          <p className="mt-3 text-xs text-slate-400">{DISCLAIMER}</p>
        </div>
        <AiSummaryPanel newbornId={d.newborn_id} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <GrowthChart d={d} />
        <Vaccines list={d.vaccines} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-3 font-semibold">Ko'riklar tarixi</h3>
          {d.checks.length === 0 ? <Empty text="Ko'riklar yo'q" /> : <ul>{[...d.checks].reverse().map((c) => <CheckRow key={c.id} c={c} />)}</ul>}
        </div>
        <div className="card">
          <h3 className="mb-3 font-semibold">Ogohlantirishlar tarixi</h3>
          {d.alerts.length === 0 ? <Empty text="Ogohlantirishlar yo'q" /> : (
            <ul className="space-y-2">
              {d.alerts.map((a) => (
                <li key={a.id} className="rounded-lg border p-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-2"><ZoneBadge zone={a.level} /> {fmtDateTime(a.created_at)}</span>
                    <span className="text-xs text-slate-500">{ALERT_STATUS_LABEL[a.status]}</span>
                  </div>
                  {a.action_taken && <div className="mt-1 text-xs text-slate-600">Ko'rilgan chora: {a.action_taken}</div>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
