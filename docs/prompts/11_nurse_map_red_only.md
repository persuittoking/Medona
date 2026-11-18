# Task 11: Nurse map = red dots only, no polyclinic search (fix)

Read CLAUDE.md first. Tasks 07-10 are done and committed: EXTEND, do not rewrite (tenancy.py, services/alerts.py,
MahallaMap, SubjectSwitch). Do NOT touch .env or *.db files. Do NOT git push.

## Problem (verified in the code)
For the `nurse` role the map page (`frontend/src/pages/PolyclinicMap.tsx`) still:
- shows the Qizil / Sariq / Yashil toggle buttons and draws yellow and green dots;
- shows the right-side `PolyclinicSearchPanel`;
and `GET /api/polyclinic/map` (backend/app/api/geo.py) returns ALL patients' home points to the nurse.

## Required behaviour (role `nurse` only)
1. The nurse map shows ONLY red-zone dots (pregnant women, children, and "Hammasi" all follow this).
   No yellow or green dots, and no zone toggle buttons. Replace them with one small info line:
   "Xaritada faqat qizil zonadagi (shoshilinch yordam kerak bo'lgan) bemorlar ko'rsatiladi".
2. Enforce it on the SERVER (minimum necessary data): for role `nurse`, `/api/polyclinic/map` returns only points
   with zone == "red". Other staff roles (doctor, specialist, department_head) keep the current behaviour.
3. Mahalla tooltips and the mahalla filter counts must NOT be computed from the filtered points (they would show
   wrong zeros). Use the aggregate counts the server already returns per mahalla (`_counts_by_mahalla` /
   `d.mahallas[i]` totals) so the tooltip still reads "Jami: N (Qizil r, Sariq y, Yashil g)".
4. The nurse does NOT get the polyclinic search panel: do not render `PolyclinicSearchPanel` for role `nurse`,
   and make `GET /api/geo/polyclinics/search` return 403 for `nurse` (tested). The nurse keeps the search box
   on the Patients list page. The map then uses the full width.
5. The "Barcha mahallalar" filter stays for nurses of multi-mahalla clinics (e.g. PL-SAM-003), default = her mahalla.
6. The legend on the map shows only the red count for nurses (reuse MahallaMap's `legend` prop or filter).
7. Every dot still opens the patient or child card, and `view_home_points` is still audit-logged.
8. Doctor, specialist, department_head and admin behaviour does not change.

## Tests (backend, pytest)
- nurse: `/api/polyclinic/map` has no yellow or green point, for subject pregnancy, child and all; red points present.
- doctor: `/api/polyclinic/map` still returns all zones.
- nurse gets 403 on `/api/geo/polyclinics/search`; doctor keeps access.
- another polyclinic's nurse still gets only her own red points (tenant isolation unchanged).
- aggregate counts per mahalla are unchanged for the nurse.

## Check by hand in the browser (as in earlier tasks) and report:
- login PL-NUK-001 / nurse: only red dots, no search panel, full-width map, tooltip counts correct.
- login PL-NUK-001 / doctor: unchanged (all zones, search panel).
- PL-SAM-003 nurse: only red dots, mahalla filter works.

## Finish
Run: ruff check backend, pytest -q, frontend typecheck, lint, build. Update docs/DEMO_SCRIPT.md (nurse map =
red only). ONE local commit "Nurse map: red-only dots, no polyclinic search", do NOT push.
Print a checklist with the result of each numbered requirement.
