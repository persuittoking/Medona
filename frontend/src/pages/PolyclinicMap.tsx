import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { api } from "../api/client";
import type { MapPoint, PolyclinicMapData, PolyclinicSearchItem, Subject, Zone } from "../api/types";
import { MahallaMap, shareColor, type MapDot } from "../components/MahallaMap";
import { PolyclinicSearchPanel } from "../components/PolyclinicSearchPanel";
import { SubjectSwitch } from "../components/SubjectSwitch";
import { ErrorBox, Skeleton } from "../components/ui";
import { ZONE_COLOR, ZONE_LABEL } from "../i18n/uz";
import { useAuth } from "../lib/auth";
import { fmtPct } from "../lib/format";
import { useSubject } from "../lib/subject";

export function usePolyclinicMap(subject: Subject = "pregnancy") {
  return useQuery({
    queryKey: ["polyclinic-map", subject],
    queryFn: () => api<PolyclinicMapData>(`/api/polyclinic/map?subject=${subject}`),
    refetchInterval: 30000,
  });
}

export function pointsFor(points: MapPoint[], subject: Subject): MapPoint[] {
  return subject === "all" ? points : points.filter((p) => p.kind === subject);
}

export function toDot(p: MapPoint, nav: NavigateFunction): MapDot {
  return p.kind === "child"
    ? {
        key: `c${p.newborn_id}`, lat: p.lat, lon: p.lon, zone: p.zone, label: `${p.code} (bola)`, shape: "square",
        href: `/children/${p.newborn_id}`, onClick: () => nav(`/children/${p.newborn_id}`),
      }
    : {
        key: `p${p.patient_id}`, lat: p.lat, lon: p.lon, zone: p.zone, label: p.code, shape: "circle",
        href: `/patients/${p.patient_id}`, onClick: () => nav(`/patients/${p.patient_id}`),
      };
}

/** Map points -> dots: pregnant women as circles, children as rounded squares; click opens the card. */
export function toDots(points: MapPoint[], nav: NavigateFunction): MapDot[] {
  return points.map((p) => toDot(p, nav));
}

export const NURSE_MAP_INFO = "Xaritada faqat qizil zonadagi (shoshilinch yordam kerak bo'lgan) bemorlar ko'rsatiladi";

/** Mahalla tooltip from the server's aggregate counts (never from the possibly red-only points). */
function mahallaLabel(x: { name: string; total?: number; red?: number; yellow?: number; green?: number }): string {
  return `${x.name} — Jami: ${x.total ?? 0} (Qizil ${x.red ?? 0}, Sariq ${x.yellow ?? 0}, Yashil ${x.green ?? 0})`;
}

export default function PolyclinicMap() {
  const { user } = useAuth();
  const [subject, setSubject] = useSubject();
  const q = usePolyclinicMap(subject);
  const nav = useNavigate();
  const [zones, setZones] = useState<Zone[]>(["red", "yellow", "green"]);
  const [mahallaChoice, setMahallaFilter] = useState<number | "all" | null>(null);
  const [otherPc, setOtherPc] = useState<PolyclinicSearchItem | null>(null);
  const [selectedDot, setSelectedDot] = useState<MapDot | null>(null);

  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <Skeleton className="h-[70vh]" />;
  const d = q.data;
  // Nurse: the server sends red-zone points only; no zone toggles and no polyclinic search panel.
  const redOnly = !!d.red_only || user?.role === "nurse";
  const myMahalla = user?.mahalla_id;
  const ownMahalla = redOnly && myMahalla != null && d.mahallas.some((x) => x.id === myMahalla) ? myMahalla : "all";
  const mahallaFilter = mahallaChoice ?? ownMahalla;
  const bySubject = pointsFor(d.points, subject);
  const byMahalla = mahallaFilter === "all" ? bySubject : bySubject.filter((p) => p.mahalla_id === mahallaFilter);
  const points = redOnly ? byMahalla : byMahalla.filter((p) => zones.includes(p.zone));
  const nChild = d.points.filter((p) => p.kind === "child").length;
  const counts = d.subject_counts ?? { pregnancy: d.points.length - nChild, child: nChild, all: d.points.length };
  const totalAll = d.mahallas.reduce((sum, x) => sum + (x.total ?? 0), 0);
  const m = d.mahallas[0];

  const visibleMahallas = mahallaFilter === "all" ? d.mahallas : d.mahallas.filter((x) => x.id === mahallaFilter);
  const areas = otherPc
    ? otherPc.mahallas.map((x) => ({
        key: `other-${otherPc.id}-${x.id}`,
        boundary: x.boundary,
        fill: shareColor(x.red_share ?? 0),
        label: `${x.name} — Jami: ${x.total} (Qizil ${x.red}, Sariq ${x.yellow}, Yashil ${x.green} · Qizil ulushi ${fmtPct(x.red_share)})`,
      }))
    : visibleMahallas.map((x) => ({ key: String(x.id), boundary: x.boundary, label: mahallaLabel(x) }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1>Mahalla xaritasi</h1>
          <p className="mt-1 text-sm text-slate-500">
            {otherPc
              ? `${otherPc.mahallas.map((x) => x.name).join(", ")} · ${otherPc.name} (${otherPc.city})`
              : `${d.mahallas.map((x) => x.name).join(", ")} · ${d.polyclinic.name}`}
          </p>
        </div>
        <SubjectSwitch value={subject} onChange={setSubject} counts={counts} />
      </div>

      {otherPc ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-amber-50 px-4 py-2.5 text-sm text-amber-900 ring-1 ring-amber-200">
          <span>
            <b>Boshqa poliklinika — faqat umumiy sonlar:</b> {otherPc.name} ({otherPc.code}) · Jami {otherPc.total} · Qizil {otherPc.red} · Sariq {otherPc.yellow} · Yashil {otherPc.green}
          </span>
          <button type="button" className="btn-sm btn bg-white ring-1 ring-amber-300" onClick={() => setOtherPc(null)}>
            ← O'z poliklinikam ({d.polyclinic.code})
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2">
          {redOnly ? (
            <p className="flex items-center gap-2 text-sm text-slate-600">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: ZONE_COLOR.red }} />
              {NURSE_MAP_INFO}
            </p>
          ) : (
          <div className="flex flex-wrap gap-2">
            {(["red", "yellow", "green"] as Zone[]).map((z) => {
              const on = zones.includes(z);
              return (
                <button key={z} aria-pressed={on} onClick={() => setZones(on ? zones.filter((x) => x !== z) : [...zones, z])}
                  className={`btn-sm btn ${on ? "bg-white ring-1 ring-slate-300" : "bg-slate-100 text-slate-400"}`}>
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: on ? ZONE_COLOR[z] : "#cbd5e1" }} />
                  {ZONE_LABEL[z]} · {byMahalla.filter((p) => p.zone === z).length}
                </button>
              );
            })}
          </div>
          )}
          {d.mahallas.length > 1 && (
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setMahallaFilter("all")}
                className={`btn-sm btn ${mahallaFilter === "all" ? "bg-brand-700 text-white" : "bg-white ring-1 ring-slate-300"}`}
              >
                Barcha mahallalar ({totalAll})
              </button>
              {d.mahallas.map((mh) => {
                const cnt = mh.total ?? 0;
                return (
                  <button
                    key={mh.id}
                    type="button"
                    onClick={() => setMahallaFilter(mh.id)}
                    className={`btn-sm btn ${mahallaFilter === mh.id ? "bg-brand-700 text-white" : "bg-white ring-1 ring-slate-300"}`}
                  >
                    {mh.name} ({cnt})
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      <div className={redOnly ? "" : "grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]"}>
        <MahallaMap
          height="calc(100vh - 260px)"
          areas={areas}
          dots={otherPc ? [] : toDots(points, nav)}
          selectedDot={otherPc ? null : selectedDot}
          onCloseSelectedDot={() => setSelectedDot(null)}
          legendZones={redOnly ? ["red"] : undefined}
        />
        {!redOnly && (
        <PolyclinicSearchPanel
          subject={subject}
          ownPolyclinicId={d.polyclinic.id}
          selectedPolyclinic={otherPc}
          onSelectPolyclinic={(pc) => {
            setOtherPc(pc);
            setSelectedDot(null);
          }}
          ownPoints={bySubject}
          onSelectPoint={(pt) => {
            setMahallaFilter("all");
            if (!zones.includes(pt.zone)) setZones((zs) => [...zs, pt.zone]);
            setSelectedDot(toDot(pt, nav));
          }}
        />
        )}
      </div>

      <p className="text-xs text-slate-500">
        {otherPc
          ? "Boshqa poliklinika — faqat umumiy sonlar va qizil ulushi bo'yicha mahalla chegaralari ko'rsatiladi (bemor nuqtalari va kodlari ko'rsatilmaydi)."
          : "Doira — homilador ayol, kvadrat — 0–1 yoshli bola (onasining uy manzilida ko'rsatiladi). Uy manzillari shaxsiy ma'lumot: faqat shu poliklinika xodimlariga ko'rinadi, har bir ko'rish audit jurnaliga yoziladi."}
        {m?.demo_boundary && " Mahalla chegarasi — demo chegara (haqiqiy ko'chalar bo'yicha chizilgan)."}
      </p>
    </div>
  );
}
