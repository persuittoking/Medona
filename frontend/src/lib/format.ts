const MONTHS = ["yan", "fev", "mar", "apr", "may", "iyun", "iyul", "avg", "sen", "okt", "noy", "dek"];

/** Server datetimes are naive UTC; make them parseable as UTC. */
export function parseUtc(s: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");
}

export function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = s.length <= 10 ? new Date(s + "T00:00:00") : parseUtc(s);
  return `${d.getDate()}-${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

export function fmtDateTime(s: string | null | undefined): string {
  if (!s) return "—";
  const d = parseUtc(s);
  return `${d.getDate()}-${MONTHS[d.getMonth()]}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function fmtPct(p: number | null | undefined): string {
  return p == null ? "—" : `${Math.round(p * 100)}%`;
}

export function fmtWeeks(w: number): string {
  const weeks = Math.floor(w);
  const days = Math.round((w - weeks) * 7);
  return days ? `${weeks} hafta ${days} kun` : `${weeks} hafta`;
}

export function fmtMinutes(m: number | null | undefined): string {
  if (m == null) return "—";
  if (m < 60) return `${Math.round(m)} daq`;
  return `${Math.floor(m / 60)} soat ${Math.round(m % 60)} daq`;
}
