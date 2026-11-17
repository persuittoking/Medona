import type { Risk } from "../api/types";
import { fmtPct } from "../lib/format";
import { ZoneBadge } from "./ui";

const DOT: Record<string, string> = { red: "bg-zred", yellow: "bg-zyellow", green: "bg-zgreen" };

/** "Nega bu zona?" — rule hits, trend hits and SHAP factors in Uzbek. */
export function RiskExplain({ risk, compact = false }: { risk: Risk; compact?: boolean }) {
  const hits = [...risk.rule_hits, ...risk.trend_hits];
  const maxShap = Math.max(0.01, ...risk.shap_top.map((s) => Math.abs(s.shap)));
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <ZoneBadge zone={risk.zone} size="lg" />
        {risk.ml_probability != null && (
          <span className="text-sm text-slate-600">
            Model bo'yicha xavf ehtimoli: <b>{fmtPct(risk.ml_probability)}</b>
          </span>
        )}
      </div>

      <section>
        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Klinik qoidalar va dinamika</h4>
        {hits.length === 0 ? (
          <p className="text-sm text-slate-500">Xavf belgilari aniqlanmadi.</p>
        ) : (
          <ul className="space-y-1">
            {hits.map((h) => (
              <li key={h.code + h.uz_text} className="flex items-start gap-2 text-sm">
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${DOT[h.zone] ?? "bg-slate-400"}`} />
                <span>
                  <span className="mr-1 font-mono text-xs text-slate-400">{h.code}</span>
                  {h.uz_text}
                </span>
              </li>
            ))}
          </ul>
        )}
        {risk.notes?.map((n) => (
          <p key={n} className="mt-1 text-sm text-slate-500">ℹ️ {n}</p>
        ))}
      </section>

      {!compact && risk.shap_top.length > 0 && (
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Modelning asosiy omillari (SHAP)
          </h4>
          <div className="space-y-1.5">
            {risk.shap_top.map((s) => (
              <div key={s.feature} className="grid grid-cols-[minmax(0,1fr)_100px] items-center gap-2 text-sm sm:grid-cols-[minmax(0,1fr)_160px]">
                <span className="truncate" title={s.uz_label}>{s.uz_label}</span>
                <div className="flex h-3 items-center" title={`${s.direction === "up" ? "xavfni oshiradi" : "xavfni kamaytiradi"}`}>
                  <div
                    className={`h-3 rounded ${s.direction === "up" ? "bg-zred/80" : "bg-zgreen/70"}`}
                    style={{ width: `${(Math.abs(s.shap) / maxShap) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-1 text-xs text-slate-400">Qizil — xavfni oshiradi, yashil — kamaytiradi.</p>
        </section>
      )}
    </div>
  );
}
