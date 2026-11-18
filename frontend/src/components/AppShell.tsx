import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { isAdmin, type Summary } from "../api/types";
import { ROLE_LABEL } from "../i18n/uz";
import { useAuth } from "../lib/auth";
import { SyntheticBadge } from "./ui";

type Item = { to: string; label: string; icon: string; badge?: number };

// Minimal inline icons (stroke paths) so we add no icon dependency.
const ICONS: Record<string, string> = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  map: "M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zm0 0v14m6-12v14",
  users: "M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM21 19v-1a4 4 0 0 0-3-3.87M15 3.13a3.5 3.5 0 0 1 0 6.75",
  bell: "M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
  chart: "M4 20V10m6 10V4m6 16v-7m4 7H2",
  shield: "M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0-13h.01M11 12h1v5h1",
  globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18",
};

function Icon({ name, className = "h-5 w-5" }: { name: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={ICONS[name]} />
    </svg>
  );
}

export function AppShell() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const staff = !!user && !isAdmin(user.role);
  const { data: summary } = useQuery({
    queryKey: ["summary", "all"],
    queryFn: () => api<Summary>("/api/dashboard/summary?subject=all"),
    refetchInterval: 15000,
    enabled: staff,
  });
  if (!user) return null;

  const items: Item[] = staff
    ? [
        { to: "/dashboard", label: "Bosh sahifa", icon: "home" },
        { to: "/map", label: "Mahalla xaritasi", icon: "map" },
        { to: "/patients", label: "Bemorlar", icon: "users" },
        ...(user.role !== "nurse" ? [{ to: "/alerts", label: "Ogohlantirishlar", icon: "bell", badge: summary?.open_alerts }] : []),
        { to: "/about", label: "Tizim haqida", icon: "info" },
      ]
    : [
        { to: "/geo", label: "Hududlar", icon: "globe" },
        { to: "/analytics", label: "Model", icon: "chart" },
        { to: "/audit", label: "Audit", icon: "shield" },
        { to: "/about", label: "Tizim haqida", icon: "info" },
      ];
  const scope = staff ? `${user.polyclinic_code} · ${user.district_name}` : (user.district_name ?? user.region_name);

  return (
    <div className="min-h-screen md:pl-64">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-[1100] hidden w-64 flex-col border-r border-slate-200 bg-white md:flex">
        <button className="flex items-center gap-2 px-6 py-5" onClick={() => nav("/")}>
          <img src="/favicon.svg" alt="" className="h-8 w-8" />
          <span className="text-lg font-bold tracking-tight text-brand-800">OnaRadar</span>
        </button>
        <div className="mx-4 mb-4 rounded-lg bg-slate-50 px-4 py-2 ring-1 ring-slate-200">
          <div className="eyebrow">{staff ? "Poliklinika" : "Hudud"}</div>
          <div className="mt-0.5 text-sm font-medium leading-snug text-slate-800">{staff ? user.polyclinic_name : scope}</div>
          {staff && <div className="mt-0.5 font-mono text-xs text-slate-500">{scope}</div>}
        </div>
        <nav className="flex-1 space-y-1 px-4">
          {items.map((i) => (
            <NavLink key={i.to} to={i.to}
              className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${isActive ? "bg-brand-50 text-brand-800" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"}`}>
              <Icon name={i.icon} />
              <span className="flex-1">{i.label}</span>
              {i.badge ? <span className="rounded-full bg-zred px-2 text-xs font-semibold text-white">{i.badge}</span> : null}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-4">
          <div className="text-sm font-medium">{user.full_name}</div>
          <div className="text-xs text-slate-500">{ROLE_LABEL[user.role]}</div>
          <button className="btn-ghost btn-sm mt-3 w-full" onClick={() => { logout(); nav("/login"); }}>Chiqish</button>
        </div>
      </aside>

      {/* Top bar (all sizes) */}
      <header className="sticky top-0 z-[1000] flex h-14 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur md:px-8">
        <img src="/favicon.svg" alt="" className="h-7 w-7 md:hidden" />
        <div className="min-w-0 flex-1 truncate text-sm text-slate-600 md:hidden">{staff ? user.polyclinic_code : scope}</div>
        <div className="hidden flex-1 text-sm text-slate-500 md:block">{ROLE_LABEL[user.role]} · {scope}</div>
        <SyntheticBadge />
        <button className="btn-ghost btn-sm md:hidden" onClick={() => { logout(); nav("/login"); }}>Chiqish</button>
      </header>

      <main className="mx-auto max-w-7xl px-4 pb-24 pt-6 md:px-8 md:pb-8">
        <Outlet />
      </main>

      {/* Mobile bottom tab bar */}
      <nav className="fixed inset-x-0 bottom-0 z-[1100] grid border-t border-slate-200 bg-white md:hidden"
        style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
        {items.map((i) => (
          <NavLink key={i.to} to={i.to}
            className={({ isActive }) => `relative flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium ${isActive ? "text-brand-700" : "text-slate-500"}`}>
            <Icon name={i.icon} />
            <span className="truncate">{i.label.split(" ")[0]}</span>
            {i.badge ? <span className="absolute right-1/4 top-1 rounded-full bg-zred px-1.5 text-[10px] font-semibold text-white">{i.badge}</span> : null}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
