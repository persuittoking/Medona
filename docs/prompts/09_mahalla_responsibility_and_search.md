# Task 09 — Mahalla responsibility, analyses from other clinics, a multi-mahalla polyclinic, polyclinic search on the map

Read CLAUDE.md first. Plan, then do each part, test, commit, and push. Do Tasks 07–08 first (committed).
Tenancy rules in `backend/app/api/tenancy.py` stay the single place where access is decided.

## Part A — Responsibility follows the mahalla
Principle: the family polyclinic that serves a woman's mahalla is responsible for her, wherever she has her
tests done. Data entered elsewhere is written into the responsible clinic's record.
1. `Mahalla.polyclinic_id` already names the responsible clinic. Make `Patient.polyclinic_id` always equal
   the polyclinic of `Patient.mahalla_id` (set on create/move, a check in the service, a test).
2. `Visit` (and the infant check) get `performed_at_polyclinic_id` (where the analysis/exam was done)
   and `entered_by`. NULL = done at the responsible clinic.
3. External result entry: staff of ANY polyclinic can record a visit/analysis for a woman who is not theirs:
   - a "Boshqa poliklinika bemori" form: search by JShShIR only (exact match). Store a keyed hash of the
     JShShIR (`pinfl_hash`, HMAC-SHA256 with a server secret from .env) to look it up — the plain JShShIR stays
     Fernet-encrypted. Backfill the hash for seeded patients.
   - The external clinic sees only: patient code, responsible polyclinic and mahalla name, and the form.
     NO name, history, zone or address (minimum necessary). After saving: "Natija mas'ul poliklinikaga
     yuborildi: <name>".
   - The visit is scored and stored under the responsible clinic; alerts go to the responsible clinic's
     specialist (normal chain). The responsible clinic sees a badge "Boshqa poliklinikada o'tkazilgan:
     <name>" on that visit, and a notification "Tashqi natija kelib tushdi".
   - Audit log: external_entry with both polyclinic ids. Rate-limit lookups per user (e.g. 30/hour) and log
     every lookup, including misses.
4. Tests: an external visit lands in the responsible tenant; the external user cannot read the patient
   afterwards (404); the alert goes to the responsible clinic; lookup by a wrong JShShIR → 404 without
   revealing anything; the hash never appears in API output.

## Part B — A polyclinic in another city that serves several mahallas
1. Add a 4th region/district/polyclinic: Samarqand shahri, "Samarqand shahar 3-son oilaviy poliklinikasi"
   (`PL-SAM-003`), responsible for **3 neighbouring mahallas** (pick 3 real adjacent MFY names in Samarqand
   city). Change `POLYCLINICS` in `app/geo.py` to a list of `mahalla_keys`, and `seed.py` `Tenant` to create
   one Mahalla per key with its own register (50–60 active pregnancies + children each). Existing
   polyclinics keep one mahalla.
2. Boundaries: extend `seed/fetch_mahallas.py` AREAS with the 3 Samarqand mahallas (OSM admin boundary if
   it exists, otherwise the existing street-block demo boundary method, non-overlapping, adjacent). Run it
   once and COMMIT the generated geojson + osm_cache, so seeding works offline.
3. Staff: nurses per mahalla (one per mahalla, each sees her own mahalla's patients by default, with a
   filter "Barcha mahallalar"), one doctor, specialist, department head per polyclinic. Add the region admin
   and district admin for Samarqand. Show the new users on the login demo list.
4. The polyclinic map shows all its mahallas with their names and per-mahalla counts; the admin drill-down
   shows Samarqand → district → this polyclinic → 3 mahallas (counts only).
5. Tests: 3 mahallas seeded with homes inside their own polygons; nurse sees only her mahalla by default;
   admin aggregates add up.

## Part C — Polyclinic search panel on the right side of the map
1. A right-side panel (320 px, collapsible; on mobile a bottom sheet) on every map page with a search
   input "Poliklinika yoki mahalla qidirish…": matches polyclinic name, code, city, and mahalla names,
   accent-insensitive (o‘/o'/oʻ, g‘/g'/gʻ treated alike).
2. Results list: polyclinic name, code, city, number of mahallas, and zone counts (Qizil/Sariq/Yashil) for
   the active "Homiladorlar/Bolalar" switch. Clicking a result flies the map to that polyclinic's mahallas
   and highlights them.
3. What is shown on the map after selecting (privacy — keep CLAUDE.md principle 4):
   - the user's OWN polyclinic: patient dots (as now), clickable to the card;
   - any other polyclinic (and everything for admins): mahalla polygons shaded by red share with counts,
     no individual dots, no codes. A note says "Boshqa poliklinika — faqat umumiy sonlar".
4. Below the search for polyclinic staff: a second input "Bemor kodi bo'yicha qidirish" within their own
   clinic — selecting a code centres the map on that dot and opens a small popup with the zone and a link to
   the card.
5. Backend: `GET /api/geo/polyclinics/search?q=` returning aggregates only (works for every role), tested
   for not leaking patient-level data.

## Part D — Check, commit, push
ruff, all tests, frontend typecheck/lint/build. Demo: log in as the Samarqand nurse → 3 mahallas on the map →
search "Nukus" in the right panel → Nukus polyclinic shows counts only → as a Nukus nurse enter an external
visit for a Samarqand woman by JShShIR → the Samarqand specialist gets the alert. Reset demo data. Update
docs (ARCHITECTURE, PRIVACY_AND_LEGAL: the external-entry rule and the minimum-necessary view; DEMO_SCRIPT).
Commit and push. Print the ✅/❌ checklist.
