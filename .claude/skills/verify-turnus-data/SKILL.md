---
name: verify-turnus-data
description: Use when checking turnus data integrity — after an import or refresh, when someone reports wrong shift data ("turen min stemmer ikke"), before a release, or on a maintenance round. Read-only sweep of schedule JSONs, stats, kompdager, and strekliste geometry.
---

# Verify turnus data integrity

## Overview

A read-only sweep of everything that can silently rot. **This skill changes
nothing** — no regeneration, no JSON edits, no cache clears. Output is a
findings report; fixing is a separate, deliberate step Solve decides on.

Why it exists: R26 shipped with a malformed `OSL_01` W1D1 record
(`start` was a list, `slutt` empty) that sat unnoticed because a downstream
consumer happened to recompute around it. Silent inconsistency is the failure
mode to hunt.

## The sweep

All commands via `venv/bin/`. Run all five even if an early one fails —
the report should be complete.

1. **Validator over every schedule JSON:**

   ```bash
   venv/bin/python - <<'EOF'
   import glob, json
   from app.utils.pdf.scraper_validator import validate_turnus_json
   for p in sorted(glob.glob("app/static/turnusfiler/*/turnus_schedule_*.json")):
       ok, errors = validate_turnus_json(json.load(open(p)))
       print(p, "OK" if ok else f"FAIL: {errors}")
   EOF
   ```

2. **Field consistency** (the W1D1 malformation class): for every day with
   two times in `tid`, `start` must equal `tid[0]` and `slutt` equal `tid[1]`,
   both as plain strings. Flag any list-valued or empty `start`/`slutt` on a
   working day.

3. **Stats freshness:** `venv/bin/pytest tests/test_shift_stats.py -q` —
   `test_stored_stats_match_fresh_computation` recomputes stats from the
   schedule and diffs against the stored `turnus_stats_*.json`.

4. **Kompdag references:** `venv/bin/pytest tests/test_kompdag_routes.py -q`
   — asserts the known-good per-linje counts (OSL_01 R26 =
   `[4, 1, 3, 2, 2, 4]`). A failure means either data drifted or someone
   changed counting rules without re-deriving references.

5. **Strekliste geometry:** `venv/bin/pytest tests/test_strekliste_geometry.py -q`
   — geometry auto-calibrates from the streker PDF's hour header; failure
   means the PDF changed and PNGs likely need regeneration (report it, don't
   regenerate).

## Report format

Per check: **OK** or **FINDING** (file, turnus/week/day if applicable, what
was expected vs found). End with an overall verdict and, for each finding,
which *separate* action would fix it (re-import, regeneration, rule
re-derivation) — recommended, not performed.

## Not this skill's job

- Fixing anything it finds (that's a brief or import-rutetermin re-run)
- Judging cross-source revision differences (import-time concern)
- Performance/caching issues — this is data integrity only
