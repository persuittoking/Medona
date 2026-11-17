import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { PolyclinicMapData, Zone } from "../api/types";
import { MahallaMap } from "../components/MahallaMap";
import { ErrorBox, Skeleton } from "../components/ui";
import { ZONE_COLOR, ZONE_LABEL } from "../i18n/uz";

export function usePolyclinicMap() {
  return useQuery({ queryKey: ["polyclinic-map"], queryFn: () => api<PolyclinicMapData>("/api/polyclinic/map"), refetchInterval: 30000 });
}

export default function PolyclinicMap() {
  const q = usePolyclinicMap();
  const nav = useNavigate();
  const [zones, setZones] = useState<Zone[]>(["red", "yellow", "green"]);
  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <Skeleton className="h-[70vh]" />;
  const d = q.data;
  const points = d.points.filter((p) => zones.includes(p.zone));
  const m = d.mahallas[0];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1>Mahalla xaritasi</h1>
          <p className="mt-1 text-sm text-slate-500">{d.mahallas.map((x) => x.name).join(", ")} · {d.polyclinic.name}</p>
        </div>
        <div className="flex gap-2">
          {(["red", "yellow", "green"] as Zone[]).map((z) => {
            const on = zones.includes(z);
            return (
              <button key={z} aria-pressed={on} onClick={() => setZones(on ? zones.filter((x) => x !== z) : [...zones, z])}
                className={`btn-sm btn ${on ? "bg-white ring-1 ring-slate-300" : "bg-slate-100 text-slate-400"}`}>
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: on ? ZONE_COLOR[z] : "#cbd5e1" }} />
                {ZONE_LABEL[z]} · {d.points.filter((p) => p.zone === z).length}
              </button>
            );
          })}
        </div>
      </div>
      <MahallaMap height="calc(100vh - 220px)"
        areas={d.mahallas.map((x) => ({ key: String(x.id), boundary: x.boundary, label: x.name }))}
        dots={points.map((p) => ({ key: p.patient_id, lat: p.lat, lon: p.lon, zone: p.zone, label: p.code,
          onClick: () => nav(`/patients/${p.patient_id}`) }))} />
      <p className="text-xs text-slate-500">
        Uy manzillari shaxsiy ma'lumot: faqat shu poliklinika xodimlariga ko'rinadi, har bir ko'rish audit jurnaliga yoziladi.
        {m?.demo_boundary && " Mahalla chegarasi — demo chegara (haqiqiy ko'chalar bo'yicha chizilgan)."}
      </p>
    </div>
  );
}
