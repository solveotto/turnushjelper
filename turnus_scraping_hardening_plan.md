# Fail-safe ingestion of turnus PDF data — detection-first hardening

## Context

The turnus (shift rotation) data is the most critical data in the app, and today it
enters the system through **one path**: `ShiftScraper` (`app/utils/pdf/shiftscraper.py`)
reads a PDF using **hardcoded pixel bounding boxes** (`TURNUS_1_POS`, `DAG_POS`, plus
8px/20px spillover heuristics) and emits `turnus_schedule_{YEAR}.json`.

Two facts shape this plan:

1. **The PDF is the only source today, but the user is actively trying to obtain a
   structured (Excel/CSV/API) export.** Therefore we should *not* invest in rewriting the
   fragile pixel-extraction engine — it is the component most likely to be replaced. The
   risk of a blind rewrite (silent misparses on the known-good R25/R26 PDFs, with zero
   existing test coverage) is high and the payoff is short-lived.

2. The user's real goal — "fail-safe scraping and error detection" — is best served by a
   **source-agnostic detection layer**: a strict, well-tested validator that sits in front
   of *any* ingestion path (today's PDF scrape, tomorrow's Excel import). This work is
   low-risk, high-value, and survives the eventual source change.

So: **harden detection now, leave the extractor alone**, and lock current extractor
behavior behind a golden-file regression test so a future rewrite (or the switch to a
structured source) is provably safe.

### What already exists (and is good)
- `app/utils/pdf/scraper_validator.py::validate_turnus_json(data) -> (bool, list[str])`
  checks structure, weekday labels, time format, time-count↔dagsverk consistency,
  ≤15h shift duration, and total-hours plausibility ranges.
- Validate-before-write is already wired at every entry point: PDF upload
  (`handle_pdf_upload`), re-scrape (`refresh_turnus_set`), create-from-existing-files, and
  the `DataframeManager` load — all call `validate_turnus_json`. **Any hardening of the
  validator automatically improves all of them.**

### Known gap found during review
The active `turnus_schedule_R26.json` already contains a malformed record: `OSL_01` W1D1
has `"start": ["13:13","19:01"]` (a list) and `"slutt": ""` (empty), while sibling days are
correct strings. It passes today's validator because the validator only inspects `tid`, and
`shift_stats.py` recomputes start/end from `tid[0]`/`tid[1]` — so it is currently harmless,
but it is exactly the class of silent inconsistency we want detection to catch.

## Scope (agreed)
Detection-first. **No changes to the pixel-extraction logic.** One small, contained,
non-coordinate normalization of the scraper's output assembly is included (start/slutt).

## Implementation & rollback strategy
- Work on a dedicated branch off `main` (e.g. `turnus-validator-hardening`). **`main` stays
  untouched** and is the instant fallback during manual testing.
- **One commit per step** (2 → 1 → 3 → 3a → 4 → 5 → 6) so any single change can be reverted in
  isolation with `git revert <sha>` without unwinding the rest. Suggested order: land the
  validator + tests first (they're pure and safe), then the scraper bug fix + R26 regen, then
  the golden/integrity tests, then the route reporting/logging.
- If manual testing surfaces a problem: `git checkout main` to fall back entirely, or
  `git revert` the offending step's commit. **Do not merge to `main`** until the "How to test"
  manual smoke tests pass.

---

## Changes

### 1. Harden the validator — `app/utils/pdf/scraper_validator.py`
Keep the existing signature `validate_turnus_json(data) -> (bool, errors)` (backward
compatible with all 4 call sites and any tests). Add these **hard** checks:

- **Hours cross-check (the biggest detection win).** New helper
  `_compute_worked_hours(turnus_data)` that sums each day's shift duration from `tid`
  (reusing the same start/end/midnight-wrap logic already in `_validate_day`, lines
  156–167) across all 6×7 days, and compares the total against the scraped `kl_timer`
  within a tolerance. This catches misplaced times / mis-assigned codes far better than
  the current static range check — a parse error that still "looks plausible" will throw
  off the computed total.
  - The exact accounting relationship (does the sum equal `kl_timer`? how does `tj_timer`
    differ?) must be **calibrated empirically** against the real R25/R26 data in step 4:
    compute the sum, observe the delta vs `kl_timer`, set the tolerance so genuine data
    passes. If `tj_timer` doesn't cross-check cleanly, leave it as range-only.
  - **Calibration hazard — split shifts undercount.** The `_validate_day` duration logic
    (lines 156–167) only computes a duration for days where `len(times) == 2`. But the
    scraper's boundary-crossing path (`shiftscraper.py` lines 241–249) deliberately places
    **one time in the current day and the other in the *next* day** for shifts that span the
    cell boundary. Those two days each have a *single* time, so a naive per-day sum
    contributes **zero** for them and the computed total comes in low. If that happens, the
    only way to make real data pass is a large tolerance — which guts the check's
    sensitivity. Before committing to the cross-check, step 4 must explicitly **count how
    many days in R25/R26 are single-time split-shift halves** and decide whether
    `_compute_worked_hours` needs to stitch split shifts back together (pair a trailing
    single time with the leading single time of the following day) rather than just
    widening the tolerance.
- **Turnus uniqueness & names.** Reject duplicate turnus names (same name twice ⇒ a page
  parsed twice or a name-merge bug) and reject `UNKNOWN`/empty names (signals
  `extract_turnus_name` failed). Add an **optional** `expected_count` parameter (default
  `None`); when provided, error if `len(data) != expected_count` — catches silently
  dropped turnuser.
- **start/slutt ↔ tid consistency.** When `start`/`slutt` are present, require: a 2-time
  work day has `start == tid[0]` and `slutt == tid[1]` (both strings); a free/single-entry
  day has `slutt == ""`. This is the check that flags the R26 `OSL_01` record. Depends on
  steps 3 **and 3a** first — the scraper fix *and* the regenerated committed JSON — or this
  check turns the existing committed R26 data into a hard failure.

Use the existing `_get(d, key)` helper for all week/day lookups (handles int keys from the
scraper and str keys from the JSON file).

### 2. New unit tests — `tests/test_scraper_validator.py`
The validator is pure and has **zero tests** today; it is the gate, so it gets the most
coverage. Add a `valid_turnus()` factory producing a structurally-valid single-turnus dict
(6 weeks × 7 days, correct weekday labels, consistent totals), then mutate one field per
test to assert each failure is caught:
- non-list top-level, empty list, multi-key entry, non-dict data
- missing week / missing day / wrong `ukedag`
- bad time format, 2 times + empty dagsverk, dagsverk + 1 time, >15h duration
- `kl_timer`/`tj_timer` out of range, missing totals
- duplicate names, `UNKNOWN` name, `expected_count` mismatch
- hours cross-check mismatch, start/slutt inconsistency
- positive test: a clean `valid_turnus()` passes with no errors

Also add cheap unit tests for the scraper's **pure** helpers (no PDF needed):
`split_concatenated_times` (`"19:014:24"` → `["19:01","4:24"]`), `extract_turnus_name`
(multi-word name, stop at separators), and `FRIDAG_NORMALIZE`.

**Reuse, don't duplicate:** `tests/test_shift_stats.py` already has a minimal-valid-turnus
factory (`_make_single_shift_json`, lines 82–101). Lift a shared factory into
`tests/conftest.py` and have both `test_shift_stats.py` and the new validator tests use it,
rather than writing a second copy.

### Relationship to `tests/test_shift_stats.py` (no overlap)
The two suites guard **different links in the same chain** and are complementary:

```
PDF ──(golden-file test, step 5)──▶ schedule.json ──(stats freshness, test_shift_stats)──▶ stats.json
                                          ▲
                         (validator/integrity test, steps 2 & 4: is schedule.json well-formed?)
```

`test_shift_stats.py` validates the **stats** artifact (`turnus_stats_*.json`) — night-shift
classification, freshness vs recompute, internal sanity — and only reads the schedule JSON
as input, assuming it is valid. This plan validates the **schedule** artifact itself and the
PDF→schedule step. No redundancy.

### 3. Fix start/slutt assembly — `app/utils/pdf/shiftscraper.py`
This is a **bug fix to existing code**, not new behavior. The scraper *already* sets
`start`/`slutt` today, at `shiftscraper.py` lines 302–306, inside `plasseringslogikk_tid`
(i.e. once per placed time object, in the middle of the placement loop):

```python
if len(turnus[uke][dag]["tid"]) == 2:
    turnus[uke][dag]["start"] = turnus[uke][dag]["tid"][0]
    turnus[uke][dag]["slutt"] = turnus[uke][dag]["tid"][1]
else:
    turnus[uke][dag]["start"] = turnus[uke][dag]["tid"]   # ← assigns the LIST by reference
```

The malformed `OSL_01` W1D1 record (`start` is a 2-element list, `slutt` is `""`) is
produced by a **specific bug in this code**, not by its absence:
- The `else` branch assigns `start = turnus[uke][dag]["tid"]` **by reference** (aliasing the
  list itself), not a string.
- The concatenated-time split path (lines 241–251) appends a second time to `tid` and then
  **returns early, bypassing the start/slutt update at 302–306**.
- Net result: `start` aliases a `tid` list that subsequently grows to 2 elements, while
  `slutt` is never written and stays `""`. That is exactly the observed record.

**The fix** is therefore *not* to add a normalization pass alongside the existing code, but
to **remove lines 302–306 entirely** and replace them with a single deterministic pass over
all 6×7 days **after `sorter_turnus("tid")` has fully completed** (so neither the split path
nor any other early return can bypass it). For each day, from the finalized `tid` list:
`start = tid[0]`, `slutt = tid[1]` for 2-time work days; `start = tid`, `slutt = ""`
otherwise. This removes the malformed-record class at the source so step 1's consistency
check can be a hard error.

**Mandatory follow-on (see step 3a):** because this changes scraper output, the committed
R26 JSON on disk must be regenerated — steps 4 and 5 both assert against it.

### 3a. Regenerate and re-commit the R26 schedule JSON — prerequisite for steps 4 & 5
This is an explicit step, not an optional aside. After step 3, the committed
`app/static/turnusfiler/r26/turnus_schedule_R26.json` is still the *old, malformed* file,
which means:
- it will **fail step 1's new start/slutt consistency check** (start is a list) → **step 4's
  data-integrity test fails** until it is regenerated;
- it will **not deep-equal the step 3 scraper output** (`start:"13:13", slutt:"19:01"` for
  the fixed day) → **step 5's golden test fails** against the stale file.

So the required ordering is: **fix scraper (3) → re-scrape R26 from the source PDF (admin
"refresh" route or `ShiftScraper().scrape_pdf(...)`) → review the diff → commit the clean
R26 JSON → only then do steps 4 and 5 assert against it.** When reviewing the regenerated
diff, scan for any *other* changed records beyond `OSL_01` W1D1, so the golden file (step 5)
doesn't lock in a second silent bug.

### 4. Real-data integrity test — extend `tests/test_data_integrity.py`
Add a test that loads the committed `turnus_schedule_R25.json` and `turnus_schedule_R26.json`
and asserts `validate_turnus_json(...)` returns valid **including the new hours cross-check**.
This both guards the committed data against accidental corruption and is where the
cross-check tolerance is calibrated against reality.

### 5. Golden-file regression test — `tests/fixtures/` + `tests/test_scraper_golden.py`
Locks the current extractor's behavior so any future change (including the eventual
structured-source switch or an extraction rewrite) is caught immediately.
- **User action:** place the real source PDF at `tests/fixtures/turnuser_R26.pdf`.
  `tests/fixtures/` is *not* covered by the `.gitignore` rule
  `app/static/turnusfiler/**/*.pdf`, so it will be committed.
- The test runs `ShiftScraper().scrape_pdf(fixture)` and asserts deep-equality against the
  committed `app/static/turnusfiler/r26/turnus_schedule_R26.json` (the known-good output).
  **This must be the step-3a-regenerated JSON**, not the current malformed file — otherwise
  the test fails on the `OSL_01` start/slutt difference.
- If the fixture is absent, `pytest.skip(...)` so the suite still runs without the PDF.

### 6. Surface validation results — flash summary + durable log
Two improvements to how the (automatic, in-app) validator results are reported. Both live
at the **route** call sites (`handle_pdf_upload`, `refresh_turnus_set`, create-from-existing
in `app/routes/admin/turnus.py`); the validator stays a pure `(bool, errors)` function so it
remains easy to test.

- **Flash summary instead of a wall of red.** Today each error is its own `danger` flash, so
  a badly broken PDF produces dozens of alerts. Replace with: one headline
  (`Validering feilet: N problemer i turnussett {year_id}`), the **first ~10** errors listed,
  and a `... og N–10 til` line if truncated. Success keeps the existing
  `Validering OK: X av Y turnuser godkjent.` summary. Import is still blocked on failure as
  it is now.
- **Dedicated import audit log.** Turnus import is rare, high-stakes, and audit-worthy, so
  give it its own log rather than burying it in `app/logs/app.log`. Add a named logger
  `logging.getLogger("turnus.ingest")` with its own `RotatingFileHandler` →
  `app/logs/turnus_import.log`, level **`INFO`**, `propagate=True` (configured alongside the
  existing handler setup in `app/routes/main.py`). Propagation means failures still bubble up
  to `app.log` at `WARNING`, while the dedicated file holds the full pass/fail history —
  including successes, which the `WARNING`-level `app.log` would otherwise drop.
  From the route, after validating, log a structured line:
  - On success: `INFO` — `year_id`, who triggered it (`current_user.username`), turnus count,
    computed-vs-printed hours delta.
  - On failure: `WARNING` — `year_id`, username, problem count, and the error list.

  This gives a durable audit trail that outlives the dismissed flash message. (A DB-backed
  import-history table would be the upgrade path if this ever needs to be queryable/filterable
  in the admin UI — out of scope here.)

- **Log scrape crashes too (not just validation failures).** A corrupt/unreadable PDF makes
  `pdfplumber` raise *before* validation runs. Those `except Exception` blocks in
  `handle_pdf_upload` / `refresh_turnus_set` / create-from-existing currently only flash
  `Feil ved skraping av PDF: {e}` and swallow the detail. Add
  `logger.exception("Turnus import CRASHED %s (user=%s)", year_id, username)` (via the
  `turnus.ingest` logger) inside each block so the stack trace lands in `turnus_import.log`.
  Net effect: the log reflects **every detected failure** — both validation rejections and
  scrape crashes. (It still cannot log wrong-but-valid data that no check flags — the
  accepted residual risk of not rewriting the extractor.)

### What we deliberately do NOT do
- No change to `TURNUS_1_POS` / `TURNUS_2_POS` / `DAG_POS` or the spillover heuristics.
- No anchor/ruling-line extraction rewrite. Revisit only when a real PDF breaks the current
  scraper *or* the structured source lands — at which point the golden file (step 5) makes
  it safe.

## Verification
0. **Ordering:** complete step 3 (scraper fix) and step 3a (regenerate + commit clean R26
   JSON) **before** running steps 2/4/5 below — the new start/slutt consistency check and the
   golden test both assert against the regenerated committed JSON.
1. `pytest tests/test_scraper_validator.py -x -s` — all validator and helper unit tests pass.
2. `pytest tests/test_data_integrity.py -x -s` — committed R25/R26 JSON passes the hardened
   validator (confirms the cross-check tolerance is correctly calibrated to real data).
3. With `tests/fixtures/turnuser_R26.pdf` in place:
   `pytest tests/test_scraper_golden.py -x -s` — scraped output matches committed R26 JSON.
4. `pytest` — full suite green (no regressions in the 4 existing validator call sites).
5. Manual smoke: in the admin "Opprett turnussett" / "refresh" flow, upload a deliberately
   broken PDF and confirm the new checks surface as a **summarized** Norwegian flash error
   (headline + first ~10 problems) and **block** the import (no JSON written), per the
   existing validate-before-write flow.
6. Confirm the import outcome is written to the dedicated `app/logs/turnus_import.log`
   (success, validation failure, **and** a forced scrape crash via an intentionally corrupt
   PDF — each with `year_id` + username), and that failures also still appear in
   `app/logs/app.log` via propagation.

## How to test the improvements (detailed procedure)

Do these in order — calibration first (it decides the hours-cross-check design), then
automated tests, then a mutation sanity check, then manual end-to-end.

### Step 0 — Calibrate the hours cross-check (before locking any tolerance)
Resolves the split-shift hazard noted in Change 1. Run a throwaway script against the real
committed data and **look at the numbers** before writing the assertion:

```python
# scratch/calibrate_hours.py  — run: python scratch/calibrate_hours.py
import json
from app.utils.pdf.scraper_validator import _compute_worked_hours  # new helper

for year in ("R25", "R26"):
    path = f"app/static/turnusfiler/{year.lower()}/turnus_schedule_{year}.json"
    data = json.load(open(path, encoding="utf-8"))
    for entry in data:
        name, td = next(iter(entry.items()))
        computed = _compute_worked_hours(td)              # hours
        kl_h, kl_m = map(int, td["kl_timer"].split(":"))
        printed = kl_h + kl_m / 60
        # count single-time days (split-shift halves) for diagnosis
        singles = sum(
            1 for w in range(1, 7) for d in range(1, 8)
            if len([t for t in td[str(w)][str(d)]["tid"] if ":" in t]) == 1
        )
        print(f"{year} {name:22} computed={computed:6.2f} printed={printed:6.2f} "
              f"delta={computed-printed:+5.2f} single_time_days={singles}")
```
- If `delta` is small and stable for all turnuser → set the tolerance just above the worst
  delta and you're done.
- If `delta` is large/negative **and** `single_time_days > 0` → split shifts are undercounting;
  make `_compute_worked_hours` stitch a trailing single time to the leading single time of the
  next day **instead of** widening the tolerance (a wide tolerance guts the check).

### Step 1 — Automated tests, per improvement
```bash
pytest tests/test_scraper_validator.py -v   # Change 1+2: every check fires; helpers correct
pytest tests/test_data_integrity.py -v      # Change 4: real R25/R26 pass hardened validator
pytest tests/test_scraper_golden.py -v      # Change 5: needs tests/fixtures/turnuser_R26.pdf
pytest                                       # Changes 1–3,6: full suite, no regressions
```

### Step 2 — Prove the tests actually catch regressions (mutation sanity check)
A passing test only matters if it can fail. Temporarily break something and confirm red, then
revert:
- Nudge a scraper constant (e.g. one `DAG_POS` bound by a few px) → `test_scraper_golden.py`
  must fail. This proves the golden file is really locking extractor behavior.
- Weaken one validator check (e.g. comment out the duplicate-name rejection) → its dedicated
  unit test in `test_scraper_validator.py` must fail.

### Step 3 — Manual end-to-end in the admin UI (Change 6: flash + logging + blocking)
Start the app (`python run.py`, port 8080) and watch the log in another terminal:
```bash
tail -f app/logs/turnus_import.log
```
Exercise all three outcomes via **Admin → "Opprett turnussett"** / refresh:
- **Happy path** — create from a valid set (or "Bruk eksisterende filer"). Expect green
  `Validering OK`, `Shifts`/`TurnusSet` rows created, and an **INFO** line in
  `turnus_import.log` (year, user, count, hours delta).
- **Validation failure** — point at a deliberately broken schedule JSON: duplicate a turnus
  entry (triggers the duplicate check) or move one day's `tid` to throw off the hours total.
  Expect a **summarized** red flash (headline + first ~10), **nothing written**, and a
  **WARNING** line in the log + `app.log`.
- **Scrape crash** — upload a non-turnus / corrupt PDF. Expect `Feil ved skraping av PDF` and
  a **stack trace** in `turnus_import.log` (the new `logger.exception`).

### Step 4 — Verify the start/slutt normalization (Change 3)
Re-scrape R26 via the admin **refresh** action, then confirm `OSL_01` W1D1 in the regenerated
`turnus_schedule_R26.json` now has `start`/`slutt` as **strings** consistent with `tid` (the
record that was malformed). The new start/slutt check in `test_data_integrity.py` should pass.

## Appendix: create-turnusset workflow (reference)

Every creation path (PDF upload, existing files, refresh) funnels through the single
`validate_turnus_json` chokepoint before anything is written or the DB is touched — which is
why hardening the validator + logging there protects the whole system in one place.

```
                         create_turnus_set()  [routes/admin/turnus.py:37]
                                  │
                 ┌────────────────┴─────────────────┐
        use_existing_files                      PDF upload
                 │                                  │
   load existing schedule JSON         handle_pdf_upload()
   from turnusfiler/{year}/                   │
                 │                     save PDF to disk
                 │                            │
                 │                     ShiftScraper().scrape_pdf()  ── crash ──┐
                 │                            │                                │
                 └──────────────┬─────────────┘                               │
                                ▼                                             │
                  ✦ validate_turnus_json()   ◀── THE GATE                     │
                                │                                             │
                    ┌───────────┴───────────┐                                │
                 invalid                   valid                             │
                    │                       │                                │
   ✦ flash summary + log         write JSON (create_json)                    │
   PDF deleted / JSON not        generate stats JSON (shift_stats.Turnus)    │
   overwritten; ABORT                       │                                │
                    │            create_turnus_set() [turnus_service.py:11]   │
   ✦ also logged ◀──┼──── inserts TurnusSet row                              │
                    │                       │                ✦ logger.exception
   (back to form)   │            add_shifts_to_turnus_set() [turnus_service.py:142]
                    │            → inserts Shifts rows (turnus names)         │
                    │                       │                                │
                    │            if is_active → set_active + df_manager reload│
                    │                       │                                │
                    │            flash success → redirect                    │
                    └───────────────────────────────────────────────────────┘
```

Full operator-facing walkthrough (UI steps + manual follow-up) lives in
`docs/guides/CREATING_TURNUS_SETS.md`.
