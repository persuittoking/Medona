# Task 08 — Children under 1 year: the same zone system for infants, and a "Homiladorlar / Bolalar" switch

Read CLAUDE.md first. Plan, then do each part, test, commit, and push. Do Task 07 first (it must be
committed): reuse its trend helpers, 3-bullet summary and escalation chain — do not duplicate them.

What exists now: `Newborn` + `NewbornCheck` models and `risk/newborn.py` (N01–N13, WHO IMCI young-infant
danger signs, neonatal period only). Alerts (`Alert.pregnancy_id`) and the map/list/card are built
around pregnancies.

## Part A — Data model: a child is followed until 12 months
1. Rename the concept in the UI to "Bola" (0–12 oy); keep the `newborns` table (add a `display` alias in
   code if helpful) — no destructive migration. Add to `Newborn`: `sex`, `status`
   (`active` until the 1st birthday, then `graduated`; `deceased`/`moved` possible), `current_risk_score`,
   `mahalla_id`/`polyclinic_id` taken from the mother's patient record (tenant key stays the mother's
   polyclinic), and a pseudonymous `code` (e.g. `B-` + mother's code + `-1`).
2. `NewbornCheck` becomes an infant check: add `age_days` (computed), `length_cm`, `head_circ_cm`,
   `feeding` (`exclusive_breast` | `mixed` | `formula` | `complementary`), `vomiting_everything`,
   `diarrhoea_days`, `blood_in_stool`, `cough_days`, `lethargic`, `vaccines_due_overdue` (list of codes
   from the national schedule: BCG, HepB, OPV/IPV, Pentavalent, Rotavirus, PCV, MMR — only the names,
   dates computed from the birth date). Keep the old columns.
3. Seed: per mahalla, 15–25 children aged 0–12 months (synthetic, with 2–6 checks each, realistic weight
   gain curves with a few faltering and a few acute danger signs), linked to delivered mothers. Keep the
   newborn demo case (DEMO4).

## Part B — Infant risk engine (rules + trends), same zone logic
1. In `risk/infant.py` (or extend `newborn.py`), with thresholds in `thresholds.py` and a source comment
   (WHO IMCI 2–59 months / young infant, WHO growth standards):
   - RED danger signs: not able to feed/breastfeed, vomits everything, convulsions, lethargic/unconscious,
     fast breathing for age (≥60 under 2 months, ≥50 for 2–12 months), severe chest indrawing,
     temperature ≥ 38.0 (under 2 months) or < 35.5, blood in stool, diarrhoea ≥ 14 days.
   - YELLOW: weight-for-age below −2 SD (use the WHO WFA 0–12 months median/SD table for the child's sex,
     stored as a small constant table), overdue vaccine (> 30 days), cough ≥ 14 days, no check for more
     than the scheduled interval (monthly in the first year), not exclusively breastfed before 6 months.
   - Keep N01–N13 for the first 28 days.
   - Trends (Task 07 style, over the last 2–3 checks): weight-for-age z-score falling ≥ 0.67 between
     checks or weight not increasing for 2 consecutive checks ("o'sish to'xtashi") → YELLOW; with any
     other yellow sign → RED.
2. Zone = max(rules, trends). No ML for children (say so in the explanation: "Bolalar uchun faqat
   klinik qoidalar va trendlar").
3. Tests for every rule, the age-dependent breathing threshold, z-score from the table, and trends.

## Part C — Alerts for children
1. `Alert` gets `newborn_id` (nullable); exactly one of pregnancy_id / newborn_id is set. Tenancy
   (`tenancy.py` `get_alert`) handles both. The same escalation chain (specialist → department head → district
   count) and SLA apply; in the list the subject shows "Bola · 4 oy" vs "Homilador · 32 hafta".
2. The 3-bullet summary works for children: allow-list payload = age in months, sex, the last 3 checks'
   values, hits — nothing personal. Template fallback included.

## Part D — UI: the switch
1. A segmented switch at the top of the map, the patient list, the alerts list and the dashboard:
   **"Homiladorlar | Bolalar (0–1 yosh) | Hammasi"**, remembered per user (localStorage), default
   "Homiladorlar". Counts on each segment.
2. Map: children as dots with a different shape (e.g. rounded square or a small baby icon) in the same zone
   colours; the legend explains it. Admin aggregate maps get the same switch (counts only).
3. Child card (`/children/:id`): mother's code link, age, zone, explanation, a weight-for-age chart
   (the child's points over the WHO median and −2 SD line, Recharts), vaccine status, check history, AI
   summary. "Yangi ko'rik" form for a child check with a live risk preview (like the visit form).
4. Mother's card shows her children; a delivered pregnancy links to the child.
5. All texts Uzbek, every screen keeps the "Sintetik ma'lumot (demo)" badge.

## Part E — Check, commit, push
ruff, all tests, frontend typecheck/lint/build. Demo: switch to "Bolalar" → a red infant with fast
breathing → alert with 3 bullets → escalation works. Update docs/CLINICAL_RULES.md (infant rules + sources)
and DEMO_SCRIPT.md. Commit and push. Print the ✅/❌ checklist.
