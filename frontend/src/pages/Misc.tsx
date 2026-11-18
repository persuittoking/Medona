import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { Empty, ErrorBox, Skeleton, SyntheticBadge } from "../components/ui";
import { isAdmin, type SlaSettings } from "../api/types";
import { DISCLAIMER, ROLE_LABEL } from "../i18n/uz";
import { useAuth } from "../lib/auth";
import { fmtDateTime, fmtPct } from "../lib/format";

interface Conf { sensitivity: number; specificity: number; precision: number; flag_rate: number; confusion: { tp: number; fp: number; tn: number; fn: number } }
interface Metrics {
  model_version: string; trained_on: string; n_pregnancies: number; n_rows: number; outcome_rate: number;
  cv_roc_auc: { mean: number }; test: { roc_auc: number; pr_auc: number; brier: number; base_rate: number };
  thresholds: { ml_yellow: number; ml_red: number };
  at_thresholds: Record<string, Conf>;
  calibration_curve: { predicted: number[]; observed: number[] };
  per_region: Record<string, { roc_auc: number; pr_auc: number; outcome_rate: number; system_sensitivity: number }>;
  by_trimester?: Record<string, { roc_auc: number }>;
  top_features: { feature: string; uz_label: string; mean_abs_shap: number }[];
}

const AT_LABEL: Record<string, string> = {
  ml_only_yellow_or_red: "Faqat model (sariq+qizil)",
  ml_only_red: "Faqat model (qizil)",
  rules_only_yellow_or_red: "Faqat klinik qoidalar",
  system_yellow_or_red: "Butun tizim (qoidalar + model)",
};

export function Analytics() {
  const q = useQuery({ queryKey: ["metrics"], queryFn: () => api<Metrics>("/api/analytics/model") });
  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <Skeleton className="h-96" />;
  const m = q.data;
  const cal = m.calibration_curve.predicted.map((p, i) => ({ p, o: m.calibration_curve.observed[i], ideal: p }));
  const sys = m.at_thresholds.system_yellow_or_red.confusion;
  const maxImp = Math.max(...m.top_features.map((f) => f.mean_abs_shap));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-bold">Model kartasi</h1>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900">Sintetik ma'lumotda o'qitilgan</span>
        <span className="text-sm text-slate-500">versiya {m.model_version} · {m.trained_on} · {m.n_pregnancies.toLocaleString()} homiladorlik</span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {[["ROC-AUC", m.test.roc_auc.toFixed(3)], ["PR-AUC", m.test.pr_auc.toFixed(3)], ["Brier", m.test.brier.toFixed(3)],
          ["Tizim sezgirligi", fmtPct(m.at_thresholds.system_yellow_or_red.sensitivity)], ["Asosiy chastota", fmtPct(m.test.base_rate)]].map(([k, v]) => (
          <div key={k} className="card"><div className="text-xs text-slate-500">{k}</div><div className="text-2xl font-bold">{v}</div></div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="card">
          <h3 className="mb-2 font-semibold">Kalibrlash egri chizig'i</h3>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={cal} margin={{ left: -15, right: 10 }}>
              <CartesianGrid stroke="#f1f5f9" />
              <XAxis dataKey="p" type="number" domain={[0, "dataMax"]} tickFormatter={(v: number) => fmtPct(v)} fontSize={11} />
              <YAxis tickFormatter={(v: number) => fmtPct(v)} fontSize={11} />
              <Tooltip formatter={(v: number) => fmtPct(v)} labelFormatter={(v) => `Bashorat ${fmtPct(Number(v))}`} />
              <Line dataKey="ideal" name="Ideal" stroke="#cbd5e1" strokeDasharray="4 4" dot={false} />
              <Line dataKey="o" name="Kuzatilgan" stroke="#0f766e" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <h3 className="mb-2 font-semibold">Chegaralarda sezgirlik va o'ziga xoslik</h3>
          <table className="w-full text-sm">
            <thead><tr className="border-b"><th className="th">Usul</th><th className="th">Sezgirlik</th><th className="th">O'ziga xoslik</th><th className="th">Aniqlik</th></tr></thead>
            <tbody>{Object.entries(m.at_thresholds).map(([k, v]) => (
              <tr key={k} className="border-b last:border-0"><td className="td">{AT_LABEL[k] ?? k}</td><td className="td">{fmtPct(v.sensitivity)}</td><td className="td">{fmtPct(v.specificity)}</td><td className="td">{fmtPct(v.precision)}</td></tr>
            ))}</tbody>
          </table>
          <h4 className="mb-1 mt-4 text-sm font-semibold">Chalkashlik matritsasi (butun tizim)</h4>
          <div className="grid max-w-xs grid-cols-2 gap-1 text-center text-sm">
            <div className="rounded bg-green-50 p-2">TP {sys.tp}</div><div className="rounded bg-amber-50 p-2">FP {sys.fp}</div>
            <div className="rounded bg-red-50 p-2">FN {sys.fn}</div><div className="rounded bg-slate-50 p-2">TN {sys.tn}</div>
          </div>
          <p className="mt-2 text-xs text-slate-500">Chegaralar: sariq ≥ {m.thresholds.ml_yellow}, qizil ≥ {m.thresholds.ml_red}</p>
        </div>
        <div className="card">
          <h3 className="mb-2 font-semibold">Hududlar bo'yicha (adolatlilik tekshiruvi)</h3>
          <table className="w-full text-sm">
            <thead><tr className="border-b"><th className="th">Hudud</th><th className="th">ROC-AUC</th><th className="th">PR-AUC</th><th className="th">Tizim sezgirligi</th></tr></thead>
            <tbody>{Object.entries(m.per_region).map(([k, v]) => (
              <tr key={k} className="border-b last:border-0"><td className="td">{k}</td><td className="td">{v.roc_auc.toFixed(3)}</td><td className="td">{v.pr_auc.toFixed(3)}</td><td className="td">{fmtPct(v.system_sensitivity)}</td></tr>
            ))}</tbody>
          </table>
          {m.by_trimester && <p className="mt-2 text-xs text-slate-500">ROC-AUC trimestrlar bo'yicha: {Object.entries(m.by_trimester).map(([k, v]) => `${k} ${v.roc_auc.toFixed(2)}`).join(" · ")}</p>}
        </div>
        <div className="card">
          <h3 className="mb-2 font-semibold">Eng muhim omillar (o'rtacha |SHAP|)</h3>
          <div className="space-y-1">{m.top_features.slice(0, 10).map((f) => (
            <div key={f.feature} className="grid grid-cols-[minmax(0,1fr)_120px] items-center gap-2 text-sm">
              <span className="truncate">{f.uz_label}</span>
              <div className="h-3 rounded bg-brand-600" style={{ width: `${(f.mean_abs_shap / maxImp) * 100}%` }} />
            </div>
          ))}</div>
        </div>
      </div>
    </div>
  );
}

interface AuditRow { id: number; created_at: string; action: string; entity: string; entity_id: number | null; ip: string | null; user: string; role: string | null; polyclinic: string | null }
const ACTION_LABEL: Record<string, string> = {
  login: "Tizimga kirish", view_patient: "Bemor kartasini ko'rish", view_child: "Bola kartasini ko'rish", reveal_pii: "Shaxsiy ma'lumotni ochish",
  create_visit: "Tashrif kiritish", create_child_check: "Bola ko'rigini kiritish", external_lookup: "Tashqi JShShIR qidiruv",
  external_lookup_miss: "Tashqi JShShIR qidiruv (topilmadi)", external_entry: "Boshqa poliklinikadan natija kiritish",
  view_home_points: "Uy manzillari xaritasini ko'rish", create_alert: "Ogohlantirish yaratildi", ack_alert: "Ogohlantirishni qabul qilish", resolve_alert: "Ogohlantirishni yopish",
  reassign_alert: "Mutaxassisga qayta biriktirish", escalate_alert_l1: "Eskalatsiya (1-daraja)", escalate_alert_l2: "Eskalatsiya (2-daraja)",
  demo_expire_sla: "Demo: SLA muddatini tugatish", telegram_new_alert: "Telegram: yangi ogohlantirish", telegram_escalated: "Telegram: eskalatsiya",
  telegram_reassigned: "Telegram: qayta biriktirish", telegram_admin_count: "Telegram: tuman boshqaruviga (faqat soni)",
  telegram_external_result: "Telegram: tashqi natija kelib tushdi",
};

function SlaInfo() {
  const { user } = useAuth();
  const allowed = user?.role === "department_head" || isAdmin(user?.role);
  const q = useQuery({ queryKey: ["sla"], queryFn: () => api<SlaSettings>("/api/settings/sla"), enabled: allowed });
  if (!allowed || !q.data) return null;
  const s = q.data;
  return (
    <div className="card space-y-2 text-sm">
      <h2 className="font-semibold">Javob muddatlari (SLA) — faqat ko'rish uchun</h2>
      <ul className="space-y-1 text-slate-700">
        <li>Qizil ogohlantirish: <b>{s.sla_red_minutes} daqiqa</b> (SLA_RED_MINUTES)</li>
        {s.demo_mode && <li>Demo rejimida hozir amal qiladi: <b>{s.effective_sla_red_minutes} daqiqa</b> (DEMO_SLA_RED_MINUTES)</li>}
        <li>Sariq ogohlantirish: <b>{s.sla_yellow_hours} soat</b> (SLA_YELLOW_HOURS)</li>
      </ul>
      <p className="text-slate-600">
        Qizil: {s.chain.red.map((r) => ROLE_LABEL[r]).join(" → ")}. Sariq: {s.chain.yellow.map((r) => ROLE_LABEL[r]).join(" → ")}.
        Tuman boshqaruviga faqat ogohlantirishlar soni yuboriladi, bemor ma'lumotlari yuborilmaydi.
      </p>
    </div>
  );
}

export function Audit() {
  const [action, setAction] = useState("");
  const q = useQuery({ queryKey: ["audit", action], queryFn: () => api<AuditRow[]>(`/api/audit${action ? `?action=${action}` : ""}`), refetchInterval: 15000 });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-xl font-bold">Audit jurnali</h1>
        <select className="input w-auto" value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">Barcha harakatlar</option>
          {Object.entries(ACTION_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      {q.error ? <ErrorBox error={q.error} /> : q.isLoading ? <Skeleton className="h-64" /> : !q.data?.length ? <Empty text="Yozuvlar yo'q" /> : (
        <div className="card overflow-x-auto p-0">
          <table className="w-full min-w-[640px]">
            <thead className="border-b bg-slate-50"><tr><th className="th">Vaqt</th><th className="th">Poliklinika</th><th className="th">Foydalanuvchi</th><th className="th">Harakat</th><th className="th">Obyekt</th><th className="th">IP</th></tr></thead>
            <tbody>{q.data.map((r) => (
              <tr key={r.id} className="border-b last:border-0">
                <td className="td whitespace-nowrap">{fmtDateTime(r.created_at)}</td><td className="td font-mono text-xs">{r.polyclinic ?? "—"}</td><td className="td">{r.user}</td>
                <td className="td">{ACTION_LABEL[r.action] ?? r.action}</td><td className="td font-mono text-xs">{r.entity} #{r.entity_id}</td><td className="td text-xs">{r.ip ?? "—"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function About() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center gap-3"><h1 className="text-xl font-bold">OnaRadar haqida</h1><SyntheticBadge /></div>
      <div className="card space-y-3 text-sm leading-relaxed">
        <p><b>OnaRadar</b> — homilador ayollar va chaqaloqlarni Qizil / Sariq / Yashil zonalar bo'yicha kuzatib boruvchi va holat yomonlashganda OvaBMU mutaxassislariga avtomatik xabar beruvchi erta ogohlantirish tizimi.</p>
        <p><b>Qanday ishlaydi:</b> patronaj hamshirasi tashrif ma'lumotlarini kiritadi → klinik qoidalar, dinamika qoidalari va ML modeli xavfni baholaydi → zona belgilanadi → zona yomonlashsa, mutaxassisga ogohlantirish yuboriladi → belgilangan muddatda javob bo'lmasa, yuqori darajaga eskalatsiya qilinadi.</p>
        <p className="rounded-lg bg-amber-50 p-3 text-amber-900"><b>Muhim:</b> {DISCLAIMER} Klinik qoidalar ML modelidan ustun turadi: model zonani faqat oshirishi mumkin, hech qachon pasaytirmaydi.</p>
        <p><b>Maxfiylik:</b> F.I.Sh., JShShIR va telefon raqami shifrlangan holda saqlanadi va sukut bo'yicha yashiriladi. AI xulosa Google Gemini modeli yordamida tayyorlanadi: unga faqat taxallusli bemor kodi va klinik ko'rsatkichlar yuboriladi (ism, JShShIR, telefon va manzil yuborilmaydi). Har bir bemor kartasini ko'rish audit jurnaliga yoziladi.</p>
        <p className="rounded-lg bg-slate-50 p-3 text-slate-700"><b>Gemini API haqida:</b> Google shartlariga ko'ra, bepul (unpaid) tarifda yuborilgan so'rovlar va javoblar Google mahsulotlarini yaxshilash uchun ishlatilishi va inson tomonidan ko'rib chiqilishi mumkin. Shu sababli haqiqiy bemor ma'lumotlari bilan faqat pullik (paid) Gemini API tarifidan foydalanish kerak. Kalit bo'lmasa yoki xizmat ishlamasa, AI xulosa o'rniga shablon xulosa ko'rsatiladi.</p>
        <p><b>Ma'lumotlar:</b> demo versiyadagi barcha bemorlar va ko'rsatkichlar sintetik (sun'iy yaratilgan). Model haqiqiy DMED ma'lumotlarida qayta o'qitilishi va klinik tasdiqlanishi kerak.</p>
      </div>
      <SlaInfo />
    </div>
  );
}
