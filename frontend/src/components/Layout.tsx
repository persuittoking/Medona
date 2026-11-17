import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Summary } from "../api/types";
import { ROLE_LABEL } from "../i18n/uz";
import { useAuth } from "../lib/auth";
import { SyntheticBadge } from "./ui";

export function Layout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const { data: summary } = useQuery({
    queryKey: ["summary", null],
    queryFn: () => api<Summary>("/api/dashboard/summary"),
    refetchInterval: 15000,
    enabled: !!user,
  });
  if (!user) return null;
  const links = [
    { to: "/dashboard", label: "Bosh sahifa" },
    { to: "/patients", label: "Bemorlar" },
    ...(user.role !== "nurse" ? [{ to: "/alerts", label: "Ogohlantirishlar", badge: summary?.open_alerts }] : []),
    ...(user.role === "admin" ? [{ to: "/analytics", label: "Model" }, { to: "/audit", label: "Audit" }] : []),
    { to: "/about", label: "Tizim haqida" },
  ];
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-[1000] border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2">
          <button className="flex items-center gap-2" onClick={() => nav("/dashboard")}>
            <img src="/favicon.svg" alt="" className="h-7 w-7" />
            <span className="text-lg font-bold text-brand-800">OnaRadar</span>
          </button>
          <SyntheticBadge />
          <nav className="order-last flex w-full gap-1 overflow-x-auto text-sm md:order-none md:w-auto">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-lg px-3 py-1.5 ${isActive ? "bg-brand-50 font-semibold text-brand-800" : "text-slate-600 hover:bg-slate-100"}`
                }
              >
                {l.label}
                {"badge" in l && l.badge ? (
                  <span className="ml-1.5 rounded-full bg-zred px-1.5 text-xs font-bold text-white">{l.badge}</span>
                ) : null}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <div className="text-right leading-tight">
              <div className="font-medium">{user.username}</div>
              <div className="text-xs text-slate-500">
                {ROLE_LABEL[user.role]} · {user.district_name ?? user.region_name}
              </div>
            </div>
            <button className="btn-ghost px-3 py-1.5" onClick={() => { logout(); nav("/login"); }}>
              Chiqish
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-5">
        <Outlet />
      </main>
    </div>
  );
}
