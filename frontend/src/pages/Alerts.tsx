import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Alert } from "../api/types";
import { Empty, ErrorBox, Skeleton, ZoneBadge } from "../components/ui";
import { ALERT_STATUS_LABEL } from "../i18n/uz";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import { fmtDateTime, fmtWeeks, parseUtc } from "../lib/format";

function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

function Countdown({ due, now }: { due: string; now: number }) {
  const left = parseUtc(due).getTime() - now;
  if (left <= 0) return <span className="font-semibold text-zred">Muddat o'tdi</span>;
  const m = Math.floor(left / 60000);
  const s = Math.floor((left % 60000) / 1000);
  const txt = m >= 120 ? `${Math.floor(m / 60)} soat ${m % 60} daq` : `${m}:${String(s).padStart(2, "0")}`;
  return <span className={`font-mono font-semibold ${m < 10 ? "text-zred" : "text-slate-700"}`}>{txt}</span>;
}

const TABS = [
  { key: "active", label: "Faol" },
  { key: "escalated", label: "Eskalatsiya" },
  { key: "acknowledged", label: "Qabul qilingan" },
  { key: "resolved", label: "Yopilgan" },
];

export default function Alerts() {
  const [tab, setTab] = useState("active");
  const [modal, setModal] = useState<{ alert: Alert; mode: "ack" | "resolve" } | null>(null);
  const [action, setAction] = useState("");
  const [busy, setBusy] = useState(false);
  const now = useNow();
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  const health = useQuery({ queryKey: ["health"], queryFn: () => api<{ demo_mode: boolean }>("/api/health"), staleTime: 300_000 });
  const demoSla = !!health.data?.demo_mode && user?.role === "specialist";
  const q = useQuery({ queryKey: ["alerts", tab], queryFn: () => api<Alert[]>(`/api/alerts?status=${tab}`), refetchInterval: 15000 });

  async function submit() {
    if (!modal) return;
    setBusy(true);
    try {
      await api(`/api/alerts/${modal.alert.id}/${modal.mode}`, { method: "POST", json: { action_taken: action } });
      toast({ kind: "success", title: modal.mode === "ack" ? "Ogohlantirish qabul qilindi" : "Ogohlantirish yopildi" });
      setModal(null);
      setAction("");
      qc.invalidateQueries();
    } catch (e) {
      toast({ kind: "error", title: "Xatolik", body: e instanceof Error ? e.message : undefined });
    } finally {
      setBusy(false);
    }
  }

  async function expireSla(a: Alert) {
    try {
      await api(`/api/alerts/${a.id}/demo-expire-sla`, { method: "POST" });
      toast({ kind: "success", title: "SLA muddati tugatildi", body: "30 soniya ichida eskalatsiya bo'ladi." });
      qc.invalidateQueries({ queryKey: ["alerts"] });
    } catch (e) {
      toast({ kind: "error", title: "Xatolik", body: e instanceof Error ? e.message : undefined });
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Ogohlantirishlar</h1>
      <div className="flex gap-1 overflow-x-auto">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm ${tab === t.key ? "bg-brand-700 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {q.error ? <ErrorBox error={q.error} /> : q.isLoading ? <Skeleton className="h-48" /> : !q.data?.length ? <Empty text="Ogohlantirishlar yo'q" /> : (
        <div className="space-y-2">
          {q.data.map((a) => (
            <div key={a.id} className={`card border-l-4 ${a.level === "red" ? "border-l-zred" : "border-l-zyellow"}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <ZoneBadge zone={a.level} />
                    <Link to={`/patients/${a.patient_id}`} className="font-mono font-semibold text-brand-700 hover:underline">{a.patient_code}</Link>
                    {a.gestational_weeks != null && <span className="text-sm text-slate-500">{fmtWeeks(a.gestational_weeks)}</span>}
                    <span className="text-sm text-slate-500">· {a.mahalla_name}</span>
                    {a.escalation_level > 0 && <span className="rounded bg-red-100 px-1.5 text-xs font-semibold text-red-800">⚠️ {a.escalation_level}-daraja eskalatsiya</span>}
                  </div>
                  <ul className="mt-1 text-sm text-slate-700">{a.reasons.map((r) => <li key={r}>• {r}</li>)}</ul>
                  <div className="mt-1 text-xs text-slate-500">
                    Yaratilgan: {fmtDateTime(a.created_at)} · Mas'ul: {a.assigned_to ?? "—"} · Holat: {ALERT_STATUS_LABEL[a.status]}
                  </div>
                  {a.action_taken && <div className="mt-1 text-xs text-slate-600">Ko'rilgan chora: {a.action_taken}</div>}
                </div>
                <div className="flex flex-col items-end gap-2">
                  {(a.status === "open" || a.status === "escalated") && (
                    <>
                      <div className="text-xs text-slate-500">Javob muddati: <Countdown due={a.sla_due_at} now={now} /></div>
                      <button className="btn-primary" onClick={() => setModal({ alert: a, mode: "ack" })}>Qabul qildim</button>
                      {demoSla && a.escalation_level < 2 && (
                        <button className="btn-ghost px-2 py-1 text-xs" onClick={() => expireSla(a)}
                          title="Faqat demo rejimida: keyingi tekshiruvda (≤30 s) eskalatsiya bo'ladi">
                          Demo: SLA muddatini hozir tugatish
                        </button>
                      )}
                    </>
                  )}
                  {a.status === "acknowledged" && <button className="btn-ghost" onClick={() => setModal({ alert: a, mode: "resolve" })}>Yopish</button>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal && (
        <div className="fixed inset-0 z-[1500] flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
          <div className="card w-full max-w-md">
            <h2 className="font-semibold">{modal.mode === "ack" ? "Ogohlantirishni qabul qilish" : "Ogohlantirishni yopish"} — {modal.alert.patient_code}</h2>
            <label className="label mt-3" htmlFor="act">Qanday chora ko'rildi? (majburiy)</label>
            <textarea id="act" className="input min-h-[90px]" autoFocus value={action} onChange={(e) => setAction(e.target.value)}
              placeholder="Masalan: Bemor bilan bog'lanildi, perinatal markazga yo'llandi" />
            <div className="mt-3 flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setModal(null)}>Bekor qilish</button>
              <button className="btn-primary" disabled={busy || action.trim().length < 3} onClick={submit}>Tasdiqlash</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
