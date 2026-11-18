# OnaRadar — Privacy and Legal Compliance (Law ZRU-547)

## 1. Personal Data Protection (Law of the Republic of Uzbekistan ZRU-547)
- **Encryption at Rest**: Full name (`full_name_enc`), JShShIR/PINFL (`pinfl_enc`), phone number (`phone_enc`), and home coordinates (`home_enc`) are encrypted at rest using Fernet (`AES-128-CBC` + `HMAC-SHA256`).
- **Keyed JShShIR Hash (`pinfl_hash`)**: To allow exact-match lookup by JShShIR without decrypting every row or storing plaintext JShShIR, `Patient.pinfl_hash` stores a keyed `HMAC-SHA256` digest computed with a server secret (`PINFL_HASH_SECRET` / `JWT_SECRET`). Plain JShShIR remains Fernet-encrypted, and `pinfl_hash` is never returned in any API response.
- **UI Masking by Default**: Patient cards display masked values (`D. K.`, `4***********12`, `+998*******12`). Unmasking requires `POST /api/patients/{id}/reveal`, which writes a `reveal_pii` audit log entry.

## 2. External Result Entry & Minimum-Necessary View
When a woman has tests or an examination performed at another polyclinic (`"Boshqa poliklinika bemori"`):
- **Responsibility Follows the Mahalla**: The polyclinic serving her mahalla (`Mahalla.polyclinic_id`) remains the sole data controller/tenant (`Patient.polyclinic_id`) for her longitudinal record.
- **Exact JShShIR Lookup Only**: Staff at the external clinic can look up the patient only by exact JShShIR (`POST /api/external/lookup`). Lookups are rate-limited per user (`30/hour`), and every lookup — including misses (`external_lookup_miss`) — is recorded in `AuditLog`.Wrong JShShIR values return a generic `404 Topilmadi`.
- **Minimum-Necessary View**: The external clinic sees **only**:
  1. Pseudonymous `patient_code`,
  2. Responsible polyclinic name and code,
  3. Responsible mahalla name, and
  4. The clinical entry form.
  The external clinic **never** sees the patient's name, obstetric history, current risk zone, risk score, or home address, and receives `404` if it attempts to open `GET /api/patients/{id}` before or after submitting the visit.
- **Dual-Polyclinic Audit Trail**: Every external submission writes an `external_entry` row in `AuditLog` recording both `from_polyclinic_id` (where the test was performed) and `to_polyclinic_id` (the responsible polyclinic).

## 3. Map Search & Cross-Polyclinic Privacy
- **Own Polyclinic**: Staff viewing their own polyclinic see patient home dots coloured by zone (`view_home_points` is audit-logged).
- **Other Polyclinics & Admin Views**: Selecting another polyclinic in the right-side map search panel (`GET /api/geo/polyclinics/search`) or viewing the admin drill-down (`GET /api/geo/*`) shows **mahalla polygons shaded by red share and aggregate zone counts only** (`"Boshqa poliklinika — faqat umumiy sonlar"`), never individual home dots or patient codes.

## 4. De-Identified AI Summary & Telegram Notifications
- Neither Google Gemini nor Telegram ever receives patient names, JShShIR, phone numbers, home coordinates, mahalla names, or free-text notes.
- Real patient data requires a **Paid (billing-enabled) Google Gemini API tier** and formal compliance review under Law ZRU-547. All demo data in this repository is 100% synthetic (`"Sintetik ma'lumot (demo)"`).
