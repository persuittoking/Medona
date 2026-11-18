# Task 07 — Smart alerts: predictive trends, 3-bullet doctor summary, escalation to the department head

Read CLAUDE.md first. Plan, then do each part, test, commit, and push. Never print or commit secret values.
Keep every principle in CLAUDE.md (decision support not diagnosis, explainability, rules override ML,
privacy: the LLM gets only the de-identified allow-list payload, all thresholds in `thresholds.py`).
Extend what exists — do not write a second engine, summary or scheduler.

What exists now (read it first):
- `backend/app/risk/trends.py` — T01–T05 compare ONLY the current visit with the previous one.
- `backend/app/risk/engine.py`, `services/scoring.py` — zone = max(rules, trends, ML); alerts on worsening.
- `backend/app/llm/summary.py` + `services/ai_summary.py` — `LlmOutput` (summary_uz, key_concerns,
  recommended_action_codes, questions_to_ask_patient_uz), Gemini → fallback model → plain retry → "Shablon".
- `backend/app/services/alerts.py` + `scheduler.py` — SLA escalation: specialist → polyclinic doctor →
  district admin; `config.py` SLA settings and DEMO_SLA_RED_MINUTES; the demo "end SLA now" button.
- Frontend: `pages/Alerts.tsx`, `components/AiSummaryPanel.tsx`, `components/RiskExplain.tsx`, `pages/PatientCard.tsx`.

## Part A — Predictive trend alerts (last 2–3 checkups)
Goal: flag a patient whose values are moving steadily in a dangerous direction, even when no single value
has crossed a red threshold yet.
1. In `trends.py` add multi-visit trend rules over the last 3 visits (2 intervals) of the same pregnancy,
   using the slope per week (value change ÷ weeks between visits, so uneven visit spacing is handled):
   - P01 systolic or diastolic rising at every step and projected (linear, next 2 weeks) to reach the
     hypertension threshold already in `thresholds.py` → YELLOW; if it is also ≥ 130/85 now → RED.
   - P02 hemoglobin falling at every step and projected below the anaemia threshold → YELLOW.
   - P03 weight gain per week above the limit at both steps (oedema / pre-eclampsia sign) → YELLOW.
   - P04 fundal height falling further behind gestational weeks at each step (growth restriction) → YELLOW.
   - P05 ML probability rising at each step by a total ≥ TREND_ML_RISE → YELLOW.
   Two or more P-hits, or a P-hit together with any clinical yellow rule → RED (same rule as now).
   All new thresholds (min visits, projection horizon, per-week slopes) go into `thresholds.py` with a
   one-line source/rationale comment. With fewer than 3 visits fall back to the existing T-rules.
2. Each hit carries `kind: "trend"`, the values it used (e.g. `[118, 126, 134]`, dates) and plain Uzbek
   text: "Sistolik bosim 3 ko'rikda ketma-ket oshmoqda: 118 → 126 → 134; shu sur'atda 2 haftada 140 dan oshishi
   mumkin". Never call it a diagnosis.
3. Frontend: in `RiskExplain.tsx` and the patient card, show trend hits with a small sparkline of the 3
   values (Recharts) and an arrow ↗/↘. In `Alerts.tsx` mark trend-driven alerts with a badge
   "Prognoz: yomonlashish trendi".
4. Seed: make 2–3 demo patients per polyclinic have a clear 3-visit rising-BP or falling-Hb trend that is
   still below the static thresholds on the last visit (so the demo shows "red/yellow by trend only").
   Keep DEMO1–DEMO4 as they are.
5. Tests: rising 3-visit BP → P01; uneven spacing; only 2 visits → old T-rules only; zig-zag values →
   no P01; rules still override ML; the patient text contains the 3 values.

## Part B — Automated 3-bullet doctor summary inside the alert
Goal: the OvaBMU specialist sees the essence in the alert itself without opening PDFs or the full card.
1. Extend `LlmOutput` with `doctor_bullets_uz: list[str]` — exactly 3 short bullets (≤ 160 chars each):
   (1) why this patient is flagged now (zone + the main rule/trend), (2) the key numbers and their trend
   with dates, (3) the recommended next step from the existing action catalog. Validate: exactly 3,
   non-empty, no PII, no diagnosis words (reuse the existing safety checks; add "tashxis" / "diagnoz"
   style words to the deny list if not there). The template "Shablon" fallback must also produce 3 bullets
   from the rule/trend hits, so it works offline.
2. Update the Gemini prompt + JSON schema; keep the de-identified payload (add the last-3-visit values the
   trends use, nothing personal). Bump the cache key/version so old cached summaries are regenerated.
3. `alert_out` returns `summary_bullets` (from the cached summary for that risk assessment; if not ready
   yet: `null` + `summary_status: "pending"`). The alert list and the alert detail show the 3 bullets with
   a source badge "AI (Gemini)" / "Shablon" and the line "Yakuniy qaror shifokorga tegishli".
   While pending, show a skeleton and poll (reuse the existing polling).
4. The Telegram message for a red alert includes the 3 bullets (still de-identified: patient code only).
5. Tests (mocked Gemini): 3 bullets parsed; wrong count → retry → template; template gives 3 bullets;
   no name/JShShIR/phone in the payload or bullets.

## Part C — Escalation timer to the department head
Goal: a RED alert not acknowledged by a specialist within the set time goes automatically to the
department head (OvaBMU bo'lim mudiri).
1. New polyclinic role `department_head` (UI: "Bo'lim mudiri (OvaBMU)"). Add it to POLYCLINIC_ROLES with
   the same tenant isolation as specialists. Seed one per polyclinic (username `department_head`, same demo
   password as the others) and show it on the login page's demo user list.
2. Escalation chain for RED: specialist (level 0) → department head (level 1, after
   `SLA_RED_MINUTES` / DEMO value) → district admin notified as a count only (level 2, after another SLA
   period). YELLOW keeps its current chain and hours. Put the chain in one place in `services/alerts.py`.
3. Alert UI: a live countdown "Javob berish uchun qoldi: 08:42" on every open red alert; when it hits zero,
   it shows "Bo'lim mudiriga yuborildi" after the next scheduler run (≤ 30 s). Show the escalation history
   (who it was assigned to and when) in the alert detail. Acknowledge stops the timer.
4. The department head sees a "Kechikkan ogohlantirishlar" list (escalated to them) at the top of Alerts and
   can acknowledge / reassign to a specialist. Every step goes to the audit log; Telegram notifies the new
   assignee.
5. Settings: `SLA_RED_MINUTES` (default 120) and `DEMO_SLA_RED_MINUTES` keep working; the department head
   (and admins) see the current value read-only on the "Tizim haqida" page.
6. Tests: overdue red → department head; acknowledged before the deadline → no escalation; second
   period → district admin as aggregate only; tenant isolation for the new role; the demo "end SLA now"
   button escalates to the department head.

## Part D — Check, commit, push
1. ruff, all backend tests, frontend typecheck/lint/build.
2. Demo flow: a trend-only demo patient shows a red/yellow zone with the sparkline; DEMO1 → new visit
   152/98, protein +2, severe headache → RED → alert shows 3 bullets → press "Demo: SLA muddatini hozir
   tugatish" → within 30 s it is assigned to the department head → log in as department_head → acknowledge.
   Then reset the demo data.
3. Update docs/CLINICAL_RULES.md (P01–P05) and docs/DEMO_SCRIPT.md. Commit and push. Print the ✅/❌ checklist.
