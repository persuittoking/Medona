import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { api } from "../api/client";
import type { MapPoint, PolyclinicMapData, Subject, Zone } from "../api/types";
import { MahallaMap, type MapDot } from "../components/MahallaMap";
import { SubjectSwitch } from "../components/SubjectSwitch";
import { ErrorBox, Skeleton } from "../components/ui";
import { ZONE_COLOR, ZONE_LABEL } from "../i18n/uz";
import { useSubject } from "../lib/subject";

export function usePolyclinicMap() {
  return useQuery({ queryKey: ["polyclinic-map"], queryFn: () => api<PolyclinicMapData>("/api/polyclinic/map"), refetchInterval: 30000 });
}

export function pointsFor(points: MapPoint[], subject: Subject): MapPoint[] {
  return subject === "all" ? points : points.filter((p) => p.kind === subject);
}

/** Map points -> dots: pregnant women as circles, children as rounded squares; click opens the card. */
export function toDots(points: MapPoint[], nav: NavigateFunction): MapDot[] {
  return points.map((p) => p.kind === "child"
    ? { key: `c${p.newborn_id}`, lat: p.lat, lon: p.lon, zone: p.zone, label: `${p.code} (bola)`, shape: "square",
        onClick: () => nav(`/children/${p.newborn_id}`) }
    : { key: `p${p.patient_id}`, lat: p.lat, lon: p.lon, zone: p.zone, label: p.code, shape: "circle",
        onClick: () => nav(`/patients/${p.patient_id}`) });
}

export default function PolyclinicMap() {
  const q = usePolyclinicMap();
  const nav = useNavigate();
  const [subject, setSubject] = useSubject();
  const [zones, setZones] = useState<Zone[]>(["red", "yellow", "green"]);
  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <Skeleton className="h-[70vh]" />;
  const d = q.data;
  const shown = pointsFor(d.points, subject);
  const points = shown.filter((p) => zones.includes(p.zone));
  const nChild = d.points.filter((p) => p.kind === "child").length;
  const counts = { pregnancy: d.points.length - nChild, child: nChild, all: d.points.length };
  const m = d.mahallas[0];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1>Mahalla xaritasi</h1>
          <p className="mt-1 text-sm text-slate-500">{d.mahallas.map((x) => x.name).join(", ")} · {d.polyclinic.name}</p>
        </div>
        <SubjectSwitch value={subject} onChange={setSubject} counts={counts} />
      </div>
      <div className="flex flex-wrap gap-2">
        {(["red", "yellow", "green"] as Zone[]).map((z) => {
          const on = zones.includes(z);
          return (
            <button key={z} aria-pressed={on} onClick={() => setZones(on ? zones.filter((x) => x !== z) : [...zones, z])}
              className={`btn-sm btn ${on ? "bg-white ring-1 ring-slate-300" : "bg-slate-100 text-slate-400"}`}>
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: on ? ZONE_COLOR[z] : "#cbd5e1" }} />
              {ZONE_LABEL[z]} · {shown.filter((p) => p.zone === z).length}
            </button>
          );
        })}
      </div>
      <MahallaMap height="calc(100vh - 260px)"
        areas={d.mahallas.map((x) => ({ key: String(x.id), boundary: x.boundary, label: x.name }))}
        dots={toDots(points, nav)} />
      <p className="text-xs text-slate-500">
        Doira — homilador ayol, kvadrat — 0–1 yoshli bola (onasining uy manzilida ko'rsatiladi).
        Uy manzillari shaxsiy ma'lumot: faqat shu poliklinika xodimlariga ko'rinadi, har bir ko'rish audit jurnaliga yoziladi.
        {m?.demo_boundary && " Mahalla chegarasi — demo chegara (haqiqiy ko'chalar bo'yicha chizilgan)."}
      </p>
    </div>
  );
}
