# OnaRadar — Q&A preparation (25 likely mentor questions)

Short, honest answers. Numbers about the model come from `backend/ml/artifacts/metrics.json` (rendered into the
README "Model" block); never quote anything else from memory. Real-world statistics belong only in
`docs/PITCH_FACTS.md` with a source.

## Product and positioning
**1. How is this different from DMED (the national electronic medical record)?**
DMED records what happened; OnaRadar is a decision-support layer that watches those records for worsening and makes
sure someone acts. It is designed to read visits from DMED (in the prototype they are typed in or synthetic), not to
replace it.

**2. Who is the user and who pays?**
The users are patronage nurses, family doctors and OvaBMU specialists; the customer is the payer of maternal-health
programmes: the Ministry of Health, regional health departments or donor-funded projects. See `BUSINESS_MODEL.md`.

**3. Why not just a dashboard?**
A dashboard needs someone to look at it. OnaRadar pushes an alert with an SLA, escalates when nobody acts, and only
closes it when a new measurement proves the patient was seen.

**4. What does the AI actually do?**
Three layers: hard clinical rules (always win), trend rules (P01–P05 predict worsening before a threshold is crossed),
and an ML model that can only raise a zone. Gemini only writes a 3-bullet summary from de-identified features; it
never decides the zone.

**5. Is this a diagnosis tool?**
No. Every screen and summary says the final decision belongs to the doctor, and the AI text is checked for diagnosis
wording. We show "xavf belgisi" (risk sign), not a diagnosis.

## Clinical safety
**6. What if the model is wrong?**
The red-flag rules are deterministic and override the model; the model can raise but never lower a zone. Every
zone shows why: rule, trend and top SHAP factors in Uzbek.

**7. Who validated the clinical rules?**
Thresholds follow WHO antenatal / IMCI guidance and are kept in one file (`thresholds.py`), but they have **not yet
been validated by a clinician**. That review, with obstetricians and OvaBMU, is the first step of a pilot.

**8. How good is the model?**
On a synthetic test set ROC-AUC is about 0.66 (README "Model" block, from `metrics.json`), with high
pregnancy-level sensitivity only because rules + trends + ML are combined. Real performance is unknown until we
retrain and validate on real, consented data.

**9. Why is the AUC modest?**
The synthetic generator deliberately includes noise and early visits where nothing has started yet. We report the
honest number instead of tuning the generator to look good.

**10. Do you reduce the 12 mandatory antenatal visits?**
No. The 12 visits are never reduced; OnaRadar only suggests which of them could be a lighter nurse-led check, and a
doctor must confirm. The visit calendar in the demo is labelled "demo jadval" until an obstetrician confirms the
national schedule.

## Workflow and trust
**11. A nurse can press "accept" without seeing the patient. How do you stop fake clicks?**
"Qabul qildim" only stops the current escalation step. An alert closes only when a new visit with the relevant
measurement (e.g. blood pressure for a BP alert) is saved, a RED closure must be confirmed by a different person,
and if the next assessment is still red the alert reopens.

**12. What about falsified measurements?**
The department head sees simple plausibility signals per user (identical BP values, values ending in 0/5, no
variation, forms saved in seconds, bursts of visits). They are labelled "signal, ayblov emas": a reason to talk, not
proof.

**13. What happens when a patient cannot be reached?**
Each contact attempt is logged. Three failed attempts over two days, or a family refusal, marks the alert
"Aloqa o'rnatilmagan": it stays active, escalates with the reason and re-appears every 24 h (red) until a
measurement is entered. Admins see only counts.

**14. What if the family refuses?**
The nurse must go through a counselling checklist (danger signs, mahalla women's activist, mahalla leader, another
visit time) and write an informed-refusal note. The alert is never closed silently.

**15. What if she moved or delivers in another city?**
Any polyclinic can enter her result by JShShIR or code (rate-limited, audited); it goes to the responsible clinic. If
she moved permanently, she is transferred to the new mahalla's polyclinic and both clinics are in the audit log.

**16. Does it work offline / with bad internet?**
The web app needs a connection to the polyclinic server; Gemini and Telegram are optional and fall back
automatically (template summary, logged notification). An offline-first mobile mode is a planned task, not built yet.

## Privacy and law
**17. Where is the data stored?**
The prototype runs locally on SQLite. The production plan is PostgreSQL hosted inside Uzbekistan. Name, JShShIR,
phone and home point are encrypted at rest; names are masked in the UI and every card view is audited.

**18. How do you comply with Law ZRU-547 "On personal data"?**
Minimum necessary data per role (the nurse map shows only red-zone homes, admins see counts only), encryption,
audit of every view, and no PII to the LLM or Telegram. A formal legal review is required before real data.

**19. The localization rule changed in March 2026 — does that matter?**
Amendments in force from 27 March 2026 narrowed mandatory in-country storage (secondary sources list biometric,
genetic and telecom-subscriber data) and allow cross-border processing under conditions. We still plan in-country
hosting for health data, and the exact article text must be checked on lex.uz with a lawyer.

**20. What does Gemini see?**
Only an allow-list of clinical features plus the pseudonymous patient code: no name, JShShIR, phone, address or home
point. The output is checked for diagnosis wording and digit runs. Real patient data would require a paid Gemini tier
and a legal review; without a key the template summary is used.

**21. Is the demo data real?**
No. Everything is synthetic and every screen shows "Sintetik ma'lumot (demo)".

## Technology and delivery
**22. Why these technologies?**
FastAPI + React are fast to build and easy to hand over; SQLite keeps the demo dependency-free. Production plan:
PostgreSQL, Alembic migrations, Docker, a Telegram bot service, CI.

**23. How do you integrate with existing systems?**
Read-only import of visits from DMED / polyclinic systems is the integration path; the external-entry API already
accepts results from any polyclinic. Exact interfaces depend on Ministry access.

**24. How do you know it saves time or lives?**
We do not claim outcomes yet. The pilot would measure time-to-acknowledgement, share of red alerts closed with a
measurement, unreachable red cases, and doctor minutes saved (shown in the demo as "taxminiy").

**25. What do you need next?**
Clinician review of the rules and visit calendar, access to de-identified historical data to retrain the model, one
pilot district, and a legal review of data processing.
