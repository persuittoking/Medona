import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { ChildCheckCreated, ChildDetail, Feeding, Risk } from "../api/types";
import { RiskExplain } from "../components/RiskExplain";
import { ErrorBox, Skeleton, ZoneBadge } from "../components/ui";
import { CHILD_SIGN_LABEL, DISCLAIMER, FEEDING_LABEL, ZONE_LABEL } from "../i18n/uz";
import { fmtAge } from "../lib/format";
import { useToast } from "../lib/toast";

const NUM_FIELDS = [
  { key: "weight_kg", label: "Vazn", unit: "kg", step: 0.01 },
  { key: "length_cm", label: "Bo'y", unit: "sm", step: 0.5 },
  { key: "head_circ_cm", label: "Bosh aylanasi", unit: "sm", step: 0.5 },
  { key: "resp_rate", label: "Nafas soni", unit: "1 daqiqada", step: 1 },
  { key: "temperature_c", label: "Harorat", unit: "°C", step: 0.1 },
  { key: "diarrhoea_days", label: "Diareya davomiyligi", unit: "kun", step: 1 },
  { key: "cough_days", label: "Yo'tal davomiyligi", unit: "kun", step: 1 },
] as const;
type NumKey = (typeof NUM_FIELDS)[number]["key"];
const NEONATAL_ONLY = new Set(["jaundice_first_24h", "jaundice_palms_soles"]);

export default function NewChildCheck() {
  const { id } = useParams();
  const newbornId = Number(id);
  const nav = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const child = useQuery({ queryKey: ["child", id], queryFn: () => api<ChildDetail>(`/api/children/${id}`), enabled: !!id });

  const [nums, setNums] = useState<Record<NumKey, string>>(
    Object.fromEntries(NUM_FIELDS.map((f) => [f.key, ""])) as Record<NumKey, string>,
  );
  const [feeding, setFeeding] = useState<Feeding | null>(null);
  const [signs, setSigns] = useState<string[]>([]);
  const [vaccines, setVaccines] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState<Risk | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const reqId = useRef(0);

  const payload = useMemo(() => {
    const num = (k: NumKey) => {
      const v = nums[k].replace(",", ".").trim();
      return v === "" || isNaN(Number(v)) ? null : Number(v);
    };
    const kg = num("weight_kg");
    const body: Record<string, unknown> = {
      newborn_id: newbornId, feeding, vaccines_given: vaccines, notes: notes || null,
      weight_g: kg == null ? null : Math.round(kg * 1000),
      length_cm: num("length_cm"), head_circ_cm: num("head_circ_cm"), resp_rate: num("resp_rate"),
      temperature_c: num("temperature_c"), diarrhoea_days: num("diarrhoea_days"), cough_days: num("cough_days"),
    };
    for (const s of Object.keys(CHILD_SIGN_LABEL)) body[s] = signs.includes(s);
    return body;
  }, [nums, feeding, signs, vaccines, notes, newbornId]);

  const hasInput = NUM_FIELDS.some((f) => nums[f.key] !== "") || signs.length > 0 || feeding !== null || vaccines.length > 0;

  // LIVE RISK PREVIEW: debounced 400 ms, scores without saving.
  useEffect(() => {
    if (!newbornId || !hasInput) { setPreview(null); return; }
    const rid = ++reqId.current;
    const t = setTimeout(async () => {
      try {
        const r = await api<Risk>("/api/children/risk/preview", { method: "POST", json: { ...payload, notes: null } });
        if (rid === reqId.current) { setPreview(r); setPreviewErr(null); }
      } catch (e) {
        if (rid === reqId.current) setPreviewErr(e instanceof Error ? e.message : "Xatolik");
      }
    }, 400);
    return () => clearTimeout(t);
  }, [payload, newbornId, hasInput]);

  async function save() {
    setSaving(true);
    try {
      const r = await api<ChildCheckCreated>("/api/children/checks", { method: "POST", json: payload });
      const z = r.assessment.zone;
      toast({
        kind: r.alert ? "red" : z === "green" ? "success" : "info",
        title: `Ko'rik saqlandi — zona: ${ZONE_LABEL[z]}`,
        body: r.alert ? "Ogohlantirish yuborildi: OvaBMU mutaxassisiga xabar berildi." : undefined,
      });
      qc.invalidateQueries();
      nav(`/children/${newbornId}`);
    } catch (e) {
      toast({ kind: "error", title: "Saqlab bo'lmadi", body: e instanceof Error ? e.message : undefined });
    } finally {
      setSaving(false);
    }
  }

  if (!newbornId) return <ErrorBox error={new Error("Bola tanlanmagan")} />;
  if (child.error) return <ErrorBox error={child.error} />;
  const c = child.data;
  const neonate = (c?.age_days ?? 0) <= 28;
  const dueVaccines = (c?.vaccines ?? []).filter((v) => v.status === "due" || v.status === "overdue");
  const toggle = (list: string[], set: (v: string[]) => void, k: string) => set(list.includes(k) ? list.filter((x) => x !== k) : [...list, k]);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <Link to={`/children/${newbornId}`} className="text-sm text-brand-700 hover:underline">← Bola kartasi</Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">Yangi ko'rik (bola)</h1>
        {c ? <><span className="font-mono">{c.code}</span><span className="text-sm text-slate-500">{fmtAge(c.age_days, true)}</span><ZoneBadge zone={c.zone} /></> : <Skeleton className="h-6 w-40" />}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="card space-y-5">
          <div className="grid grid-cols-2 gap-3">
            {NUM_FIELDS.map((f) => (
              <div key={f.key}>
                <label className="label" htmlFor={f.key}>{f.label} <span className="font-normal text-slate-400">({f.unit})</span></label>
                <input id={f.key} className="input h-12 text-lg" inputMode="decimal" type="number" step={f.step} value={nums[f.key]}
                  onChange={(e) => setNums((s) => ({ ...s, [f.key]: e.target.value }))} />
              </div>
            ))}
          </div>

          <div>
            <div className="label">Ovqatlanish</div>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(FEEDING_LABEL) as Feeding[]).map((k) => (
                <button key={k} type="button" aria-pressed={feeding === k} onClick={() => setFeeding(feeding === k ? null : k)}
                  className={`h-11 rounded-lg border px-3 text-sm font-medium ${feeding === k ? "border-brand-700 bg-brand-700 text-white" : "border-slate-300 bg-white"}`}>
                  {FEEDING_LABEL[k]}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="label">Xavfli belgilar</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(CHILD_SIGN_LABEL).filter(([k]) => neonate || !NEONATAL_ONLY.has(k)).map(([k, label]) => {
                const on = signs.includes(k);
                return (
                  <button key={k} type="button" aria-pressed={on} onClick={() => toggle(signs, setSigns, k)}
                    className={`h-11 rounded-full border px-4 text-sm font-medium ${on ? "border-zred bg-red-50 text-red-800" : "border-slate-300 bg-white text-slate-700"}`}>
                    {on ? "✓ " : ""}{label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div className="label">Bugun qilingan emlashlar</div>
            {dueVaccines.length === 0 ? <p className="text-sm text-slate-500">Hozir muddati kelgan emlash yo'q.</p> : (
              <div className="flex flex-wrap gap-2">
                {dueVaccines.map((v) => {
                  const on = vaccines.includes(v.code);
                  return (
                    <button key={v.code} type="button" aria-pressed={on} onClick={() => toggle(vaccines, setVaccines, v.code)}
                      className={`h-10 rounded-full border px-3 font-mono text-sm ${on ? "border-green-700 bg-green-50 text-green-800" : v.status === "overdue" ? "border-red-300 bg-white text-red-700" : "border-slate-300 bg-white"}`}>
                      {on ? "✓ " : ""}{v.code}{v.status === "overdue" ? " (kechikkan)" : ""}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div>
            <label className="label" htmlFor="notes">Izoh</label>
            <textarea id="notes" className="input min-h-[80px]" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>

          <button className="btn-primary h-12 w-full text-base" onClick={save} disabled={saving || !hasInput}>
            {saving ? "Saqlanmoqda…" : "Ko'rikni saqlash"}
          </button>
        </div>

        <aside className="lg:sticky lg:top-20 lg:self-start">
          <div className={`card border-2 ${preview ? (preview.zone === "red" ? "border-zred" : preview.zone === "yellow" ? "border-zyellow" : "border-zgreen") : ""}`}>
            <h3 className="mb-1 font-semibold">Jonli xavf bahosi</h3>
            <p className="mb-3 text-xs text-slate-500">Saqlashdan oldin — qiymatlar kiritilishi bilan yangilanadi. Nafas me'yori yoshga bog'liq.</p>
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
