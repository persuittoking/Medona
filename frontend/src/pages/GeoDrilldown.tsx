import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Crumb, GeoLevel, GeoNode, GeoPolyclinic, Subject, SubjectCounts } from "../api/types";
import { SubjectSwitch } from "../components/SubjectSwitch";
import { CircleMap, MahallaMap, shareColor } from "../components/MahallaMap";
import { ErrorBox, Skeleton } from "../components/ui";
import { fmtPct } from "../lib/format";
import { useSubject } from "../lib/subject";

const TOTAL_LABEL: Record<Subject, string> = { pregnancy: "Faol homiladorlar", child: "Kuzatuvdagi bolalar", all: "Jami kuzatuvda" };

function Header({ subject, onChange, counts }: { subject: Subject; onChange: (s: Subject) => void; counts?: SubjectCounts }) {
  return <SubjectSwitch value={subject} onChange={onChange} counts={counts} />;
}
import { Kpi } from "./Dashboard";

const CHILD_ROUTE: Record<string, string> = { country: "region", region: "district", district: "polyclinic" };
const CHILD_TITLE: Record<string, string> = { country: "Viloyatlar", region: "Tumanlar", district: "Poliklinikalar" };

function crumbHref(c: Crumb): string {
  return c.level === "country" ? "/geo" : `/geo/${c.level}/${c.id}`;
}

function Breadcrumb({ items, current }: { items: Crumb[]; current: string }) {
  if (!items.length) return <div className="eyebrow">Hududlar bo'yicha umumiy ko'rinish</div>;
  return (
    <nav className="flex flex-wrap items-center gap-1 text-sm" aria-label="breadcrumb">
      {items.map((c) => (
        <span key={c.level + (c.id ?? "")} className="flex items-center gap-1">
          <Link to={crumbHref(c)} className="text-brand-700 hover:underline">{c.name}</Link>
          <span className="text-slate-300">›</span>
        </span>
      ))}
      <span className="font-medium text-slate-900">{current}</span>
    </nav>
  );
}

function AggNote() {
  return (
    <p className="text-xs text-slate-500">
      Faqat umumlashtirilgan sonlar ko'rsatiladi — ism, bemor kodi va uy manzillari boshqaruv darajasida ko'rinmaydi.
    </p>
  );
}

function ChildrenTable({ level, nodes }: { level: string; nodes: GeoNode[] }) {
  const nav = useNavigate();
  return (
    <div className="card overflow-x-auto p-0 md:p-0">
      <table className="w-full min-w-[560px]">
        <thead className="border-b border-slate-100"><tr>
          <th className="th">{CHILD_TITLE[level]}</th><th className="th text-right">Faol</th><th className="th text-right">Qizil</th>
          <th className="th text-right">Sariq</th><th className="th text-right">Yashil</th><th className="th">Qizil ulushi</th>
          <th className="th text-right">Ochiq ogohl.</th>
        </tr></thead>
        <tbody>
          {nodes.map((n) => (
            <tr key={n.id} onClick={() => n.accessible && nav(`/geo/${CHILD_ROUTE[level]}/${n.id}`)}
              className={`border-b border-slate-100 last:border-0 ${n.accessible ? "cursor-pointer hover:bg-slate-50" : "text-slate-400"}`}>
              <td className="td font-medium">{n.name}{n.code && <span className="ml-2 font-mono text-xs text-slate-500">{n.code}</span>}</td>
              {n.accessible ? (
                <>
                  <td className="td text-right tabular-nums">{n.total}</td>
                  <td className="td text-right tabular-nums text-zred">{n.red}</td>
                  <td className="td text-right tabular-nums text-amber-600">{n.yellow}</td>
                  <td className="td text-right tabular-nums text-zgreen">{n.green}</td>
                  <td className="td">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-100">
                        <div className="h-full rounded-full" style={{ width: `${Math.min(100, (n.red_share ?? 0) * 400)}%`, background: shareColor(n.red_share ?? 0) }} />
                      </div>
                      <span className="text-xs tabular-nums">{fmtPct(n.red_share)}</span>
                    </div>
                  </td>
                  <td className="td text-right tabular-nums">{n.open_alerts}</td>
                </>
              ) : <td className="td text-xs" colSpan={6}>Sizning hududingizga kirmaydi</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LevelView({ path, subject, setSubject }: { path: string; subject: Subject; setSubject: (s: Subject) => void }) {
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["geo", path, subject], queryFn: () => api<GeoLevel>(`${path}?subject=${subject}`) });
  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <Skeleton className="h-[500px]" />;
  const d = q.data;
  const go = (id: number) => nav(`/geo/${CHILD_ROUTE[d.level]}/${id}`);
  const withTerritory = d.children.filter((c) => c.territory?.length);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Breadcrumb items={d.breadcrumb ?? []} current={d.name} />
          <h1 className="mt-2">{d.name}</h1>
        </div>
        <Header subject={subject} onChange={setSubject} counts={d.subject_counts} />
      </div>
      {d.level === "district" && withTerritory.length ? (
        <MahallaMap height={460} dimOutside={false} legend={false}
          areas={withTerritory.flatMap((c) => c.territory!.map((t, i) => ({
            key: `${c.id}-${i}`, boundary: t.boundary, fill: shareColor(c.red_share ?? 0),
            label: `${c.name}: qizil ulushi ${fmtPct(c.red_share)}`, onClick: () => go(c.id),
          })))} />
      ) : (
        <CircleMap nodes={d.children} onSelect={go} height={460} />
      )}
      <ChildrenTable level={d.level} nodes={d.children} />
      <AggNote />
    </div>
  );
}

function PolyclinicView({ id, subject, setSubject }: { id: string; subject: Subject; setSubject: (s: Subject) => void }) {
  const q = useQuery({ queryKey: ["geo-pc", id, subject], queryFn: () => api<GeoPolyclinic>(`/api/geo/polyclinics/${id}?subject=${subject}`) });
  if (q.error) return <ErrorBox error={q.error} />;
  if (!q.data) return <Skeleton className="h-[500px]" />;
  const d = q.data;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Breadcrumb items={d.breadcrumb} current={d.code} />
          <h1 className="mt-2">{d.name}</h1>
          <p className="mt-1 text-sm text-slate-500">Xizmat hududi: {d.territory.map((t) => t.name).join(", ")}</p>
        </div>
        <Header subject={subject} onChange={setSubject} counts={d.subject_counts} />
      </div>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-6">
        <Kpi label={TOTAL_LABEL[subject]} value={d.total} />
        <Kpi label="Qizil" value={d.red} tone="text-zred" />
        <Kpi label="Sariq" value={d.yellow} tone="text-amber-600" />
        <Kpi label="Yashil" value={d.green} tone="text-zgreen" />
        <Kpi label="Qizil ulushi" value={fmtPct(d.red_share)} />
        <Kpi label="Ochiq ogohlantirishlar" value={d.open_alerts} />
      </div>
      <MahallaMap height={460} legend={false}
        areas={d.territory.map((t, i) => ({ key: String(i), boundary: t.boundary, label: t.name }))} />
      <AggNote />
    </div>
  );
}

export default function GeoDrilldown() {
  const { level, id } = useParams();
  const [subject, setSubject] = useSubject();
  if (level === "polyclinic" && id) return <PolyclinicView id={id} subject={subject} setSubject={setSubject} />;
  const path = level === "region" ? `/api/geo/regions/${id}` : level === "district" ? `/api/geo/districts/${id}` : "/api/geo/country";
  return <LevelView key={path} path={path} subject={subject} setSubject={setSubject} />;
}
