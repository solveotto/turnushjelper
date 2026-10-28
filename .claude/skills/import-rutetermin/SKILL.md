---
name: import-rutetermin
description: Use when onboarding a new rutetermin (R27, R28, ...) into Turnushjelper, or re-importing/refreshing an existing turnus set's source data — new Timeskjema/turnus-PDF/innplassering/streker files have arrived and must become schedule JSON, stats, DB records, and PNGs.
---

# Import a rutetermin

## Overview

Turn a new rutetermin's source files into a live, validated turnus set.
Data correctness is the app's entire value: **never bypass
`validate_turnus_json`, never silently "fix" source data, and report every
anomaly and cross-source difference to Solve at the end.**

Read `CLAUDE.md` → "Turnus Data Sources & Ingestion" first: the Timeskjema
parsing traps, the kl_timer tolerance rationale and the strekliste rules all
live there. `docs/guides/CREATING_TURNUS_SETS.md` is the step-by-step guide
to the admin UI that this skill assumes.

## Ingestion path

The Timeskjema export is the primary source and the PDF scrape is the
cross-check (decided 2026-07-08; the parser is on `main` at
`app/utils/timeskjema_parser.py`). Both run through the same admin page,
**"Opprett turnussett"** (`create_turnus_set` in `app/routes/admin/turnus.py`),
which sniffs the uploaded file by content:

- **Timeskjema `.xls`** (really ISO-8859-1 TSV, not Excel) → parsed,
  self-checked, validated. If a verification PDF is uploaded alongside, the
  PDF is scraped too and every difference is staged on a review page
  (`/admin/import-turnusset/review/<year>`) for Solve to approve or cancel.
  Nothing is written until approval.
- **Turnus PDF** only → `ShiftScraper` (hardcoded pixel boxes; do not modify
  it — hardening goes in the validator). Use this when the drop is a PDF
  with no Timeskjema yet, which is typical for a first draft.
- Anything else (real OLE2 Excel, HTML) is refused. Run
  `scripts/probe_timeskjema.py <file>` on a new Timeskjema **before**
  uploading: it diffs the file's shape against the R26 export and says in
  seconds whether the parser will accept it. `--convert` fixes a wrong
  encoding losslessly.

The stored source names matter: the create flow saves
`turnusdata/{rxx}/turnuser_RXX.xls` and `turnusdata/{rxx}/pdf/turnuser_RXX.pdf`,
and **"refresh"** on an existing set re-ingests exactly those files
(Timeskjema preferred, PDF fallback), renames/adds/removes shift rows while
**preserving favourites**, and regenerates stats. Later revisions of the
same rutetermin go through refresh, never through a second create.

## Expected inputs

Place in `turnusdata/{rXX}/` (match R26's naming) — the data store lives
outside `app/`, since anything under `app/static/` is served without
authentication:

| File | Purpose |
|---|---|
| Timeskjema `.xls` → `turnuser_RXX.xls` | primary schedule source |
| turnus PDF → `pdf/turnuser_RXX.pdf` | cross-check, or primary when no Timeskjema |
| streker PDF, uploaded → `streklister/{rxx}_streker_{STED}.pdf` | strekliste PNGs, strekliste tables, double shifts |
| `turnusnøkkel_RXX_org.xlsx` | only calendar-date source; kompdager; søknadsskjema |
| `søknadsskjema_org.docx` | application form template |

A first draft usually arrives without the nøkkel, streker and innplassering.
That is fine: kompdager show `–`, strekliste tabs stay empty and
søknadsskjema will not generate until the files exist. Never fake them.

**PII exception:** `innplassering_RXX.pdf` (who is placed on which tur) goes
in `instance/protected/{rXX}/` (`AppConfig.protected_dir`), NOT under
`app/static/`. Same for `medlemsliste.xlsx` and `ansinitet.pdf`.
`tests/test_protected_files.py` enforces this.

## Where to run it

`turnus_schedule_RXX.json`, `turnus_stats_RXX.json` and
`double_shifts_{rxx}.json` are tracked in git; the source PDFs, PNGs and
`.xls` are not. Preferred flow: import locally through the admin UI, read
the diff, commit the generated JSON, `git pull` on the server and create the
set there with **"Bruk eksisterende filer"** (same validator, no re-scrape).
Data imports need no restart: the per-worker caches carry a fingerprint of
their source files and rebuild when it changes (CLAUDE.md → Caching). A pull
that brings code still needs `sudo systemctl restart turnushjelper`. Deploy
status is per host: record host *and* SHA.

## Steps

Everything runs with `venv/bin/` prefixes. Start with a baseline
`venv/bin/pytest -q` (must pass before you begin) and `venv/bin/alembic
current` (must be at head on the DB you import into).

1. **Create the set** in "Opprett turnussett": name, `RXX`, upload the
   Timeskjema (plus the PDF as verification if available) or the PDF alone.
   Leave **"Sett som aktivt turnussett"** unticked for a draft — users can
   browse any set from the navbar selector, and R26 stays live until the
   final version lands. The year check warns if the Timeskjema's rutetermin
   end year does not match `RXX`.
2. **Read the validation flashes and the review page.** A red "Validering
   feilet" means stop and report — never patch JSON by hand. Cross-source
   differences do NOT mean scrape error: R26's two sources differed in 20
   real revision cells. Hand the diff (turnus, week, day, both values) to
   Solve to adjudicate. The full log is `app/logs/turnus_import.log`.
3. **Strekliste**: upload the streker PDF on "Administrer turnussett". The
   employer's edition covers every depot; pick the set's stasjoneringssted
   (OSL) when asked, and only those pages are kept. Then press "Generer".
   That one step renders the PNGs, scans double shifts into
   `double_shifts_{rxx}.json`, and parses the duties into
   `strekliste_dagsverk` / `strekliste_aktivitet`. It runs as its own
   process (minutes on the servers) and the dialog polls it;
   `scripts/generate_strekliste.py --year RXX` is the same run from the
   command line. Never place the full multi-station PDF by hand: it would
   bypass the split. Geometry auto-calibrates from the PDF's hour
   header; if `tests/test_strekliste_geometry.py` fails, the layout
   changed — report, don't retune. Then run
   `scripts/strekliste_gjennomgang.py --year RXX` and **read the report**
   (`turnusdata/{rxx}/streklister/gjennomgang_{rxx}.html`, gitignored)
   warnings-first before trusting the parse. For the CLI,
   `app/utils/pdf/double_shift_scanner.py <rxx>` takes the version as an
   argument.
4. **Turnusnøkkel**: upload `turnusnøkkel_RXX_org.xlsx` on "Administrer
   turnussett" when it arrives.
5. **Innplassering**: `venv/bin/python scripts/import_innplassering.py
   --year RXX` (or the admin button). It prints which DB it is about to
   write to — check that line; a wrong `DB_TYPE` once wrote R26 into an
   empty local SQLite while prod stayed unchanged. The 7.fører linjenummer
   parsing is unverified — spot-check a few 7.fører rows with
   `scripts/check_7th_drivers.py --year RXX`.
6. **Kompdager**: with the nøkkel in place, run `count_kompdager(turnus_set_id)`
   per linje, show Solve the counts, then add a reference assertion to
   `tests/test_kompdag_routes.py` mirroring the R26 pattern
   (`OSL_01 R26 = [4, 1, 3, 2, 2, 4]`).
7. **Exports for nlfstreik** once the set is final:
   `scripts/export_turnusplan.py --year RXX` (needs the nøkkel) and
   `scripts/export_strekliste.py --year RXX`.
8. **Activate** the set in the admin panel when the final version lands
   (both workers follow within a minute), and run the `verify-turnus-data`
   skill.
9. **Finish**: full `venv/bin/pytest -q` (all green, count may grow with the
   new kompdag test), then report: files produced, validator results,
   cross-source diff, anomalies, and anything left for Solve to decide.

CLI fallbacks exist for every step (`app/utils/pdf/shiftscraper.py <pdf> RXX`,
`scripts/create_new_turnus_year_in_database.py RXX "<name>"`), but they
skip the review page, so prefer the UI for the initial import.

## Red flags — stop and report instead

- Editing schedule JSON by hand to make validation pass
- Tuning `_HOURS_TOL_LOW`/`_HOURS_TOL_HIGH` or scraper pixel boxes to make
  one dataset fit
- Treating cross-source differences as scrape errors without checking the
  PDF's own text
- Creating a second turnus set for a revision instead of using refresh
  (`year_identifier` is unique; favourites are per set)
- Regenerating stats for an *existing* set (only
  `tests/test_shift_stats.py::test_stored_stats_match_fresh_computation`
  failing justifies that)
- Seeding a real `year_identifier` in any test that deletes a turnus set
  (it deletes the real PNGs — see `tests/test_turnus_set_delete_guard.py`)
