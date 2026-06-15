# User Administration Rework: NLF-medlemsnummer

*Date: 2026-06-11*

Summary of the user-administration rework: registration switched from rullenummer to NLF-medlemsnummer, member-list Excel import in the admin UI, and full admin edit/create of users.

## What changed

### NLF-medlemsnummer is now the registration identifier

- New unique `medlemsnummer` column on `users` (migration `012_add_medlemsnummer`).
- The register form, backend validation, and the live-check API (`/api/check-medlemsnummer`, replacing `/api/check-rullenummer`) all use it.
- Rullenummer remains as optional HR data, and the seniority-PDF sync (`ansinitet.pdf`) is untouched.

### Excel import in the admin UI

New upload card on `/admin/employees` (mirrors the PDF upload). Expects an `.xlsx` with the columns `Navn` ("Etternavn, Fornavn") and `Medlemsnr`. The file is saved as `app/static/turnusfiler/medlemsliste.xlsx`.

Import logic (`user_service.sync_members_from_excel`):

- Matches **registered users** by exact normalized name and sets their medlemsnummer. Registered users are never deleted or overwritten — a differing existing medlemsnummer is reported as a conflict.
- Sets medlemsnummer on name-matched **stubs**, keeping their rullenummer so the PDF sync still recognizes them.
- Creates fresh stubs (`__stub_m<medlemsnummer>`) for new members.
- Deletes unregistered stubs that aren't on the member list or that conflict (stubs are disposable — they hold no credentials or favorites).
- Re-running the same file is idempotent (everything reports `unchanged`).

After upload, a report card shows counts, conflicts, and a clickable list of registered users whose names didn't match the member list (fix those manually via Edit).

### Full edit-user form

Admins can edit everything on `/admin/edit_user/<id>`: name, email, medlemsnummer, rullenummer, station, hire/birth dates, seniority number, password, and the admin/verified/stub flags. The Flask-Login cache (`user_<username>`, 60s TTL) is invalidated on edit/toggle/delete so changes take effect immediately.

### Full manual create

`/admin/create_user` has a "create as stub" toggle:

- **Stub**: requires name + NLF-medlemsnummer (credentials auto-generated, member registers themselves).
- **Regular account**: requires username + password; everything else optional — so admin accounts without NLF membership still work.

The quick "Legg til ansatt manuelt" form on the employees page now also requires NLF-medlemsnummer (rullenummer optional).

## Merging the two sources (updated 2026-06-12)

The Excel (medlemsnummer) and PDF (rullenummer) imports merge by name in **both directions**, so import order doesn't matter:

- `sync_employees_from_scrape` (PDF): if no user has the rullenummer but exactly one user with the same normalized name has **no** rullenummer (e.g. an Excel-created member stub), the rullenummer + HR data are merged into that user instead of creating a duplicate. Reported as `merged_by_name`.
- `sync_members_from_excel` (Excel): same-name duplicate stubs (from a PDF sync that ran before the member list was imported) have their rullenummer/station/dates/seniority **absorbed** into the kept member user before the duplicate is deleted.

To repair a database that already has duplicates: re-upload the medlemsliste Excel (absorbs the PDF twins), then run the PDF "Synkroniser" to refresh HR data. People whose names differ between the two sources won't auto-merge — set their numbers manually via Rediger.

## Data quirks worth knowing

1. **The xlsx stores member numbers as strings with a leading zero** (`"068588"`), and has broken dimension metadata that silently truncates naive openpyxl reads. The parser handles the truncation (`ws.reset_dimensions()`), and medlemsnummer is normalized everywhere (leading zeros stripped), so members can type `68588` or `068588` interchangeably.
2. **Name matching** is exact after normalization (trim, collapse whitespace, casefold). Middle-name or diacritic variants between the stored name and the Excel name will not match — registered users end up in the report's "uten NLF-medlemsnummer" list for manual fixing; stub mismatches self-heal (old stub deleted, fresh one created).

## Key files

| Area | Files |
|------|-------|
| Model + migration | `app/models.py`, `migrations/versions/012_add_medlemsnummer.py` |
| Service layer | `app/services/user_service.py` (`get_user_by_medlemsnummer`, `sync_members_from_excel`, `admin_create_user`, reworked `update_user`/`create_stub_user`, `normalize_medlemsnummer`) |
| Excel parser | `app/utils/member_excel.py` |
| Registration | `app/forms.py` (RegisterForm), `app/routes/registration.py`, `app/routes/api.py`, `app/templates/register.html` |
| Admin UI | `app/routes/admin/employees.py`, `app/routes/admin/users.py`, `app/templates/admin_employees.html`, `edit_user.html`, `create_user.html`, `admin_user_detail.html` |
| Tests | `tests/test_member_import.py`, `tests/test_registration_routes.py`, `tests/test_admin_user_routes.py`, extended `tests/test_user_service.py` |

## Going live

1. Deploy and run `alembic upgrade head`.
2. Upload the member list on **Admin → Ansattliste → NLF medlemsliste**.
3. Review the import report; fix unmatched registered users via Edit.

Note: `pytest` was not in the venv and was installed ad hoc (`venv/bin/pip install pytest`) — consider adding it to a dev requirements file.
