import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { SyntheticBadge } from "../components/ui";
import { DEMO_USERS, DISCLAIMER, ROLE_LABEL } from "../i18n/uz";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function go(u: string, p: string) {
    setBusy(true);
    setError(null);
    try {
      const user = await login(u, p);
      nav(user.role === "nurse" ? "/patients" : "/dashboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kirishda xatolik");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-white px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <img src="/favicon.svg" alt="" className="mx-auto h-14 w-14" />
          <h1 className="mt-3 text-2xl font-bold text-brand-800">OnaRadar</h1>
          <p className="mt-1 text-sm text-slate-600">Homilador ayollar va chaqaloqlar uchun erta ogohlantirish tizimi</p>
          <div className="mt-2"><SyntheticBadge /></div>
        </div>

        <form
          className="card space-y-3"
          onSubmit={(e) => { e.preventDefault(); go(username, password); }}
        >
          <div>
            <label className="label" htmlFor="u">Login</label>
            <input id="u" className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="p">Parol</label>
            <input id="p" type="password" className="input" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <div className="rounded-lg bg-red-50 p-2 text-sm text-red-700">{error}</div>}
          <button className="btn-primary w-full" disabled={busy || !username || !password}>Kirish</button>
        </form>

        <div className="card mt-4">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Demo sifatida kirish</h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {DEMO_USERS.map((d) => (
              <button key={d.username} className="btn-ghost justify-start text-left" disabled={busy} onClick={() => go(d.username, "demo1234")}>
                <span>
                  <span className="block font-medium">{d.label}</span>
                  <span className="block text-xs text-slate-500">{ROLE_LABEL[d.role]}</span>
                </span>
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500">Barcha demo foydalanuvchilar paroli: <code>demo1234</code></p>
        </div>
        <p className="mt-4 text-center text-xs text-slate-500">{DISCLAIMER}</p>
      </div>
    </div>
  );
}
