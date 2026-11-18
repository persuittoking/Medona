import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { MapPoint, PolyclinicSearchItem, Subject } from "../api/types";
import { ZONE_COLOR, ZONE_LABEL } from "../i18n/uz";
import { ZoneBadge } from "./ui";

/** Normalize Uzbek apostrophe variants (o‘/o'/oʻ, g‘/g'/gʻ) so client-side filtering matches backend search. */
export function normUz(s: string): string {
  return (s || "").toLowerCase().replace(/['‘’ʻʼ`´ʹ]/g, "'").trim();
}

export function matchUz(query: string, ...fields: (string | undefined | null)[]): boolean {
  const q = normUz(query);
  if (!q) return true;
  const qBare = q.replace(/'/g, "");
  return fields.some((f) => {
    const n = normUz(f ?? "");
    return n.includes(q) || (qBare.length > 0 && n.replace(/'/g, "").includes(qBare));
  });
}

export function PolyclinicSearchPanel({
  subject,
  ownPolyclinicId,
  selectedPolyclinic,
  onSelectPolyclinic,
  ownPoints,
  onSelectPoint,
}: {
  subject: Subject;
  ownPolyclinicId?: number | null;
  selectedPolyclinic: PolyclinicSearchItem | null;
  onSelectPolyclinic: (item: PolyclinicSearchItem | null) => void;
  ownPoints?: MapPoint[];
  onSelectPoint?: (pt: MapPoint) => void;
}) {
  const [q, setQ] = useState("");
  const [codeQ, setCodeQ] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const search = useQuery({
    queryKey: ["polyclinic-search", q.trim(), subject],
    queryFn: () =>
      api<PolyclinicSearchItem[]>(
        `/api/geo/polyclinics/search?subject=${subject}&q=${encodeURIComponent(q.trim())}`,
      ),
  });

  const results = useMemo(() => {
    const list = search.data ?? [];
    if (!q.trim()) return list;
    return list.filter((p) =>
      matchUz(q, p.name, p.code, p.city, p.region_name, ...p.mahallas.map((m) => m.name)),
    );
  }, [search.data, q]);

  const codeMatches = useMemo(() => {
    if (!ownPoints || !codeQ.trim()) return [];
    const term = codeQ.trim().toLowerCase();
    return ownPoints.filter((p) => p.code.toLowerCase().includes(term)).slice(0, 8);
  }, [ownPoints, codeQ]);

  const body = (
    <div className="space-y-4">
      <div>
        <label className="label" htmlFor="pc-search">Poliklinika yoki mahalla</label>
        <input
          id="pc-search"
          className="input"
          placeholder="Poliklinika yoki mahalla qidirish…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      {selectedPolyclinic && ownPolyclinicId && selectedPolyclinic.id !== ownPolyclinicId && (
        <div className="rounded-lg bg-amber-50 p-2.5 text-xs text-amber-900 ring-1 ring-amber-200">
          <div className="font-semibold">Boshqa poliklinika — faqat umumiy sonlar</div>
          <button
            type="button"
            className="mt-1 font-medium text-brand-700 hover:underline"
            onClick={() => onSelectPolyclinic(null)}
          >
            ← O'z poliklinikamga qaytish
          </button>
        </div>
      )}

      <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
        {results.length === 0 ? (
          <p className="py-4 text-center text-xs text-slate-500">Poliklinika yoki mahalla topilmadi</p>
        ) : (
          results.map((item) => {
            const isOwn = ownPolyclinicId === item.id;
            const isSelected = selectedPolyclinic ? selectedPolyclinic.id === item.id : isOwn;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelectPolyclinic(isOwn ? null : item)}
                className={`w-full rounded-lg border p-2.5 text-left transition ${
                  isSelected
                    ? "border-brand-700 bg-brand-50/70 ring-1 ring-brand-700"
                    : "border-slate-200 bg-white hover:bg-slate-50"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-semibold text-brand-800">{item.code}</span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">
                    {item.mahalla_count} ta mahalla
                  </span>
                </div>
                <div className="mt-0.5 text-sm font-medium leading-snug text-slate-900">{item.name}</div>
                <div className="text-xs text-slate-500">
                  {item.city} · {item.mahallas.map((m) => m.name).join(", ")}
                </div>
                <div className="mt-1.5 flex items-center gap-3 text-xs">
                  <span className="flex items-center gap-1 font-medium text-zred">
                    <span className="h-2 w-2 rounded-full" style={{ background: ZONE_COLOR.red }} />
                    {ZONE_LABEL.red} {item.red}
                  </span>
                  <span className="flex items-center gap-1 font-medium text-amber-700">
                    <span className="h-2 w-2 rounded-full" style={{ background: ZONE_COLOR.yellow }} />
                    {ZONE_LABEL.yellow} {item.yellow}
                  </span>
                  <span className="flex items-center gap-1 font-medium text-zgreen">
                    <span className="h-2 w-2 rounded-full" style={{ background: ZONE_COLOR.green }} />
                    {ZONE_LABEL.green} {item.green}
                  </span>
                </div>
              </button>
            );
          })
        )}
      </div>

      {ownPoints && onSelectPoint && (
        <div className="border-t border-slate-200 pt-3">
          <label className="label" htmlFor="pt-code-search">O'z poliklinikam bo'yicha</label>
          <input
            id="pt-code-search"
            className="input"
            placeholder="Bemor kodi bo'yicha qidirish"
            value={codeQ}
            onChange={(e) => setCodeQ(e.target.value)}
          />
          {codeQ.trim() && (
            <div className="mt-2 max-h-44 space-y-1 overflow-y-auto">
              {codeMatches.length === 0 ? (
                <p className="py-2 text-xs text-slate-500">Bemor kodi topilmadi</p>
              ) : (
                codeMatches.map((pt) => (
                  <button
                    key={`${pt.kind}-${pt.code}`}
                    type="button"
                    onClick={() => {
                      onSelectPolyclinic(null);
                      onSelectPoint(pt);
                    }}
                    className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-left text-xs hover:bg-slate-50"
                  >
                    <span className="font-mono font-semibold text-slate-800">{pt.code}</span>
                    <ZoneBadge zone={pt.zone} />
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <>
      {/* Desktop 320px collapsible right-side panel */}
      <aside className={`hidden shrink-0 lg:block ${collapsed ? "w-11" : "w-80"}`}>
        {collapsed ? (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            className="card flex h-full w-11 flex-col items-center justify-center gap-2 p-2 text-xs font-medium text-slate-600 hover:bg-slate-50"
            title="Qidiruv panelini ochish"
          >
            <span>◀</span>
            <span className="[writing-mode:vertical-rl]">Qidiruv</span>
          </button>
        ) : (
          <div className="card space-y-3 p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-900">Poliklinikalar qidiruvi</h3>
              <button
                type="button"
                onClick={() => setCollapsed(true)}
                className="text-xs text-slate-400 hover:text-slate-700"
                title="Yig'ish"
              >
                ▶
              </button>
            </div>
            {body}
          </div>
        )}
      </aside>

      {/* Mobile bottom sheet */}
      <div className="lg:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen((o) => !o)}
          className="btn-ghost w-full justify-between"
        >
          <span>Poliklinika yoki mahalla qidirish…</span>
          <span>{mobileOpen ? "▼" : "▲"}</span>
        </button>
        {mobileOpen && (
          <div className="fixed inset-x-0 bottom-14 z-[1200] max-h-[70vh] overflow-y-auto rounded-t-2xl border-t border-slate-200 bg-white p-4 shadow-2xl">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold">Poliklinikalar qidiruvi</h3>
              <button type="button" className="text-sm text-slate-500" onClick={() => setMobileOpen(false)}>
                Yopish ✕
              </button>
            </div>
            {body}
          </div>
        )}
      </div>
    </>
  );
}
