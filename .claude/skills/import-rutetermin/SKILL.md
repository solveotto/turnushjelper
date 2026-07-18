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

## Ingestion path — check before starting

Timeskjema TSV is the intended primary source, but the parser lives on the
unmerged branch `ny_shift_ingress`. Check whether it has landed
(`ls app/utils/pdf/ | grep -i timeskjema`):

- **Parser present** → TSV is primary, PDF scrape is cross-verification.
- **Parser absent (current state)** → PDF scrape is primary; keep the
  Timeskjema `.xls` (really ISO-8859-1 TSV, not Excel) for later verification.

Read `CLAUDE.md` → "Turnus Data Sources & Ingestion" for the TSV parsing
traps and the kl_timer tolerance rationale before touching either path.

## Expected inputs

Place in `app/static/turnusfiler/{rXX}/` (match R26's naming):

| File | Purpose |
|---|---|
| turnus PDF (e.g. `Oslo R27 ....pdf`) | schedule scrape source |
| Timeskjema `.xls` | TSV cross-check / future primary |
| `streklister/{rxx}_streker.pdf` | strekliste PNGs + double shifts |
| `turnusnøkkel_RXX_org.xlsx` | only calendar-date source; kompdager |
| `søknadsskjema_org.docx` | application form template |

**PII exception:** `innplassering_RXX.pdf` (who is placed on which tur) goes in
`instance/protected/{rXX}/` (`AppConfig.protected_dir`), NOT under `app/static/` —
everything under static is served without authentication. Same for
`medlemsliste.xlsx` and `ansinitet.pdf`. `tests/test_protected_files.py`
enforces this.

## Steps

Everything runs with `venv/bin/` prefixes. Start with a baseline
`venv/bin/pytest -q` (must pass before you begin).

1. **Scrape**: `venv/bin/python app/utils/pdf/shiftscraper.py <pdf> RXX`
   → writes `turnus_schedule_RXX.json`. The scraper uses hardcoded pixel
   boxes — do not modify it; hardening goes in the validator.
2. **Validate**: confirm the JSON passes `validate_turnus_json`
   (`app/utils/pdf/scraper_validator.py`). A failure means stop and report,
   not patch the JSON by hand.
3. **Cross-verify** against the second source when available. Differences do
   NOT mean scrape error — R26's two sources differed in 20 real revision
   cells. Produce a diff (turnus, week, day, both values) for Solve to
   adjudicate. Never hard-fail on inequality.
4. **Double shifts**: `app/utils/pdf/double_shift_scanner.py` has
   `version = "r26"` **hardcoded in `main()`** — edit it to the new version
   (or fix it to take an argument) before running, else it silently rescans
   r26. Writes `double_shifts_{rxx}.json` from the streker PDF.
5. **DB set**: `venv/bin/python scripts/create_new_turnus_year_in_database.py`
   (creates the TurnusSet, imports shifts, auto-generates
   `turnus_stats_RXX.json` if missing). Alternative: admin-UI PDF upload
   (`handle_pdf_upload` in `app/routes/admin/turnus.py`) does scrape+create
   in one step.
6. **Innplassering**:
   `venv/bin/python scripts/import_innplassering.py --year RXX`.
   Known caveat: the 7.fører linjenummer parsing is unverified
   (`TODO_remaining_fixes.md` Task 7) — spot-check a few 7.fører rows.
7. **Strekliste PNGs**: upload/place the streker PDF, then generate via the
   admin UI or `strekliste_generator.generate_all_images("rxx")`. Geometry
   auto-calibrates from the PDF's hour header; if
   `tests/test_strekliste_geometry.py` fails, the PDF layout changed — report,
   don't retune constants.
8. **Kompdager**: with the nøkkel Excel in place, run
   `count_kompdager(turnus_set_id)` per linje, show Solve the counts, then
   add a reference assertion to `tests/test_kompdag_routes.py` mirroring the
   R26 pattern (`OSL_01 R26 = [4, 1, 3, 2, 2, 4]`).
9. **Activate** the set in the admin panel (sets `is_active=1`, invalidates
   caches on refresh).
10. **Finish**: full `venv/bin/pytest -q` (all green, count may grow with the
    new kompdag test), then report: files produced, validator results,
    cross-source diff, anomalies, and anything left for Solve to decide.

## Red flags — stop and report instead

- Editing schedule JSON by hand to make validation pass
- Tuning `_HOURS_TOL_LOW`/`_HOURS_TOL_HIGH` or scraper pixel boxes to make
  one dataset fit
- Treating cross-source differences as scrape errors without checking the
  PDF's own text
- Regenerating stats for an *existing* set (only
  `tests/test_shift_stats.py::test_stored_stats_match_fresh_computation`
  failing justifies that)
