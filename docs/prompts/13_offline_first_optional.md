# Task 13 (OPTIONAL, only if time allows): Works with weak or no internet

Read CLAUDE.md first. EXTEND, do not rewrite. No .env/*.db changes. Do NOT git push.

## Part A: Offline-first visit entry (PWA)
- Make the frontend an installable PWA (manifest + service worker; keep dependencies minimal).
- The visit and child-check forms work offline: save to IndexedDB with a client id, show "Oflayn saqlandi" and
  a pending count, sync automatically when the connection returns, idempotent on the server (client_id unique),
  conflicts resolved by server timestamp. Scoring happens on sync; the nurse sees the zone after sync.
- A visible status chip: Onlayn / Oflayn / Sinxronlanmoqda.

## Part B: Paper fallback
- A printable A5 "Ko'rik varaqasi" (patient code, fields in the same order as the visit form, a QR with the code)
  and a "Varaqadan kiritish" screen for a clerk at the polyclinic to enter paper results later,
  marked "qog'ozdan kiritilgan" and the entry date.

## Part C: Low-bandwidth alerts
- Keep Telegram messages short (already de-identified). Add an SMS adapter interface (stub only, logs to OUTBOX)
  for a future gateway; document it.

## Tests + finish
Backend idempotent-sync tests; frontend typecheck, lint, build; docs update; ONE local commit, do NOT push.
