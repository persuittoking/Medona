import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { PatientDetail, Risk, VisitCreated } from "../api/types";
import { RiskExplain } from "../components/RiskExplain";
import { ErrorBox, Skeleton, ZoneBadge } from "../components/ui";
import { DISCLAIMER, PROTEINURIA_LABEL, SYMPTOM_LABEL, ZONE_LABEL } from "../i18n/uz";
import { useToast } from "../lib/toast";
import { fmtWeeks } from "../lib/format";

const NUM_FIELDS = [
  { key: "systolic", label: "Sistolik bosim", unit: "mmHg", step: 1 },
  { key: "diastolic", label: "Diastolik bosim", unit: "mmHg", step: 1 },
  { key: "hemoglobin_g_l", label: "Gemoglobin", unit: "g/L", step: 1 },
  { key: "weight_kg", label: "Vazn", unit: "kg", step: 0.1 },
  { key: "fasting_glucose_mmol", label: "Glyukoza (och qoringa)", unit: "mmol/L", step: 0.1 },
  { key: "temperature_c", label: "Harorat", unit: "°C", step: 0.1 },
  { key: "fetal_heart_rate", label: "Homila yurak urishi", unit: "zarba/daq", step: 1 },
  { key: "fundal_height_cm", label: "Bachadon tubi balandligi", unit: "sm", step: 0.5 },
] as const;
type NumKey = (typeof NUM_FIELDS)[number]["key"];

export default function NewVisit() {
  const [sp] = useSearchParams();
  const pregnancyId = Number(sp.get("pregnancy"));
  const patientId = sp.get("patient");
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const patient = useQuery({ queryKey: ["patient", patientId], queryFn: () => api<PatientDetail>(`/api/patients/${patientId}`), enabled: !!patientId });

  const [nums, setNums] = useState<Record<NumKey, string>>(
    Object.fromEntries(NUM_FIELDS.map((f) => [f.key, ""])) as Record<NumKey, string>,
  );
  const [proteinuria, setProteinuria] = useState<string | null>(null);
  const [symptoms, setSymptoms] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState<Risk | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [openedAt] = useState(() => new Date().toISOString()); // plausibility signal only (form open -> save time)
  const reqId = useRef(0);

  const payload = useMemo(() => {
    const body: Record<string, unknown> = { pregnancy_id: pregnancyId, symptoms, proteinuria, notes: notes || null };
    for (const f of NUM_FIELDS) {
      const v = nums[f.key].replace(",", ".").trim();
      body[f.key] = v === "" || isNaN(Number(v)) ? null : Number(v);
    }
    return body;
  }, [nums, proteinuria, symptoms, notes, pregnancyId]);

  const hasInput = NUM_FIELDS.some((f) => nums[f.key] !== "") || symptoms.length > 0 || proteinuria !== null;

  // LIVE RISK PREVIEW: debounced 400 ms, scores without saving.
  useEffect(() => {
    if (!pregnancyId || !hasInput) { setPreview(null); return; }
    const id = ++reqId.current;
    const t = setTimeout(async () => {
      try {
        const r = await api<Risk>("/api/risk/preview", { method: "POST", json: { ...payload, notes: null } });
        if (id === reqId.current) { setPreview(r); setPreviewErr(null); }
      } catch (e) {
        if (id === reqId.current) setPreviewErr(e instanceof Error ? e.message : "Xatolik");
      }
    }, 400);
    return () => clearTimeout(t);
  }, [payload, pregnancyId, hasInput]);

  async function save() {
    setSaving(true);
    try {
      const r = await api<VisitCreated>("/api/visits", { method: "POST", json: { ...payload, opened_at: openedAt } });
      const z = r.assessment.zone;
      toast({
        kind: r.alert ? "red" : z === "green" ? "success" : "info",
        title: `Tashrif saqlandi — zona: ${ZONE_LABEL[z]}`,
        body: r.alert ? "Ogohlantirish yuborildi: OvaBMU mutaxassisiga xabar berildi." : undefined,
      });
      qc.invalidateQueries();
      nav(patientId ? `/patients/${patientId}` : "/patients");
    } catch (e) {
      toast({ kind: "error", title: "Saqlab bo'lmadi", body: e instanceof Error ? e.message : undefined });
    } finally {
      setSaving(false);
    }
  }

  if (!pregnancyId) return <ErrorBox error={new Error("Homiladorlik tanlanmagan")} />;
  const p = patient.data;

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <Link to={patientId ? `/patients/${patientId}` : "/patients"} className="text-sm text-brand-700 hover:underline">← Bemor kartasi</Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">Yangi tashrif</h1>
        {p && <><span className="font-mono">{p.code}</span><span className="text-sm text-slate-500">{fmtWeeks(p.pregnancy.gestational_weeks)}</span><ZoneBadge zone={p.pregnancy.current_zone} /></>}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="card space-y-5">
          <div className="grid grid-cols-2 gap-3">
            {NUM_FIELDS.map((f) => (
              <div key={f.key}>
                <label className="label" htmlFor={f.key}>{f.label} <span className="font-normal text-slate-400">({f.unit})</span></label>
                <input
                  id={f.key}
                  className="input h-12 text-lg"
                  inputMode="decimal"
                  type="number"
                  step={f.step}
                  value={nums[f.key]}
                  onChange={(e) => setNums((s) => ({ ...s, [f.key]: e.target.value }))}
                />
              </div>
            ))}
          </div>

          <div>
            <div className="label">Siydikda oqsil (proteinuriya)</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(PROTEINURIA_LABEL).map(([k, label]) => (
                <button key={k} type="button" onClick={() => setProteinuria(proteinuria === k ? null : k)}
                  className={`h-11 min-w-[64px] rounded-lg border px-3 text-base font-medium ${proteinuria === k ? "border-brand-700 bg-brand-700 text-white" : "border-slate-300 bg-white"}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="label">Shikoyatlar va belgilar</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(SYMPTOM_LABEL).map(([k, label]) => {
                const on = symptoms.includes(k);
                return (
                  <button key={k} type="button" aria-pressed={on}
                    onClick={() => setSymptoms((s) => (on ? s.filter((x) => x !== k) : [...s, k]))}
                    className={`h-11 rounded-full border px-4 text-sm font-medium ${on ? "border-zred bg-red-50 text-red-800" : "border-slate-300 bg-white text-slate-700"}`}>
                    {on ? "✓ " : ""}{label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="label" htmlFor="notes">Izoh</label>
            <textarea id="notes" className="input min-h-[80px]" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>

          <button className="btn-primary h-12 w-full text-base" onClick={save} disabled={saving || !hasInput}>
            {saving ? "Saqlanmoqda…" : "Tashrifni saqlash"}
          </button>
        </div>

        <aside className="lg:sticky lg:top-20 lg:self-start">
          <div className={`card border-2 ${preview ? (preview.zone === "red" ? "border-zred" : preview.zone === "yellow" ? "border-zyellow" : "border-zgreen") : ""}`}>
            <h3 className="mb-1 font-semibold">Jonli xavf bahosi</h3>
            <p className="mb-3 text-xs text-slate-500">Saqlashdan oldin — qiymatlar kiritilishi bilan yangilanadi.</p>
            {previewErr ? <ErrorBox error={new Error(previewErr)} /> : !hasInput ? (
              <p className="text-sm text-slate-500">Qiymatlarni kiriting…</p>
            ) : !preview ? <Skeleton className="h-32" /> : <RiskExplain risk={preview} />}
            <p className="mt-3 text-xs text-slate-400">{DISCLAIMER}</p>
          </div>
        </aside>
      </div>
    </div>
  );
}
