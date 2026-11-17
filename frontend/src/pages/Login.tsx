import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { isAdmin, type Territory } from "../api/types";
import { MahallaMap } from "../components/MahallaMap";
import { SyntheticBadge } from "../components/ui";
import { DEMO_USERS, DISCLAIMER } from "../i18n/uz";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [polyclinic, setPolyclinic] = useState("PL-NUK-001");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const territories = useQuery({ queryKey: ["territories"], queryFn: () => api<Territory[]>("/api/public/territories") });

  // The map follows the polyclinic ID being typed (outline only — no patient data before login).
  const shown = useMemo(() => {
    const list = territories.data ?? [];
    return list.find((t) => t.code === polyclinic.trim().toUpperCase()) ?? list[0];
  }, [territories.data, polyclinic]);

  async function go(pc: string, u: string, p: string) {
    setBusy(true);
    setError(null);
    try {
      const user = await login(pc, u, p);
      nav(isAdmin(user.role) ? "/geo" : user.role === "nurse" ? "/map" : "/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kirishda xatolik");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,480px)_1fr]">
      <div className="flex flex-col justify-center px-6 py-10 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <div className="flex items-center gap-3">
            <img src="/favicon.svg" alt="" className="h-10 w-10" />
            <div>
              <div className="text-xl font-bold tracking-tight text-brand-800">OnaRadar</div>
              <div className="text-xs text-slate-500">Onalar va chaqaloqlar uchun erta ogohlantirish</div>
            </div>
          </div>
          <div className="mt-4"><SyntheticBadge /></div>

          <form className="mt-8 space-y-4" onSubmit={(e) => { e.preventDefault(); go(polyclinic, username, password); }}>
            <div>
              <label className="label" htmlFor="pc">Poliklinika ID</label>
              <input id="pc" className="input font-mono uppercase" placeholder="PL-NUK-001" value={polyclinic}
                onChange={(e) => setPolyclinic(e.target.value)} />
              <p className="mt-1 text-xs text-slate-500">Tuman va viloyat adminlari uchun bo'sh qoldiring.</p>
            </div>
            <div>
              <label className="label" htmlFor="u">Login</label>
              <input id="u" className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="p">Parol</label>
              <input id="p" type="password" className="input" autoComplete="current-password" value={password}
                onChange={(e) => setPassword(e.target.value)} />
            </div>
            {error && <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-200">{error}</div>}
            <button className="btn-primary w-full" disabled={busy || !username || !password}>Kirish</button>
          </form>

          <div className="mt-8">
            <div className="eyebrow mb-2">Demo sifatida kirish · parol demo1234</div>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_USERS.map((d) => (
                <button key={d.polyclinic + d.username} className="btn-ghost h-auto flex-col items-start py-2 text-left" disabled={busy}
                  onMouseEnter={() => d.polyclinic && setPolyclinic(d.polyclinic)}
                  onClick={() => go(d.polyclinic, d.username, "demo1234")}>
                  <span className="text-sm font-medium">{d.label}</span>
                  <span className="font-mono text-[11px] text-slate-500">{d.polyclinic ? `${d.polyclinic} / ${d.username}` : d.username}</span>
                </button>
              ))}
            </div>
          </div>
          <p className="mt-8 text-xs leading-relaxed text-slate-500">{DISCLAIMER}</p>
        </div>
      </div>

      <div className="relative hidden bg-slate-900 lg:block">
        {shown && (
          <MahallaMap height="100vh" padding={0.35} interactive={false} legend={false}
            areas={shown.mahallas.map((m, i) => ({ key: `${shown.code}-${i}`, boundary: m.boundary }))}
            overlay={
              <div className="absolute bottom-8 left-8 z-[500] max-w-sm rounded-card bg-white/95 p-4 shadow-pop ring-1 ring-slate-200">
                <div className="eyebrow">Xizmat hududi</div>
                <div className="mt-1 font-semibold text-slate-900">{shown.name}</div>
                <div className="text-sm text-slate-600">{shown.mahallas.map((m) => m.name).join(", ")} · {shown.district}</div>
                <div className="mt-1 font-mono text-xs text-slate-500">{shown.code}</div>
              </div>
            } />
        )}
      </div>
    </div>
  );
}
