import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Alert, Role, Subject } from "../api/types";
import { SubjectSwitch } from "../components/SubjectSwitch";
import { Empty, ErrorBox, Skeleton, SourceTag, ZoneBadge } from "../components/ui";
import { ALERT_EVENT_LABEL, ALERT_STATUS_LABEL, FINAL_DECISION, ROLE_LABEL } from "../i18n/uz";
import { useAuth } from "../lib/auth";
import { useToast } from "../lib/toast";
import { fmtDateTime, parseUtc } from "../lib/format";
import { useSubject } from "../lib/subject";

const bySubject = (alerts: Alert[] | undefined, s: Subject) => (alerts ?? []).filter((a) => s === "all" || a.subject === s);

const FAST_POLL_MS = 3000; // while a summary is pending or a deadline has passed (scheduler runs every 30 s)
const SLOW_POLL_MS = 15000;

/** Who gets the alert next, in the dative ("...ga yuborildi"). */
const NEXT_TARGET: Partial<Record<Role, string>> = {
  department_head: "Bo'lim mudiriga",
  doctor: "Oilaviy shifokorga",
  district_admin: "Tuman boshqaruviga (faqat soni)",
};

const isActive = (a: Alert) => a.status === "open" || a.status === "escalated";
const isOverdue = (a: Alert, now: number) => isActive(a) && parseUtc(a.sla_due_at).getTime() <= now;

function useNow(ms = 1000) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

function pollMs(alerts: Alert[] | undefined): number {
  if (!alerts) return SLOW_POLL_MS;
  const now = Date.now();
  return alerts.some((a) => (isActive(a) && a.summary_status === "pending") || (isOverdue(a, now) && a.next_role))
    ? FAST_POLL_MS
    : SLOW_POLL_MS;
}

function fmtLeft(ms: number): string {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h >= 2) return `${h} soat ${m} daq`;
  const mm = String(h * 60 + m).padStart(2, "0");
  return `${mm}:${String(s).padStart(2, "0")}`;
}

/** Live SLA timer. At zero: "...ga yuborilmoqda" until the next scheduler run (<= 30 s) escalates it. */
function SlaTimer({ a, now }: { a: Alert; now: number }) {
  const left = parseUtc(a.sla_due_at).getTime() - now;
  if (left <= 0) {
    return a.next_role ? (
      <span className="font-semibold text-zred">Muddat tugadi — {NEXT_TARGET[a.next_role] ?? "yuqori darajaga"} yuborilmoqda…</span>
    ) : (
      <span className="font-semibold text-zred">Muddat o'tdi</span>
    );
  }
  const urgent = left < 10 * 60_000;
  return (
    <span>
      Javob berish uchun qoldi:{" "}
      <span className={`font-mono font-semibold ${urgent ? "text-zred" : "text-slate-700"}`}>{fmtLeft(left)}</span>
    </span>
  );
}

function EscalationBadge({ a }: { a: Alert }) {
  if (a.escalation_level === 0) return null;
  const text = a.escalation_level >= 2
    ? "Tuman boshqaruviga xabar berildi"
    : a.assigned_role === "department_head" ? "Bo'lim mudiriga yuborildi" : `${a.escalation_level}-daraja eskalatsiya`;
  return <span className="rounded bg-red-100 px-1.5 text-xs font-semibold text-red-800">⚠️ {text}</span>;
}

function TrendBadge() {
  return (
    <span className="rounded bg-orange-50 px-1.5 text-xs font-semibold text-orange-800 ring-1 ring-orange-200"
      title="Ogohlantirish oxirgi ko'riklardagi yomonlashish trendiga asoslangan">
      ↗ Prognoz: yomonlashish trendi
    </span>
  );
}

/** The 3 doctor bullets (AI or template) inside the alert. */
function AlertBullets({ a }: { a: Alert }) {
  if (a.summary_status === "unavailable") {
    return <ul className="mt-1 text-sm text-slate-700">{a.reasons.map((r) => <li key={r}>• {r}</li>)}</ul>;
  }
  if (a.summary_status === "pending" || !a.summary_bullets) {
    return (
      <div className="mt-2 space-y-1.5" aria-busy="true">
        <p className="text-xs text-slate-500">AI xulosa tayyorlanmoqda…</p>
        <Skeleton className="h-3 w-11/12" />
        <Skeleton className="h-3 w-10/12" />
        <Skeleton className="h-3 w-8/12" />
      </div>
    );
  }
  return (
    <div className="mt-2 rounded-lg bg-slate-50 p-2.5 ring-1 ring-slate-200">
      <div className="mb-1 flex items-center gap-2 text-xs text-slate-500">
        Qisqacha (3 band) {a.summary_source && <SourceTag source={a.summary_source} />}
      </div>
      <ul className="space-y-1 text-sm text-slate-800">
        {a.summary_bullets.map((b, i) => (
          <li key={i} className="flex gap-2"><span className="font-semibold text-slate-400">{i + 1}.</span><span>{b}</span></li>
        ))}
      </ul>
      <p className="mt-1.5 text-xs text-amber-800">{FINAL_DECISION}.</p>
    </div>
  );
}

function AlertHistory({ a }: { a: Alert }) {
  return (
    <ol className="mt-2 space-y-1 border-l-2 border-slate-200 pl-3 text-xs text-slate-600">
      {a.history.map((e, i) => (
        <li key={i}>
          <span className="font-mono text-slate-400">{fmtDateTime(e.at)}</span> · {ALERT_EVENT_LABEL[e.event] ?? e.event}
          {e.assignee && <> → <b>{e.assignee}</b>{e.assignee_role && ` (${ROLE_LABEL[e.assignee_role]})`}</>}
          {e.actor && e.event !== "acknowledged" && <> · {e.actor}</>}
          {e.note && <span className="text-slate-500"> — {e.note}</span>}
        </li>
      ))}
    </ol>
  );
}

interface CardProps {
  a: Alert;
  now: number;
  demoSla: boolean;
  canReassign: boolean;
  onModal: (a: Alert, mode: Mode) => void;
  onExpire: (a: Alert) => void;
}

function AlertCard({ a, now, demoSla, canReassign, onModal, onExpire }: CardProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`card border-l-4 ${a.level === "red" ? "border-l-zred" : "border-l-zyellow"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <ZoneBadge zone={a.level} />
            <Link to={a.subject === "child" ? `/children/${a.newborn_id}` : `/patients/${a.patient_id}`}
              className="font-mono font-semibold text-brand-700 hover:underline">{a.patient_code}</Link>
            {a.subject_label && (
              <span className={`rounded px-1.5 text-xs font-semibold ${a.subject === "child" ? "bg-sky-50 text-sky-800 ring-1 ring-sky-200" : "bg-slate-100 text-slate-700"}`}>
                {a.subject_label}
              </span>
            )}
            <span className="text-sm text-slate-500">· {a.mahalla_name}</span>
            {a.trend_driven && <TrendBadge />}
            <EscalationBadge a={a} />
          </div>
          <AlertBullets a={a} />
          <div className="mt-1.5 text-xs text-slate-500">
            Yaratilgan: {fmtDateTime(a.created_at)} · Mas'ul: {a.assigned_to ?? "—"} · Holat: {ALERT_STATUS_LABEL[a.status]}
            {" · "}
            <button className="text-brand-700 hover:underline" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
              {open ? "Yopish" : "Batafsil: eskalatsiya tarixi"}
            </button>
          </div>
          {open && <AlertHistory a={a} />}
          {a.action_taken && <div className="mt-1 text-xs text-slate-600">Ko'rilgan chora: {a.action_taken}</div>}
        </div>
        <div className="flex flex-col items-end gap-2">
          {isActive(a) && (
            <>
              <div className="text-xs text-slate-500"><SlaTimer a={a} now={now} /></div>
              <button className="btn-primary" onClick={() => onModal(a, "ack")}>Qabul qildim</button>
              {canReassign && (
                <button className="btn-ghost px-3 py-1 text-xs" onClick={() => onModal(a, "reassign")}>Mutaxassisga qayta biriktirish</button>
              )}
              {demoSla && a.escalation_level < 2 && (
                <button className="btn-ghost px-2 py-1 text-xs" onClick={() => onExpire(a)}
                  title="Faqat demo rejimida: keyingi tekshiruvda (≤30 s) eskalatsiya bo'ladi">
                  Demo: SLA muddatini hozir tugatish
                </button>
              )}
            </>
          )}
          {a.status === "acknowledged" && <button className="btn-ghost" onClick={() => onModal(a, "resolve")}>Yopish</button>}
        </div>
      </div>
    </div>
  );
}

type Mode = "ack" | "resolve" | "reassign";

const TABS = [
  { key: "active", label: "Faol" },
  { key: "escalated", label: "Eskalatsiya" },
  { key: "acknowledged", label: "Qabul qilingan" },
  { key: "resolved", label: "Yopilgan" },
];

export default function Alerts() {
  const [tab, setTab] = useState("active");
  const [modal, setModal] = useState<{ alert: Alert; mode: Mode } | null>(null);
  const [action, setAction] = useState("");
  const [target, setTarget] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const now = useNow();
  const qc = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  const [subject, setSubject] = useSubject();
  const isHead = user?.role === "department_head";
  const health = useQuery({ queryKey: ["health"], queryFn: () => api<{ demo_mode: boolean }>("/api/health"), staleTime: 300_000 });
  const demoSla = !!health.data?.demo_mode && (user?.role === "specialist" || isHead);
  const q = useQuery({
    queryKey: ["alerts", tab],
    queryFn: () => api<Alert[]>(`/api/alerts?status=${tab}`),
    refetchInterval: (query) => pollMs(query.state.data),
  });
  const late = useQuery({
    queryKey: ["alerts", "late"],
    queryFn: () => api<Alert[]>("/api/alerts?status=active&mine=true&escalated=true"),
    refetchInterval: (query) => pollMs(query.state.data),
    enabled: isHead,
  });
  const specialists = useQuery({
    queryKey: ["assignees"],
    queryFn: () => api<{ id: number; full_name: string }[]>("/api/alerts/assignees"),
    enabled: isHead,
    staleTime: 300_000,
  });

  function openModal(a: Alert, mode: Mode) {
    setModal({ alert: a, mode });
    setAction("");
    setTarget(specialists.data?.[0]?.id ?? "");
  }

  async function submit() {
    if (!modal) return;
    setBusy(true);
    try {
      const json = modal.mode === "reassign" ? { user_id: target, note: action || null } : { action_taken: action };
      await api(`/api/alerts/${modal.alert.id}/${modal.mode}`, { method: "POST", json });
      const title = { ack: "Ogohlantirish qabul qilindi", resolve: "Ogohlantirish yopildi", reassign: "Mutaxassisga qayta biriktirildi" }[modal.mode];
      toast({ kind: "success", title });
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

  const card = (a: Alert) => (
    <AlertCard key={a.id} a={a} now={now} demoSla={demoSla} canReassign={isHead && isActive(a)}
      onModal={openModal} onExpire={expireSla} />
  );
  const valid = modal?.mode === "reassign" ? target !== "" : action.trim().length >= 3;
  const rows = bySubject(q.data, subject);
  const lateRows = bySubject(late.data, subject);
  const counts = q.data && {
    pregnancy: bySubject(q.data, "pregnancy").length, child: bySubject(q.data, "child").length, all: q.data.length,
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-xl font-bold">Ogohlantirishlar</h1>
        <SubjectSwitch value={subject} onChange={setSubject} counts={counts} />
      </div>

      {isHead && (
        <section className="space-y-2 rounded-card bg-red-50/60 p-3 ring-1 ring-red-200">
          <h2 className="flex items-center gap-2 font-semibold text-red-900">
            Kechikkan ogohlantirishlar
            <span className="rounded-full bg-red-600 px-2 text-xs text-white">{lateRows.length}</span>
          </h2>
          <p className="text-xs text-red-900/80">Mutaxassis belgilangan muddatda qabul qilmagan va sizga yuborilgan ogohlantirishlar.</p>
          {late.error ? <ErrorBox error={late.error} /> : late.isLoading ? <Skeleton className="h-24" />
            : !lateRows.length ? <p className="text-sm text-slate-600">Kechikkan ogohlantirishlar yo'q.</p>
            : <div className="space-y-2">{lateRows.map(card)}</div>}
        </section>
      )}

      <div className="flex gap-1 overflow-x-auto">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-sm ${tab === t.key ? "bg-brand-700 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {q.error ? <ErrorBox error={q.error} /> : q.isLoading ? <Skeleton className="h-48" /> : !rows.length ? <Empty text="Ogohlantirishlar yo'q" /> : (
        <div className="space-y-2">{rows.map(card)}</div>
      )}

      {modal && (
        <div className="fixed inset-0 z-[1500] flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
          <div className="card w-full max-w-md">
            <h2 className="font-semibold">
              {{ ack: "Ogohlantirishni qabul qilish", resolve: "Ogohlantirishni yopish", reassign: "Mutaxassisga qayta biriktirish" }[modal.mode]} — {modal.alert.patient_code}
            </h2>
            {modal.mode === "reassign" && (
              <>
                <label className="label mt-3" htmlFor="tgt">Mutaxassis</label>
                <select id="tgt" className="input" value={target} onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : "")}>
                  {(specialists.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.full_name}</option>)}
                </select>
              </>
            )}
            <label className="label mt-3" htmlFor="act">
              {modal.mode === "reassign" ? "Izoh (ixtiyoriy)" : "Qanday chora ko'rildi? (majburiy)"}
            </label>
            <textarea id="act" className="input min-h-[90px]" autoFocus value={action} onChange={(e) => setAction(e.target.value)}
              placeholder={modal.mode === "reassign" ? "Masalan: Bemorni bugun ko'rib chiqing" : "Masalan: Bemor bilan bog'lanildi, perinatal markazga yo'llandi"} />
            <div className="mt-3 flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setModal(null)}>Bekor qilish</button>
              <button className="btn-primary" disabled={busy || !valid} onClick={submit}>Tasdiqlash</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
