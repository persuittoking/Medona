import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AiSummary, AiSummaryPending } from "../api/types";
import { ErrorBox, Skeleton, SourceTag } from "./ui";

const POLL_MS = 3000;
const MAX_WAIT_MS = 60_000;

/** The backend generates the summary in the background (right after a visit is saved) and answers 202
 * "pending" until it is cached; we poll every 3 s for at most 60 s. */
export function AiSummaryPanel({ pregnancyId, newbornId }: { pregnancyId?: number; newbornId?: number }) {
  const qc = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const startedAt = useRef(Date.now());
  const path = newbornId != null ? `/api/llm/summary/child/${newbornId}` : `/api/llm/summary/${pregnancyId}`;
  const key = ["ai", path];
  useEffect(() => {
    startedAt.current = Date.now();
  }, [path]);
  const q = useQuery({
    queryKey: key,
    queryFn: () => api<AiSummary | AiSummaryPending>(path),
    staleTime: 60_000,
    refetchInterval: (query) =>
      query.state.data?.status === "pending" && Date.now() - startedAt.current < MAX_WAIT_MS ? POLL_MS : false,
  });

  async function regenerate() {
    setRefreshing(true);
    startedAt.current = Date.now();
    try {
      qc.setQueryData(key, await api<AiSummary | AiSummaryPending>(`${path}?refresh=true`));
    } finally {
      setRefreshing(false);
    }
  }

  const s = q.data?.status === "ready" ? q.data : undefined;
  const pending = q.data?.status === "pending";
  const timedOut = pending && Date.now() - startedAt.current >= MAX_WAIT_MS;
  return (
    <div className="card">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-semibold">AI xulosa {s && <SourceTag source={s.source} />}</h3>
        <button className="btn-ghost px-3 py-1 text-xs" onClick={regenerate} disabled={refreshing || q.isLoading}>
          {refreshing ? "Yaratilmoqda…" : "Qayta yaratish"}
        </button>
      </div>
      {/* While refetching (e.g. right after a new visit) never show the previous assessment's summary. */}
      {q.error ? <ErrorBox error={q.error} /> : timedOut ? (
        <p className="text-sm text-slate-600">AI xulosa hozircha tayyor emas. Birozdan so'ng "Qayta yaratish" tugmasini bosing.</p>
      ) : !s || refreshing || (q.isFetching && !pending) ? (
        <div className="space-y-2">
          <p className="text-xs text-slate-500">AI xulosa tayyorlanmoqda…</p>
          <Skeleton className="h-40" />
        </div>
      ) : (
        <div className="space-y-3 text-sm">
          {s.doctor_bullets_uz && s.doctor_bullets_uz.length > 0 && (
            <div className="rounded-lg bg-slate-50 p-2.5 ring-1 ring-slate-200">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Mutaxassis uchun qisqacha (3 band)</h4>
              <ol className="list-decimal space-y-0.5 pl-5">{s.doctor_bullets_uz.map((b, i) => <li key={i}>{b}</li>)}</ol>
            </div>
          )}
          <p className="leading-relaxed">{s.summary_uz}</p>
          {s.key_concerns.length > 0 && (
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Asosiy xavotirlar</h4>
              <ul className="list-disc space-y-0.5 pl-5">
                {s.key_concerns.map((c, i) => <li key={i}><span className="font-mono text-xs text-slate-400">{c.code}</span> {c.text_uz}</li>)}
              </ul>
            </div>
          )}
          {s.recommended_actions.length > 0 && (
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Tavsiya etilgan harakatlar (protokol katalogidan)</h4>
              <ul className="space-y-1">
                {s.recommended_actions.map((a) => (
                  <li key={a.code} className="flex gap-2"><span className="rounded bg-brand-50 px-1.5 font-mono text-xs leading-5 text-brand-800">{a.code}</span>{a.text_uz}</li>
                ))}
              </ul>
            </div>
          )}
          {s.questions_to_ask_patient_uz.length > 0 && (
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Bemordan so'rash kerak</h4>
              <ul className="list-disc space-y-0.5 pl-5">{s.questions_to_ask_patient_uz.map((x, i) => <li key={i}>{x}</li>)}</ul>
            </div>
          )}
          <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-900">{s.disclaimer_uz}</p>
        </div>
      )}
    </div>
  );
}
