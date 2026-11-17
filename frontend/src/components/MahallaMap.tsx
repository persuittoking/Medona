import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { CircleMarker, MapContainer, Polygon, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import type { GeoPolygon, Zone } from "../api/types";
import { SATELLITE, STREETS, ZONE_COLOR, ZONE_LABEL } from "../i18n/uz";

type LatLng = [number, number];
const WORLD: LatLng[] = [[-89.9, -179.9], [-89.9, 179.9], [89.9, 179.9], [89.9, -179.9]];

/** GeoJSON [lon, lat] rings -> Leaflet [lat, lon]. */
export function rings(poly: GeoPolygon): LatLng[][] {
  return poly.coordinates.map((ring) => ring.map(([lon, lat]) => [lat, lon] as LatLng));
}

export interface MapArea {
  key: string;
  boundary: GeoPolygon;
  label?: string;
  /** Fill colour (admin choropleth); omitted = transparent with glowing outline. */
  fill?: string;
  onClick?: () => void;
}

export interface MapDot {
  key: string | number;
  lat: number;
  lon: number;
  zone: Zone;
  label: string;
  onClick?: () => void;
}

function FitTo({ bounds, padding }: { bounds: L.LatLngBounds; padding: number }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds.pad(padding), { animate: true });
  }, [map, bounds, padding]);
  return null;
}

/**
 * Satellite-first map of one or more mahalla territories.
 * - fits the territory with padding ("slightly bigger"),
 * - dims everything OUTSIDE the mahallas (inverted mask),
 * - draws a thick glowing teal border,
 * - optional zone-coloured dots (patient home points — staff of the own polyclinic only).
 */
export function MahallaMap({ areas, dots = [], height = 420, padding = 0.18, dimOutside = true, interactive = true,
  defaultBase = "satellite", legend = true, overlay }: {
  areas: MapArea[];
  dots?: MapDot[];
  height?: number | string;
  padding?: number;
  dimOutside?: boolean;
  interactive?: boolean;
  defaultBase?: "satellite" | "streets";
  legend?: boolean;
  overlay?: ReactNode;
}) {
  const [base, setBase] = useState<"satellite" | "streets">(defaultBase);
  const allRings = useMemo(() => areas.map((a) => ({ ...a, rings: rings(a.boundary) })), [areas]);
  const bounds = useMemo(() => {
    const pts = allRings.flatMap((a) => a.rings[0]);
    return pts.length ? L.latLngBounds(pts) : L.latLngBounds([[41.2, 69.2], [41.4, 69.4]]);
  }, [allRings]);
  const tiles = base === "satellite" ? SATELLITE : STREETS;
  const glow = base === "satellite" ? "#2DD4BF" : "#0F766E";

  return (
    <div className="relative overflow-hidden rounded-card ring-1 ring-slate-200" style={{ height }}>
      <MapContainer bounds={bounds.pad(padding)} zoomSnap={0.25} zoomDelta={0.5} scrollWheelZoom={interactive} dragging={interactive}
        zoomControl={interactive} doubleClickZoom={interactive} attributionControl style={{ height: "100%", width: "100%" }}>
        <TileLayer key={base} url={tiles.url} attribution={tiles.attribution} maxZoom={19} />
        <FitTo bounds={bounds} padding={padding} />
        {dimOutside && allRings.length > 0 && (
          <Polygon positions={[WORLD, ...allRings.map((a) => a.rings[0])]} interactive={false}
            pathOptions={{ stroke: false, fillColor: "#020617", fillOpacity: base === "satellite" ? 0.55 : 0.35 }} />
        )}
        {allRings.map((a) => (
          <Polygon key={`fill-${a.key}`} positions={a.rings}
            eventHandlers={a.onClick ? { click: a.onClick } : undefined}
            pathOptions={{ stroke: false, fillColor: a.fill ?? glow, fillOpacity: a.fill ? 0.45 : 0.04 }}>
            {a.label && <Tooltip sticky className="zone-tip">{a.label}</Tooltip>}
          </Polygon>
        ))}
        {allRings.map((a) => (
          <Polyline key={`halo-${a.key}`} positions={a.rings[0]} interactive={false}
            pathOptions={{ color: glow, weight: 14, opacity: 0.25, lineJoin: "round", className: "mahalla-glow" }} />
        ))}
        {allRings.map((a) => (
          <Polyline key={`line-${a.key}`} positions={a.rings[0]} interactive={false}
            pathOptions={{ color: base === "satellite" ? "#CCFBF1" : glow, weight: 3.5, opacity: 1, lineJoin: "round" }} />
        ))}
        {dots.map((d) => (
          <CircleMarker key={d.key} center={[d.lat, d.lon]} radius={d.zone === "red" ? 7 : 5.5}
            eventHandlers={d.onClick ? { click: d.onClick } : undefined}
            pathOptions={{ color: "#ffffff", weight: 1.5, fillColor: ZONE_COLOR[d.zone], fillOpacity: 1 }}>
            <Tooltip className="zone-tip" direction="top" offset={[0, -6]}>{d.label} · {ZONE_LABEL[d.zone]}</Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>

      <div className="absolute right-3 top-3 z-[500] flex overflow-hidden rounded-lg bg-white/95 text-xs font-medium shadow-pop ring-1 ring-slate-200">
        {(["satellite", "streets"] as const).map((b) => (
          <button key={b} onClick={() => setBase(b)} aria-pressed={base === b}
            className={`px-3 py-1.5 ${base === b ? "bg-brand-700 text-white" : "text-slate-700 hover:bg-slate-50"}`}>
            {b === "satellite" ? "Sun'iy yo'ldosh" : "Ko'chalar"}
          </button>
        ))}
      </div>
      {legend && dots.length > 0 && (
        <div className="absolute bottom-6 left-3 z-[500] flex gap-3 rounded-lg bg-white/95 px-3 py-1.5 text-xs shadow-pop ring-1 ring-slate-200">
          {(["red", "yellow", "green"] as Zone[]).map((z) => (
            <span key={z} className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full ring-2 ring-white" style={{ background: ZONE_COLOR[z] }} />
              {ZONE_LABEL[z]} {dots.filter((d) => d.zone === z).length}
            </span>
          ))}
        </div>
      )}
      {overlay}
    </div>
  );
}

/** Circle-marker map for the country / region levels of the admin drill-down (no boundary polygons there). */
export function CircleMap({ nodes, height = 420, onSelect }: {
  nodes: { id: number; name: string; lat: number; lon: number; total?: number; red_share?: number; accessible: boolean }[];
  height?: number;
  onSelect: (id: number) => void;
}) {
  const bounds = useMemo(() => L.latLngBounds(nodes.map((n) => [n.lat, n.lon] as LatLng)), [nodes]);
  const maxTotal = Math.max(1, ...nodes.map((n) => n.total ?? 0));
  return (
    <div className="overflow-hidden rounded-card ring-1 ring-slate-200" style={{ height }}>
      <MapContainer bounds={bounds.pad(0.3)} scrollWheelZoom={false} style={{ height: "100%", width: "100%" }}>
        <TileLayer url={STREETS.url} attribution={STREETS.attribution} />
        <FitTo bounds={bounds} padding={nodes.length > 1 ? 0.3 : 2} />
        {nodes.map((n) => (
          <CircleMarker key={n.id} center={[n.lat, n.lon]}
            radius={n.accessible ? 10 + 22 * Math.sqrt((n.total ?? 0) / maxTotal) : 7}
            eventHandlers={n.accessible ? { click: () => onSelect(n.id) } : undefined}
            pathOptions={n.accessible && (n.total ?? 0) > 0
              ? { color: "#0F766E", weight: 2, fillColor: shareColor(n.red_share ?? 0), fillOpacity: 0.75 }
              : n.accessible
              ? { color: "#64748b", weight: 1.5, fillColor: "#e2e8f0", fillOpacity: 0.8 }
              : { color: "#94a3b8", weight: 1, fillColor: "#cbd5e1", fillOpacity: 0.5, dashArray: "3 3" }}>
            <Tooltip className="zone-tip">
              <b>{n.name}</b><br />
              {!n.accessible ? "Sizning hududingizga kirmaydi" : (n.total ?? 0) === 0 ? "Ma'lumot yo'q (demo poliklinika yo'q)" : `Faol: ${n.total} · Qizil ulushi ${Math.round((n.red_share ?? 0) * 100)}%`}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}

/** Red-share colour scale (risk only): green -> amber -> red. */
export function shareColor(share: number): string {
  if (share >= 0.12) return "#DC2626";
  if (share >= 0.06) return "#F97316";
  if (share >= 0.02) return "#F59E0B";
  return "#16A34A";
}
