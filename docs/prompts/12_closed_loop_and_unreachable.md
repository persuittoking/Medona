# Task 12: Proof of care (closed loop) + unreachable-patient workflow

Read CLAUDE.md first. Tasks 07-11 are done: EXTEND, do not rewrite (tenancy.py, services/alerts.py, the alert chain,
visit_intensity). Do NOT touch .env or *.db. Do NOT git push. No PII in anything new; all UI text in Uzbek;
demo data stays labelled synthetic.

## Why (technical mentor feedback)
A nurse or doctor can press "accept" without seeing the patient. The system must trust measurements and
independent signals, not clicks. It must also handle patients who cannot be reached.

## Part A: Closed-loop closure
- Acknowledging an alert records the acknowledgement and stops escalation of the CURRENT step only. It does NOT close it.
- An alert can be resolved only if a NEW Visit (or NewbornCheck for children) for the same subject was saved after
  the alert's created_at and contains the measured fields relevant to the alert. Config map in thresholds.py
  (e.g. BP rules R01/R02/P01 -> systolic+diastolic; Hb rules -> hemoglobin_g_l; infant rules -> temperature/resp_rate/weight).
  Otherwise POST resolve returns 409: "Yopish uchun yangi o'lchov kerak".
- Resolution needs structured fields: action codes (existing catalog) + outcome (yaxshilandi / o'zgarishsiz / yo'llandi).

## Part B: Outcome check
- If the first assessment after resolution is still red or worse, reopen the alert automatically (event "reopened", audit).
- If an alert was acknowledged but no new measurement arrives within the SLA, escalate again (reuse run_escalations).

## Part C: Two-person rule for RED
- A specialist's resolve puts a red alert in status "pending_confirmation"; a DIFFERENT user (role department_head or doctor)
  must confirm closure. The same user cannot do both. Audit both steps.

## Part D: Unreachable-patient workflow (contact attempts)
- New table ContactAttempt: alert_id, user_id, attempted_at, channel (uyga borildi / telefon / Telegram / mahalla vakili orqali),
  result (aloqa bo'ldi / oila ruxsat bermadi / bemor boshqa joyda / topilmadi / telefon o'chiq), note (free text, no PII warning shown).
- Nurse or doctor logs each attempt on the alert card ("Aloqa urinishi qo'shish").
- Rules (thresholds.py): 3 failed attempts across at least 2 different days, or a first "oila ruxsat bermadi", sets the alert
  status to "unreachable" (still ACTIVE, never silently closed) and escalates to the next role with a clear reason.
- "Oila ruxsat bermadi": show a counselling checklist (explain danger signs, involve the mahalla women's activist and
  mahalla leader, offer a home visit at another time) and require recording an informed refusal note. The alert keeps
  a retry schedule (re-appears every 24 h for RED, 72 h for YELLOW) until a measurement is entered.
- "Bemor boshqa joyda": prompt to enter or request the result via the existing external-entry feature
  (responsibility follows the mahalla); if she moved permanently, allow transferring her to the new mahalla's
  polyclinic (reuse assign_patient_mahalla; audit-log both polyclinics).
- Admin views: show only AGGREGATE counts of unreachable red alerts per polyclinic (no patient data).

## Part E: Plausibility signals (simple statistics, no ML needed)
- Per user over the last 30 days: share of identical BP values, terminal-digit bias (mostly 0/5), near-zero variation,
  visit form open-to-save time under N seconds (client sends opened_at), many visits saved in the same minute.
- Store flags per user and visit with reason codes. Show them ONLY to department_head on a new page "Sifat nazorati":
  counts and patient codes only, labelled "signal, ayblov emas".
- Department head dashboard tile: "Qabul qilingan, lekin o'lchovsiz" rate and "Aloqa o'rnatilmagan qizil" count.

## Tests
closure blocked without a measurement; closure allowed with one; reopen on still-red; same-user confirm blocked;
unreachable status after 3 attempts over 2 days; refusal path; admin sees counts only; plausibility flags; tenant isolation.

## Finish
Run ruff check backend, pytest -q, frontend typecheck, lint, build. Update docs/DEMO_SCRIPT.md (add a 1-minute
"proof of care" scene). Make sure a department_head demo login exists. ONE local commit
"Proof of care: closed loop, unreachable workflow, quality signals", do NOT push. Print a checklist with the
result of each part.
