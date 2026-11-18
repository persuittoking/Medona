import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { PatientDetail, Visit, VisitPlan, Zone } from "../api/types";
import { AiSummaryPanel } from "../components/AiSummaryPanel";
import { LoopButtons, LoopInfo, UNRESOLVED } from "../components/AlertLoop";
import { MahallaMap } from "../components/MahallaMap";
import { usePolyclinicMap } from "./PolyclinicMap";
import { RiskExplain } from "../components/RiskExplain";
import { Empty, ErrorBox, Skeleton, ZoneBadge } from "../components/ui";
import { ALERT_STATUS_LABEL, DISCLAIMER, PROTEINURIA_LABEL, SEX_LABEL, SYMPTOM_LABEL, ZONE_COLOR } from "../i18n/uz";
import { useAuth } from "../lib/auth";
import { fmtAge, fmtDate, fmtDateTime, fmtPct, fmtWeeks } from "../lib/format";
import { useToast } from "../lib/toast";

function Gauge({ p, zone }: { p: number | null; zone: Zone }) {
  const v = p ?? 0;
  const color = ZONE_COLOR[zone];
  return (
    <div className="flex items-center gap-2" title="ML modeli bo'yicha xavf ehtimoli">
      <div className="h-2.5 w-28 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full" style={{ width: `${Math.max(3, v * 100)}%`, background: color }} />
      </div>
      <span className="text-sm font-semibold">{fmtPct(p)}</span>
    </div>
  );
}

function MiniChart({ data, lines, refs, title, unit }: {
  data: Record<string, unknown>[]; title: string; unit: string;
  lines: { key: string; name: string; color: string }[]; refs: { y: number; label: string; color: string }[];
}) {
  return (
    <div className="card">
      <h4 className="mb-1 text-sm font-semibold">{title} <span className="font-normal text-slate-400">({unit})</span></h4>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ left: -22, right: 8, top: 6 }}>
          <CartesianGrid stroke="#f1f5f9" vertical={false} />
          <XAxis dataKey="w" fontSize={11} tickFormatter={(v: number) => `${Math.round(v)}h`} />
          <YAxis fontSize={11} domain={["auto", "auto"]} />
          <Tooltip labelFormatter={(v) => `${v} hafta`} />
          {lines.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {refs.map((r) => <ReferenceLine key={r.label} y={r.y} stroke={r.color} strokeDasharray="4 3" label={{ value: r.label, fontSize: 10, fill: r.color, position: "insideTopRight" }} />)}
          {lines.map((l) => <Line key={l.key} dataKey={l.key} name={l.name} stroke={l.color} strokeWidth={2} connectNulls dot={{ r: 3 }} />)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function VisitRow({ v }: { v: Visit }) {
  const extBadge = v.external_badge_uz ?? (v.performed_at_polyclinic_name ? `Boshqa poliklinikada o'tkazilgan: ${v.performed_at_polyclinic_name}` : null);
  return (
    <li className="border-l-2 border-brand-100 pb-3 pl-4">
      <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
        <span>{fmtDate(v.visit_date)} · {fmtWeeks(v.gestational_weeks)}</span>
        {extBadge && (
          <span className="rounded bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-800 ring-1 ring-indigo-200">
            {extBadge}
          </span>
        )}
      </div>
      <div className="mt-0.5 flex flex-wrap gap-x-4 gap-y-0.5 text-sm text-slate-600">
        {v.systolic != null && <span>AB {v.systolic}/{v.diastolic}</span>}
        {v.hemoglobin_g_l != null && <span>Hb {v.hemoglobin_g_l} g/L</span>}
        {v.proteinuria && <span>Oqsil: {PROTEINURIA_LABEL[v.proteinuria]}</span>}
        {v.weight_kg != null && <span>{v.weight_kg} kg</span>}
        {v.fasting_glucose_mmol != null && <span>Glyukoza {v.fasting_glucose_mmol}</span>}
        {v.fetal_heart_rate != null && <span>HYU {v.fetal_heart_rate}</span>}
        {v.fundal_height_cm != null && <span>BTB {v.fundal_height_cm} sm</span>}
      </div>
      {v.symptoms.length > 0 && <div className="mt-1 text-xs text-amber-700">Shikoyatlar: {v.symptoms.map((s) => SYMPTOM_LABEL[s] ?? s).join(", ")}</div>}
      {v.notes && <div className="mt-1 text-xs text-slate-500">{v.notes}</div>}
    </li>
  );
}

export default function PatientCard() {
  const { id } = useParams();
  const { user } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["patient", id], queryFn: () => api<PatientDetail>(`/api/patients/${id}`) });
  const map = usePolyclinicMap();
  const [pii, setPii] = useState<{ full_name: string; pinfl: string; phone: string } | null>(null);
  const [confirming, setConfirming] = useState(false);

  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <div className="space-y-6"><Skeleton className="h-28" /><Skeleton className="h-64" /></div>;
  const d = q.data;
  const p = d.pregnancy;
  const vp = d.visit_plan;
  const ra = d.latest_assessment;
  const chart = d.visits.map((v) => ({ w: v.gestational_weeks, hb: v.hemoglobin_g_l, sys: v.systolic, dia: v.diastolic, wt: v.weight_kg }));
  const canEnter = (user?.role === "nurse" || user?.role === "doctor") && p.status === "active";

  async function confirmLightVisit() {
    setConfirming(true);
    try {
      const updated = await api<VisitPlan>(`/api/patients/${d.patient_id}/visit-intensity/confirm`, { method: "POST" });
      toast({
        kind: "success",
        title: "Yengil ko'rik rejimi tasdiqlandi",
        body: `${updated.confirmed_light_visits} ta rejadagi ko'rik Yengil (hamshira ishtirokida) sifatida belgilandi.`,
      });
      qc.invalidateQueries({ queryKey: ["patient", id] });
      qc.invalidateQueries({ queryKey: ["summary"] });
    } catch (e) {
      toast({ kind: "error", title: "Tasdiqlab bo'lmadi", body: e instanceof Error ? e.message : undefined });
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div className="space-y-6">
      <Link to="/patients" className="text-sm text-brand-700 hover:underline">← Bemorlar ro'yxati</Link>

      <div className="card flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-mono text-xl font-bold">{d.code}</h1>
            <ZoneBadge zone={p.current_zone} size="lg" />
            {p.status !== "active" && <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{p.status === "delivered" ? "Tug'ruq bo'lgan" : p.status}</span>}
            {p.status === "delivered" && d.newborns.filter((n) => n.pregnancy_id === p.id).map((n) => (
              <Link key={n.id} to={`/children/${n.id}`} className="rounded bg-sky-50 px-2 py-0.5 text-xs font-semibold text-sky-800 ring-1 ring-sky-200 hover:underline">
                Bola: {n.code} →
              </Link>
            ))}
          </div>
          <div className="mt-2 grid gap-x-6 gap-y-1 text-sm text-slate-600 sm:grid-cols-2">
            <span>Ism: <b>{pii ? pii.full_name : d.name_masked}</b></span>
            <span>JShShIR: <b className="font-mono">{pii ? pii.pinfl : d.pinfl_masked}</b></span>
            <span>Telefon: <b className="font-mono">{pii ? pii.phone : d.phone_masked}</b></span>
            <span>Yosh: <b>{d.age}</b></span>
            <span>Muddat: <b>{fmtWeeks(p.gestational_weeks)}</b> · TKS: {fmtDate(p.edd)}</span>
            <span>G{p.gravidity} P{p.parity} · TMI {p.bmi_booking ?? "—"}</span>
            <span>{d.mahalla} · {d.polyclinic_name}</span>
            <span>Perinatal markazgacha: {Math.round(d.distance_to_perinatal_km)} km</span>
          </div>
          {p.history.length > 0 && <div className="mt-2 text-xs text-slate-500">Anamnez: {p.history.join(", ")}</div>}
        </div>
        <div className="flex flex-col items-end gap-2">
          <Gauge p={p.current_risk_score} zone={p.current_zone} />
          {!pii && (
            <button className="btn-ghost px-3 py-1 text-xs" onClick={async () => setPii(await api(`/api/patients/${d.patient_id}/reveal`, { method: "POST" }))}>
              Ko'rsatish (auditga yoziladi)
            </button>
          )}
          {canEnter && <Link className="btn-primary" to={`/visits/new?pregnancy=${p.id}&patient=${d.patient_id}`}>+ Yangi tashrif</Link>}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-3 font-semibold">Nega bu zona?</h3>
          {ra ? <RiskExplain risk={ra} /> : <Empty text="Hali baholash yo'q" />}
          <p className="mt-3 text-xs text-slate-400">{DISCLAIMER}</p>
        </div>
        <AiSummaryPanel pregnancyId={p.id} />
      </div>

      {vp && (
        <div className="card space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-semibold">Tashriflar intensivligi rejasi ({vp.standard_visits} ta majburiy ko'rik)</h3>
              <p className="text-xs text-slate-500">
                Milliy standart bo'yicha {vp.standard_visits} ta majburiy antenatal ko'rik soni hech qachon qisqartirilmaydi.
              </p>
            </div>
            <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
              Jami: {vp.total_scheduled_visits} ta ko'rik
            </span>
          </div>

          {vp.eligible && vp.recommendation_uz ? (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-3 text-sm text-emerald-950">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-semibold text-emerald-900">{vp.recommendation_uz}</div>
                  <p className="mt-0.5 text-xs text-emerald-800">{vp.reason_uz}</p>
                </div>
                {vp.confirmed ? (
                  <span className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white">
                    ✓ Shifokor tasdiqlagan ({vp.confirmed_light_visits} ta Yengil)
                  </span>
                ) : user?.role === "doctor" && p.status === "active" ? (
                  <button
                    type="button"
                    className="btn-primary btn-sm"
                    disabled={confirming}
                    onClick={confirmLightVisit}
                  >
                    {confirming ? "Tasdiqlanmoqda…" : "Shifokor sifatida tasdiqlash (Yengil ko'rik)"}
                  </button>
                ) : (
                  <span className="rounded bg-white px-2.5 py-1 text-xs font-medium text-emerald-900 ring-1 ring-emerald-300">
                    Faqat oilaviy shifokor tasdiqlashi mumkin
                  </span>
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-700 ring-1 ring-slate-200">
              <b>Barcha qolgan ko'riklar: To'liq (shifokor ko'rigi).</b> {vp.reason_uz}
            </div>
          )}

          <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-6 lg:grid-cols-12">
            {vp.schedule.map((sl) => {
              const isLight = sl.intensity === "Yengil";
              const isRecLight = !vp.confirmed && sl.recommended_intensity === "Yengil";
              return (
                <div
                  key={sl.visit_number}
                  className={`rounded-lg border p-2 text-center text-xs ${
                    sl.status === "completed"
                      ? "border-slate-200 bg-slate-50 text-slate-500"
                      : isLight
                      ? "border-emerald-300 bg-emerald-50 text-emerald-900"
                      : isRecLight
                      ? "border-dashed border-emerald-300 bg-white text-emerald-800"
                      : "border-slate-200 bg-white text-slate-800"
                  }`}
                >
                  <div className="font-mono text-[11px] text-slate-400">#{sl.visit_number} · {sl.target_week}h</div>
                  <div className="mt-0.5 font-semibold">{sl.intensity}</div>
                  {isRecLight && <div className="text-[10px] text-emerald-700">(tavsiya: Yengil)</div>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {d.visits.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-3">
          <MiniChart title="Gemoglobin" unit="g/L" data={chart} lines={[{ key: "hb", name: "Hb", color: "#0f766e" }]}
            refs={[{ y: 100, label: "100", color: "#F59E0B" }, { y: 70, label: "70", color: "#DC2626" }]} />
          <MiniChart title="Arterial bosim" unit="mmHg" data={chart}
            lines={[{ key: "sys", name: "Sistolik", color: "#0f766e" }, { key: "dia", name: "Diastolik", color: "#64748b" }]}
            refs={[{ y: 140, label: "140", color: "#F59E0B" }, { y: 90, label: "90", color: "#F59E0B" }, { y: 160, label: "160", color: "#DC2626" }, { y: 110, label: "110", color: "#DC2626" }]} />
          <MiniChart title="Vazn" unit="kg" data={chart} lines={[{ key: "wt", name: "Vazn", color: "#0f766e" }]} refs={[]} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-3 font-semibold">Tashriflar tarixi</h3>
          {d.visits.length === 0 ? <Empty text="Tashriflar yo'q" /> : <ul>{[...d.visits].reverse().map((v) => <VisitRow key={v.id} v={v} />)}</ul>}
        </div>
        <div className="space-y-6">
          {map.data && (
            <div className="card">
              <h3 className="mb-1 font-semibold">Uy joylashuvi</h3>
              <p className="mb-3 text-xs text-slate-500">Shaxsiy ma'lumot — faqat {d.polyclinic_name} xodimlari ko'radi.</p>
              <MahallaMap height={260} padding={0.08} legend={false}
                areas={map.data.mahallas.filter((m) => m.id === d.mahalla_id).map((m) => ({ key: String(m.id), boundary: m.boundary }))}
                dots={[{ key: d.patient_id, lat: d.home.lat, lon: d.home.lon, zone: p.current_zone, label: d.code }]} />
            </div>
          )}
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
                  <LoopInfo a={a} />
                  {UNRESOLVED.includes(a.status) && <div className="mt-2"><LoopButtons a={a} /></div>}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {d.newborns.length > 0 && (
            <div className="card">
              <h3 className="mb-3 font-semibold">Bolalari</h3>
              <ul className="space-y-3">
                {d.newborns.map((n) => (
                  <li key={n.id} className="space-y-1 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <ZoneBadge zone={n.zone} />
                      <Link to={`/children/${n.id}`} className="font-mono font-semibold text-brand-700 hover:underline">{n.code ?? `#${n.id}`}</Link>
                      <span className="text-slate-600">{n.sex ? SEX_LABEL[n.sex] : ""}{n.age_days != null && ` · ${fmtAge(n.age_days)}`}</span>
                      {n.status !== "active" && <span className="rounded bg-slate-100 px-1.5 text-xs">{n.status === "graduated" ? "1 yoshdan oshgan" : n.status}</span>}
                    </div>
                    <div className="text-slate-600">Tug'ilgan: {fmtDate(n.birth_date)} · {n.birth_weight_g} g · {n.gestational_weeks_at_birth} hafta · Apgar(5) {n.apgar_5 ?? "—"}</div>
                    {n.hits.length > 0 && (
                      <ul className="mt-1 list-disc pl-5 text-slate-700">
                        {n.hits.slice(0, 3).map((h) => <li key={h.code}><span className="font-mono text-xs text-slate-400">{h.code}</span> {h.uz_text}</li>)}
                      </ul>
                    )}
                    <Link to={`/children/${n.id}`} className="text-xs font-medium text-brand-700 hover:underline">Bola kartasi →</Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
