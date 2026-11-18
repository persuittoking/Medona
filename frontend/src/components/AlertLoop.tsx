import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ActionCatalog, Alert, TransferTarget } from "../api/types";
import { useAuth } from "../lib/auth";
import { fmtDateTime } from "../lib/format";
import { useToast } from "../lib/toast";

/** Proof of care (closed loop) UI shared by the Alerts page and the patient / child cards. */

export const UNRESOLVED = ["open", "escalated", "unreachable", "acknowledged", "pending_confirmation"];
const RESOLVE_ROLES = ["specialist", "doctor", "department_head"];
const CONFIRM_ROLES = ["doctor", "department_head"];
const CONTACT_ROLES = ["nurse", "doctor"];
const NEED_MEASUREMENT = "Yopish uchun yangi o'lchov kerak";

export function useActionCatalog() {
  return useQuery({ queryKey: ["action-catalog"], queryFn: () => api<ActionCatalog>("/api/alerts/action-catalog"), staleTime: Infinity });
}

function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[1500] flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true"
      onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div className="card max-h-[90vh] w-full max-w-lg overflow-y-auto">
        <h2 className="font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

function useSubmit(onDone: () => void) {
  const qc = useQueryClient();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  async function run(path: string, json: unknown, title: string) {
    setBusy(true);
    try {
      await api(path, { method: "POST", json });
      toast({ kind: "success", title });
      qc.invalidateQueries();
      onDone();
    } catch (e) {
      toast({ kind: "error", title: "Xatolik", body: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  }
  return { busy, run };
}

/** Status box: what measurement closes the alert, contact attempts, unreachable / refusal, closure. */
export function LoopInfo({ a }: { a: Alert }) {
  const open = UNRESOLVED.includes(a.status);
  return (
    <div className="mt-2 space-y-1.5 text-xs">
      {open && (
        <div className={`rounded-md px-2 py-1 ring-1 ${a.has_measurement ? "bg-emerald-50 text-emerald-900 ring-emerald-200" : "bg-slate-50 text-slate-700 ring-slate-200"}`}>
          {a.has_measurement
            ? <>✓ Yangi o'lchov kiritilgan{a.evidence_at && ` (${fmtDateTime(a.evidence_at)})`} — endi yopish mumkin</>
            : <>Yopish uchun yangi o'lchov kerak: <b>{a.required_measurements.join(", ")}</b>
                {a.measurement_due_at && <> · muddat: {fmtDateTime(a.measurement_due_at)}</>}</>}
        </div>
      )}
      {a.unreachable_reason && open && (
        <div className="rounded-md bg-red-50 px-2 py-1 text-red-900 ring-1 ring-red-200">
          ⚠️ Aloqa o'rnatilmagan: {a.unreachable_reason} — ogohlantirish faol qoladi
          {a.retry_due_at && <> · keyingi urinish: <b className={a.retry_overdue ? "text-zred" : ""}>{a.retry_overdue ? "hozir" : fmtDateTime(a.retry_due_at)}</b></>}
        </div>
      )}
      {a.reopened_count > 0 && (
        <div className="rounded-md bg-orange-50 px-2 py-1 text-orange-900 ring-1 ring-orange-200">
          ↺ Qayta ochilgan ({a.reopened_count} marta): yopilgandan keyingi birinchi baholash yana qizil zona
        </div>
      )}
      {a.status === "pending_confirmation" && (
        <div className="rounded-md bg-amber-50 px-2 py-1 text-amber-900 ring-1 ring-amber-200">
          Yopish taklif qilindi: {a.resolved_by} · {a.resolution_outcome_uz} — boshqa xodim (shifokor yoki bo'lim mudiri) tasdiqlashi kerak
        </div>
      )}
      {a.status === "resolved" && a.resolution_outcome_uz && (
        <div className="text-slate-600">
          Natija: <b>{a.resolution_outcome_uz}</b> · {a.resolution_actions.map((x) => x.code).join(", ")}
          {a.confirmed_by && <> · tasdiqladi: {a.confirmed_by}</>}
        </div>
      )}
      {a.contact_attempts.length > 0 && (
        <details>
          <summary className="cursor-pointer text-slate-600">Aloqa urinishlari: {a.contact_attempts.length} ta (muvaffaqiyatsiz: {a.failed_attempts})</summary>
          <ul className="mt-1 space-y-0.5 pl-3 text-slate-600">
            {a.contact_attempts.map((c) => (
              <li key={c.id}>
                <span className="font-mono text-slate-400">{fmtDateTime(c.at)}</span> · {c.channel_uz}: <b>{c.result_uz}</b>
                {c.user && <> · {c.user}</>}{c.note && <> — {c.note}</>}
                {c.counselling_uz.length > 0 && <div className="text-slate-500">Maslahat: {c.counselling_uz.join("; ")}</div>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export function ResolveDialog({ a, onClose }: { a: Alert; onClose: () => void }) {
  const cat = useActionCatalog();
  const [codes, setCodes] = useState<string[]>([]);
  const [outcome, setOutcome] = useState("");
  const [note, setNote] = useState("");
  const { busy, run } = useSubmit(onClose);
  const actions = (cat.data?.actions ?? []).filter((x) => (a.subject === "child") === (Number(x.code.slice(1)) >= 21));
  const toggle = (c: string) => setCodes((cs) => (cs.includes(c) ? cs.filter((x) => x !== c) : [...cs, c]));
  return (
    <Modal title={`Ogohlantirishni yopish — ${a.patient_code}`} onClose={onClose}>
      {!a.has_measurement ? (
        <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-900 ring-1 ring-red-200">
          {NEED_MEASUREMENT}: {a.required_measurements.join(", ")}. Avval tashrif yoki ko'rikni kiriting.
        </p>
      ) : (
        <>
          <div className="label mt-3">Ko'rilgan choralar (katalogdan, kamida bittasi)</div>
          <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg p-2 ring-1 ring-slate-200">
            {actions.map((x) => (
              <label key={x.code} className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={codes.includes(x.code)} onChange={() => toggle(x.code)} />
                <span><span className="font-mono text-xs text-slate-400">{x.code}</span> {x.text_uz}</span>
              </label>
            ))}
          </div>
          <div className="label mt-3">Natija</div>
          <div className="flex flex-wrap gap-2">
            {(cat.data?.outcomes ?? []).map((o) => (
              <button key={o.code} type="button" onClick={() => setOutcome(o.code)} aria-pressed={outcome === o.code}
                className={`btn-sm btn ${outcome === o.code ? "bg-brand-700 text-white" : "bg-white ring-1 ring-slate-300"}`}>{o.text_uz}</button>
            ))}
          </div>
          <label className="label mt-3" htmlFor="rnote">Izoh (ixtiyoriy, shaxsiy ma'lumotsiz)</label>
          <input id="rnote" className="input" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
          {a.level === "red" && (
            <p className="mt-2 text-xs text-amber-800">Qizil ogohlantirish: yopishni boshqa xodim (shifokor yoki bo'lim mudiri) tasdiqlaydi.</p>
          )}
        </>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-ghost" onClick={onClose}>Bekor qilish</button>
        <button className="btn-primary" disabled={busy || !a.has_measurement || !codes.length || !outcome}
          onClick={() => run(`/api/alerts/${a.id}/resolve`, { action_codes: codes, outcome, note: note || null },
            a.level === "red" ? "Yopish taklif qilindi — tasdiq kutilmoqda" : "Ogohlantirish yopildi")}>
          Yopish
        </button>
      </div>
    </Modal>
  );
}

export function ContactAttemptDialog({ a, onClose }: { a: Alert; onClose: () => void }) {
  const cat = useActionCatalog();
  const { user } = useAuth();
  const [channel, setChannel] = useState("phone");
  const [result, setResult] = useState("");
  const [note, setNote] = useState("");
  const [done, setDone] = useState<string[]>([]);
  const [target, setTarget] = useState<number | "">("");
  const { busy, run } = useSubmit(onClose);
  const transfer = useSubmit(onClose);
  const targets = useQuery({
    queryKey: ["transfer-targets"], queryFn: () => api<TransferTarget[]>("/api/transfer/mahallas"),
    enabled: result === "elsewhere", staleTime: 300_000,
  });
  const refused = result === "refused";
  const minNote = cat.data?.refusal_note_min ?? 10;
  const requiredOk = (cat.data?.counselling ?? []).filter((c) => c.required).every((c) => done.includes(c.code));
  const valid = !!result && (!refused || (requiredOk && note.trim().length >= minNote));
  return (
    <Modal title={`Aloqa urinishi qo'shish — ${a.patient_code}`} onClose={onClose}>
      <label className="label mt-3" htmlFor="ch">Aloqa usuli</label>
      <select id="ch" className="input" value={channel} onChange={(e) => setChannel(e.target.value)}>
        {(cat.data?.channels ?? []).map((c) => <option key={c.code} value={c.code}>{c.text_uz}</option>)}
      </select>
      <div className="label mt-3">Natija</div>
      <div className="flex flex-wrap gap-2">
        {(cat.data?.results ?? []).map((r) => (
          <button key={r.code} type="button" onClick={() => setResult(r.code)} aria-pressed={result === r.code}
            className={`btn-sm btn ${result === r.code ? "bg-brand-700 text-white" : "bg-white ring-1 ring-slate-300"}`}>{r.text_uz}</button>
        ))}
      </div>
      {refused && (
        <div className="mt-3 rounded-lg bg-amber-50 p-3 text-sm ring-1 ring-amber-200">
          <div className="font-semibold text-amber-900">Maslahat ro'yxati (oila ruxsat bermadi)</div>
          {(cat.data?.counselling ?? []).map((c) => (
            <label key={c.code} className="mt-1 flex items-start gap-2">
              <input type="checkbox" className="mt-1" checked={done.includes(c.code)}
                onChange={() => setDone((d) => (d.includes(c.code) ? d.filter((x) => x !== c.code) : [...d, c.code]))} />
              <span>{c.text_uz}{c.required && <b className="text-zred"> *</b>}</span>
            </label>
          ))}
          <p className="mt-2 text-xs text-amber-900">Xabardor rad etish qaydi majburiy. Ogohlantirish yopilmaydi: o'lchov kiritilguncha qayta eslatiladi.</p>
        </div>
      )}
      {result === "elsewhere" && (
        <div className="mt-3 space-y-2 rounded-lg bg-indigo-50 p-3 text-sm text-indigo-950 ring-1 ring-indigo-200">
          <p>Bemor boshqa joyda bo'lsa, natijani u yerdagi poliklinikadan so'rang yoki kiriting (mas'uliyat mahallaga qarab belgilanadi).</p>
          {(user?.role === "nurse" || user?.role === "doctor") && (
            <Link to="/external-visit" className="btn-sm btn bg-white ring-1 ring-indigo-300" onClick={onClose}>📥 Tashqi natijani kiritish</Link>
          )}
          <div className="pt-1">
            <label className="label" htmlFor="tr">Butunlay ko'chib ketgan bo'lsa: yangi mahalla</label>
            <div className="flex gap-2">
              <select id="tr" className="input" value={target} onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : "")}>
                <option value="">— tanlang —</option>
                {(targets.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.name} · {m.polyclinic_code}</option>)}
              </select>
              <button type="button" className="btn-sm btn bg-white ring-1 ring-indigo-300" disabled={target === "" || transfer.busy || a.patient_id == null}
                onClick={() => transfer.run(`/api/patients/${a.patient_id}/transfer`, { mahalla_id: target }, "Bemor yangi mahalla poliklinikasiga o'tkazildi")}>
                O'tkazish
              </button>
            </div>
          </div>
        </div>
      )}
      <label className="label mt-3" htmlFor="cnote">Izoh{refused ? " (majburiy: xabardor rad etish)" : " (ixtiyoriy)"}</label>
      <textarea id="cnote" className="input min-h-[70px]" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)}
        placeholder={refused ? "Masalan: xavfli belgilar tushuntirildi, oila hozircha rad etdi" : ""} />
      <p className="mt-1 text-xs text-slate-500">Ism, telefon raqami yoki manzilni yozmang — faqat bemor kodi ishlatiladi.</p>
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-ghost" onClick={onClose}>Bekor qilish</button>
        <button className="btn-primary" disabled={busy || !valid}
          onClick={() => run(`/api/alerts/${a.id}/contact-attempts`, { channel, result, note: note || null, counselling: done }, "Aloqa urinishi saqlandi")}>
          Saqlash
        </button>
      </div>
    </Modal>
  );
}

export function ConfirmDialog({ a, onClose }: { a: Alert; onClose: () => void }) {
  const [note, setNote] = useState("");
  const { busy, run } = useSubmit(onClose);
  return (
    <Modal title={`Yopishni tasdiqlash — ${a.patient_code}`} onClose={onClose}>
      <p className="mt-3 text-sm text-slate-700">
        {a.resolved_by} taklifi: <b>{a.resolution_outcome_uz}</b>
      </p>
      <ul className="mt-1 list-disc pl-5 text-sm text-slate-700">{a.resolution_actions.map((x) => <li key={x.code}>{x.text_uz}</li>)}</ul>
      <label className="label mt-3" htmlFor="cfnote">Izoh (ixtiyoriy)</label>
      <input id="cfnote" className="input" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn-ghost" onClick={onClose}>Bekor qilish</button>
        <button className="btn-ghost ring-1 ring-slate-300" disabled={busy}
          onClick={() => run(`/api/alerts/${a.id}/confirm`, { approve: false, note: note || null }, "Yopish qaytarildi")}>Qaytarish</button>
        <button className="btn-primary" disabled={busy}
          onClick={() => run(`/api/alerts/${a.id}/confirm`, { approve: true, note: note || null }, "Yopish tasdiqlandi")}>Tasdiqlash</button>
      </div>
    </Modal>
  );
}

type Dialog = "resolve" | "contact" | "confirm" | null;

/** Closed-loop buttons for one alert (role-aware). `extra` renders before them (e.g. "Qabul qildim"). */
export function LoopButtons({ a, extra }: { a: Alert; extra?: ReactNode }) {
  const { user } = useAuth();
  const [dialog, setDialog] = useState<Dialog>(null);
  const role = user?.role ?? "";
  const open = UNRESOLVED.includes(a.status);
  const canResolve = open && a.status !== "pending_confirmation" && RESOLVE_ROLES.includes(role);
  const canConfirm = a.status === "pending_confirmation" && CONFIRM_ROLES.includes(role) && user?.id !== a.resolved_by_user_id;
  const canContact = open && a.status !== "pending_confirmation" && CONTACT_ROLES.includes(role);
  return (
    <>
      <div className="flex flex-wrap items-center justify-end gap-2">
        {extra}
        {canContact && <button className="btn-ghost px-3 py-1 text-xs ring-1 ring-slate-300" onClick={() => setDialog("contact")}>Aloqa urinishi qo'shish</button>}
        {canResolve && (
          <button className="btn-ghost px-3 py-1 text-xs ring-1 ring-slate-300" onClick={() => setDialog("resolve")}
            title={a.has_measurement ? "" : NEED_MEASUREMENT}>
            Yopish{!a.has_measurement && " 🔒"}
          </button>
        )}
        {canConfirm && <button className="btn-primary px-3 py-1 text-xs" onClick={() => setDialog("confirm")}>Yopishni tasdiqlash</button>}
        {a.status === "pending_confirmation" && !canConfirm && (
          <span className="text-xs text-amber-800">Boshqa xodim tasdig'i kutilmoqda</span>
        )}
      </div>
      {dialog === "resolve" && <ResolveDialog a={a} onClose={() => setDialog(null)} />}
      {dialog === "contact" && <ContactAttemptDialog a={a} onClose={() => setDialog(null)} />}
      {dialog === "confirm" && <ConfirmDialog a={a} onClose={() => setDialog(null)} />}
    </>
  );
}
