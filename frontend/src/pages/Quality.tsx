import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { LoopTiles, QualityReport } from "../api/types";
import { Empty, ErrorBox, Skeleton } from "../components/ui";
import { ROLE_LABEL } from "../i18n/uz";
import { fmtPct } from "../lib/format";
import { Kpi } from "./Dashboard";

function fmtValue(reason: string, v: number | null): string {
  if (v == null) return "";
  if (reason === "identical_bp" || reason === "digit_bias") return fmtPct(v);
  if (reason === "low_variation") return `SD ${v.toFixed(1)} mmHg`;
  return String(v);
}

/** Department head tiles: acknowledged-but-unmeasured rate and unreachable RED alerts. */
export function LoopTilesRow({ tiles }: { tiles: LoopTiles }) {
  return (
    <>
      <Kpi label="Qabul qilingan, lekin o'lchovsiz" value={fmtPct(tiles.acknowledged_without_measurement_rate)}
        tone={tiles.acknowledged_without_measurement ? "text-amber-600" : undefined}
        hint={`${tiles.acknowledged_without_measurement} / ${tiles.acknowledged} ta · ${tiles.window_days} kun`} />
      <Kpi label="Aloqa o'rnatilmagan qizil" value={tiles.unreachable_red} tone={tiles.unreachable_red ? "text-zred" : undefined}
        hint="faol, o'lchov yo'q" />
    </>
  );
}

export default function Quality() {
  const q = useQuery({ queryKey: ["quality"], queryFn: () => api<QualityReport>("/api/quality") });
  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <Skeleton className="h-96" />;
  const d = q.data;
  return (
    <div className="space-y-5">
      <div>
        <h1>Sifat nazorati</h1>
        <p className="mt-1 text-sm text-slate-500">
          Oxirgi 30 kun bo'yicha oddiy statistik belgilar. Bu — <b>{d.label_uz}</b>: sabab har doim suhbat orqali aniqlanadi.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <LoopTilesRow tiles={d.tiles} />
      </div>
      {!d.users.length ? <Empty text="Hozircha signal yo'q" /> : (
        <div className="space-y-3">
          {d.users.map((u) => (
            <div key={u.user_id} className="card">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{u.user}</span>
                {u.role && <span className="text-xs text-slate-500">{ROLE_LABEL[u.role]}</span>}
                <span className="rounded bg-amber-50 px-1.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200">{d.label_uz}</span>
              </div>
              <ul className="mt-2 space-y-1.5 text-sm">
                {u.signals.map((s) => (
                  <li key={s.reason}>
                    <b>{s.label_uz}</b>
                    {s.value != null && <span className="text-slate-500"> · {fmtValue(s.reason, s.value)}</span>}
                    {s.visits > 0 && <span className="text-slate-500"> · {s.visits} ta tashrif</span>}
                    {s.patient_codes.length > 0 && (
                      <div className="mt-0.5 flex flex-wrap gap-1.5 text-xs">
                        {s.patient_codes.slice(0, 12).map((c) => <span key={c} className="font-mono text-slate-600">{c}</span>)}
                        {s.patient_codes.length > 12 && <span className="text-slate-400">+{s.patient_codes.length - 12}</span>}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-slate-500">
        Faqat bo'lim mudiri ko'radi. Bemor ismi ko'rsatilmaydi — faqat kodlar. Batafsil: <Link to="/alerts" className="text-brand-700 hover:underline">Ogohlantirishlar</Link>. Sintetik ma'lumot (demo).
      </p>
    </div>
  );
}
