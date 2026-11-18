# OnaRadar — demo script (tasks 07–08: smart alerts, children 0–1 year)

All data is synthetic. Password for every demo user: `demo1234`. Start: `start_all.bat`
(backend :8000, frontend :5173). Reset afterwards: `reset_demo.bat` (stop the backend first).

`DEMO_MODE=true`: the red-alert SLA is `DEMO_SLA_RED_MINUTES` (10), so nothing escalates by itself mid-pitch.

## 1. Trend-only patient (≈30 s)
1. Log in **PL-NUK-001 / nurse** → Bemorlar → search `TRND`.
2. `QQR-NUK-TRND2` is **RED** although no static rule fires: "Nega bu zona?" shows
   **P01 · Prognoz** "Sistolik bosim 3 ko'rikda ketma-ket oshmoqda: 116 → 125 → 134; shu sur'atda 2 haftada
   140 dan oshishi mumkin — hozir 130/85 dan yuqori" with a sparkline ↗.
3. `QQR-NUK-TRND3` is **YELLOW** by P02 (Hb 122 → 113 → 104 g/L, sparkline ↘).
   Say: *the system warns before a threshold is crossed; the final decision belongs to the doctor.*

## 2. DEMO1 turns red (≈60 s)
1. `QQR-NUK-DEMO1` (19 y, 31 weeks) is **YELLOW** by P01 only (diastolic 72 → 78 → 84 over 3 checkups).
2. **+ Yangi tashrif** → BP **152/98**, proteinuria **+2**, symptom *Kuchli bosh og'rig'i* → the live
   preview turns **RED** (R02 "Preeklampsiya shubhasi") → save.

## 3. Alert with the 3-bullet summary (≈45 s)
1. Log in **PL-NUK-001 / specialist** → Ogohlantirishlar.
2. The new red alert shows 3 bullets (why now · key numbers by gestational week · next step from the
   action catalog), a source badge "AI (Gemini)" or "Shablon", and "Yakuniy qaror shifokorga tegishli".
   While Gemini is still working the card shows a skeleton and polls every 3 s.
3. The live countdown "Javob berish uchun qoldi: 09:58" runs on every open red alert.

## 4. Escalation to the department head (≈45 s)
1. Press **"Demo: SLA muddatini hozir tugatish"** → the timer shows "Muddat tugadi — Bo'lim mudiriga
   yuborilmoqda…" → within 30 s the badge "Bo'lim mudiriga yuborildi" appears.
   "Batafsil: eskalatsiya tarixi" lists created → escalated, with names and times.
2. Log in **PL-NUK-001 / department_head** → "Kechikkan ogohlantirishlar" at the top → **Qabul qildim**
   (or "Mutaxassisga qayta biriktirish"). Every step is in the audit log; Telegram messages are
   de-identified (patient code + 3 bullets) and go to the log when no bot token is configured.
3. "Tizim haqida" (department head / admins) shows the SLA settings read-only and the chain:
   RED specialist → bo'lim mudiri → tuman boshqaruvi (faqat soni).

## 5. Children 0–1 year: the same zones (≈60 s)
1. Log in **PL-NUK-001 / nurse** → Bosh sahifa → switch **"Bolalar (0–1 yosh)"** (the choice is remembered per user).
   The map shows children as **rounded squares** at the mother's home point (circles = pregnant women). The
   KPIs and the top list are now about children.
2. `B-QQR-NUK-DEMO4-1` (4 days old, 2150 g, 36 weeks) is **RED**: N03 "Tez nafas olish (64/daq)".
3. Open `B-QQR-NUK-DEMO5-1` (boy, ~4 months, **GREEN**). The card shows the weight-for-age chart over the WHO median
   and the −2 SD line, the vaccine status (all on time), the check history, and the mother's code as a link.
4. **+ Yangi ko'rik** → breathing **56** → the live preview turns **RED**: I05 "Yoshiga nisbatan tez nafas (56/daq,
   me'yor < 50)". Say: *under 2 months the limit is 60, so the threshold depends on age (WHO IMCI)*. Save.
5. Log in **specialist** → Ogohlantirishlar → "Bolalar": the alert shows "Bola · 4 oy", the 3 bullets
   (why · weight by age in months · next step "Bolani shoshilinch ravishda bolalar shifoxonasiga yo'llash") and
   the countdown. "Demo: SLA muddatini hozir tugatish" → it escalates to the department head, the same chain as
   pregnancies. Explanation text: "Bolalar uchun faqat klinik qoidalar va trendlar (ML modeli qo'llanilmaydi)".

## 6. Admin view (≈20 s)
Log in **region.admin** → map drill-down → counts only, no names or codes. The same switch
"Homiladorlar | Bolalar | Hammasi" changes the counts.

## Reset
Stop the backend, run `reset_demo.bat` (re-seeds the database; DEMO1 is YELLOW again, DEMO5's child GREEN again).
An older demo DB also keeps working without a reset: on startup the backend adds new columns (never drops
anything), but the seeded children only appear after `reset_demo.bat`.
