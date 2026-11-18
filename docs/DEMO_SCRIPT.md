# OnaRadar — demo script (task 07: smart alerts)

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

## 5. Admin view (≈20 s)
Log in **region.admin** → map drill-down → counts only, no names or codes.

## Reset
Stop the backend, run `reset_demo.bat` (re-seeds the database; DEMO1 is YELLOW again).
