import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ExternalEntryOut, ExternalLookupOut } from "../api/types";
import { DISCLAIMER, PROTEINURIA_LABEL, SYMPTOM_LABEL } from "../i18n/uz";
import { useToast } from "../lib/toast";

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

export default function ExternalVisit() {
  const toast = useToast();
  const qc = useQueryClient();
  const [pinfl, setPinfl] = useState("");
  const [lookingUp, setLookingUp] = useState(false);
  const [lookupErr, setLookupErr] = useState<string | null>(null);
  const [found, setFound] = useState<ExternalLookupOut | null>(null);
  const [sent, setSent] = useState<ExternalEntryOut | null>(null);

  const [nums, setNums] = useState<Record<NumKey, string>>(
    Object.fromEntries(NUM_FIELDS.map((f) => [f.key, ""])) as Record<NumKey, string>,
  );
  const [proteinuria, setProteinuria] = useState<string | null>(null);
  const [symptoms, setSymptoms] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  const hasInput = NUM_FIELDS.some((f) => nums[f.key] !== "") || symptoms.length > 0 || proteinuria !== null;

  async function doLookup(e: React.FormEvent) {
    e.preventDefault();
    setLookingUp(true);
    setLookupErr(null);
    setFound(null);
    setSent(null);
    try {
      const res = await api<ExternalLookupOut>("/api/external/lookup", {
        method: "POST",
        json: { pinfl: pinfl.trim() },
      });
      setFound(res);
    } catch (err) {
      setLookupErr(err instanceof Error ? err.message : "Topilmadi");
    } finally {
      setLookingUp(false);
    }
  }

  async function saveVisit() {
    if (!found) return;
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        pinfl: pinfl.trim(),
        symptoms,
        proteinuria,
        notes: notes || null,
      };
      for (const f of NUM_FIELDS) {
        const v = nums[f.key].replace(",", ".").trim();
        payload[f.key] = v === "" || isNaN(Number(v)) ? null : Number(v);
      }
      const res = await api<ExternalEntryOut>("/api/external/visits", {
        method: "POST",
        json: payload,
      });
      setSent(res);
      toast({
        kind: "success",
        title: res.message_uz,
      });
      qc.invalidateQueries();
    } catch (err) {
      toast({
        kind: "error",
        title: "Saqlab bo'lmadi",
        body: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link to="/patients" className="text-sm text-brand-700 hover:underline">← Bemorlar ro'yxati</Link>
      <div>
        <h1 className="text-xl font-bold">Boshqa poliklinika bemori</h1>
        <p className="mt-1 text-sm text-slate-500">
          Boshqa oilaviy poliklinika hududida yashovchi homilador ayol uchun tahlil yoki ko'rik natijasini kiritish.
          Natija bemorning mahallasiga mas'ul poliklinikaga yuboriladi.
        </p>
      </div>

      <form onSubmit={doLookup} className="card space-y-3">
        <label className="label" htmlFor="ext-pinfl">Bemor JShShIR (aniq 14 ta raqam)</label>
        <div className="flex flex-wrap gap-2">
          <input
            id="ext-pinfl"
            className="input flex-1 font-mono"
            placeholder="Masalan: 41503991234567"
            value={pinfl}
            onChange={(e) => setPinfl(e.target.value)}
            maxLength={14}
          />
          <button type="submit" className="btn-primary" disabled={lookingUp || pinfl.trim().length < 4}>
            {lookingUp ? "Qidirilmoqda…" : "JShShIR bo'yicha qidirish"}
          </button>
        </div>
        <p className="text-xs text-slate-500">
          Har bir qidiruv (shu jumladan topilmagan so'rovlar) audit jurnaliga yoziladi.
        </p>
        {lookupErr && (
          <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-200">{lookupErr}</div>
        )}
      </form>

      {sent && (
        <div className="rounded-card border border-green-300 bg-green-50 p-4 text-sm text-green-900">
          <div className="font-semibold">{sent.message_uz}</div>
          <div className="mt-1 text-xs text-green-800">
            Bemor kodi: <span className="font-mono font-semibold">{sent.patient_code}</span> · Mahalla: {sent.mahalla_name}
          </div>
        </div>
      )}

      {found && !sent && (
        <div className="space-y-4">
          <div className="card space-y-2 border-l-4 border-l-brand-700">
            <div className="eyebrow">Mas'ul muassasa (minimum zarur ma'lumot)</div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-lg font-bold text-slate-900">{found.patient_code}</span>
              <span className="rounded bg-brand-50 px-2 py-0.5 font-mono text-xs font-semibold text-brand-800">
                {found.responsible_polyclinic_code}
              </span>
            </div>
            <div className="text-sm text-slate-700">
              Mas'ul poliklinika: <b>{found.responsible_polyclinic_name}</b> · Mahalla: <b>{found.mahalla_name}</b>
            </div>
            <p className="text-xs text-slate-500">
              Maxfiylik: tashqi poliklinika xodimi bemorning F.I.Sh., anamnezi, xavf zonasi va uy manzilini ko'rmaydi.
            </p>
          </div>

          {!found.has_active_pregnancy ? (
            <div className="card text-sm text-slate-600">Bu bemorda faol homiladorlik topilmadi.</div>
          ) : (
            <div className="card space-y-5">
              <h2 className="font-semibold">Tahlil / ko'rik ko'rsatkichlari</h2>
              <div className="grid grid-cols-2 gap-3">
                {NUM_FIELDS.map((f) => (
                  <div key={f.key}>
                    <label className="label" htmlFor={`ext-${f.key}`}>
                      {f.label} <span className="font-normal text-slate-400">({f.unit})</span>
                    </label>
                    <input
                      id={`ext-${f.key}`}
                      className="input h-11 text-base"
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
                    <button
                      key={k}
                      type="button"
                      onClick={() => setProteinuria(proteinuria === k ? null : k)}
                      className={`h-10 min-w-[60px] rounded-lg border px-3 text-sm font-medium ${
                        proteinuria === k ? "border-brand-700 bg-brand-700 text-white" : "border-slate-300 bg-white"
                      }`}
                    >
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
                      <button
                        key={k}
                        type="button"
                        aria-pressed={on}
                        onClick={() => setSymptoms((s) => (on ? s.filter((x) => x !== k) : [...s, k]))}
                        className={`h-10 rounded-full border px-3.5 text-sm font-medium ${
                          on ? "border-zred bg-red-50 text-red-800" : "border-slate-300 bg-white text-slate-700"
                        }`}
                      >
                        {on ? "✓ " : ""}{label}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="label" htmlFor="ext-notes">Izoh</label>
                <textarea
                  id="ext-notes"
                  className="input min-h-[72px]"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                />
              </div>

              <button
                type="button"
                className="btn-primary h-12 w-full text-base"
                disabled={saving || !hasInput}
                onClick={saveVisit}
              >
                {saving ? "Yuborilmoqda…" : `Mas'ul poliklinikaga yuborish (${found.responsible_polyclinic_name})`}
              </button>
              <p className="text-xs text-slate-400">{DISCLAIMER}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
