# Import turnusset — timeskjema (.xls) as primary data source

**Status:** implemented 2026-07-08 (all tests green; end-to-end verified with real R26 files).
One deviation discovered during implementation: the Tj.t week sums include the per-week
`SIR` allowance (sum-row column), so the arithmetic self-check is
`Σ(day Tj.t) + SIR(sum row) == declared Tj.t`; KL.TID sums exactly as designed.
**Date:** 2026-07-08
**Branch context:** `ny_shift_ingress`

**Naming rule:** flow-level names (routes, endpoints, UI wording) use *import turnusset* —
they describe what the feature does. Format-level names (the parser module, its functions,
stored files) keep *timeskjema* — they describe exactly which input a component reads.

## Goal

Switch primary turnus ingestion from PDF pixel-scraping (`ShiftScraper`) to parsing the
"Timeskjema" export (`R26 endelig.xls`). Keep the PDF scraper as (a) an optional
cross-verification source and (b) the fallback ingestion path when no .xls is available.

## Source file review (evidence, verified 2026-07-08)

### The file is not Excel

`app/static/turnusfiler/r26/R26 endelig.xls` is a **tab-separated ISO-8859-1 text file**
(a "Timeskjema for Lokfører" report) with a misleading `.xls` extension. This is good for
parsing (no binary format, no pixel coordinates), but the importer must **sniff the actual
content** and fail loudly on anything unexpected (real OLE2 Excel, HTML, etc.), since the
export tool controls the format, not us.

### Structure (per turnus block, 57 blocks in R26)

```
Timeskjema for Lokfører
Datasett: R 26 Vy ØSTLANDET GRUNNPLAN v02
Ruteterminperiode: R25          ← WRONG label; do not use
Rutetermin: 14.12.2025 12.12.2026   ← reliable dates
Stasjoneringssted: Oslo S
Turnus: OSL 01
Materiell: ...
Dag  Dv.Nr.  Start tid  Avslutningstid  KLT-NE ... KL.TID ... Tj.t ...   ← header (3 rows)
Mandag   3006  13:13  19:01  ... 5:48 ... 5:48 ...
...42 day rows total, interleaved with:
Sum uke N    ... per-week sums ...
Totalsummer for turnus  ... totals ...
```

Parsing facts established against the real file:

1. **Day rows are weekday-labeled** (`Mandag`…`Søndag`) — a built-in checksum. All
   57 × 42 day rows mapped onto calendar slots with zero label mismatches in a test parse.
2. **Accounting-week grouping:** `Sum uke` boundaries do not follow calendar weeks. A shift
   starting Sunday 23:45 is listed as the first row of the *next* week's block. Week blocks
   therefore have 6–8 day rows, but the day rows in sequence are always exactly the 42
   calendar days Mon-w1 … Sun-w6. → Map sequentially; verify each label against the
   expected weekday; hard-fail on mismatch or count ≠ 42.
3. **Trailing station-summary section** ("Beregninger sum per stasjoneringssted") at file
   end has its own `Totalsummer` row. Anchor turnus totals on the exact string
   `Totalsummer for turnus`, and stop block parsing at it.
4. **`&` artifacts** are appended to some values (`1:31&`, `7:35&`) — strip.
5. **Fridag codes** are single `X`/`O`/`T` (PDF used `XX`/`OO`/`TT`; normalize both).
6. **Blank rows** (only weekday label) = sleep-off day after a midnight-crossing shift —
   same semantics as empty `tid` in the current JSON.
7. **Midnight ends** appear as `0:00` (e.g. `914002400` 14:00–0:00).
8. **`Ruteterminperiode:` header says R25** while the `Rutetermin:` dates are
   14.12.2025–12.12.2026 (= R26). Never derive year-id from the label; the dates can be
   used as a warn-level cross-check against the admin-supplied year-id.
9. Encoding: ISO-8859-1 (ø/Ø etc.).

### Data comparison: XLS vs current PDF-scraped JSON

A full diff of all 57 turnuser (2,394 day-cells) against the live
`turnus_schedule_R26.json` found **20 differing cells + 9 differing totals**. Every one
was adjudicated against the PDF document's own text:

- The scraped JSON matches the PDF **exactly** at all 20 cells — the scraper made no
  errors there.
- The differences are **genuine revisions** between the documents. The PDF
  ("Oslo R26 etter listemøte.pdf", printed 09.10.2025 per its footer) is an older revision
  than the "endelig" XLS. Both carry the same dataset label ("… GRUNNPLAN v02"), so the
  label is not a version marker.
- Diff categories: 1-minute retimings (OSL 01/03/04, LHM-adjacent shifts); X/O fridag
  order swaps (OSL 02/07/15); week-1↔3 shift swap (OSL 19); Sunday shift swapped between
  OSL 25↔33; Ramme 10 weekend rework. Week sums inside each document are internally
  consistent with that document's cell values (e.g. OSL 01 week 3: PDF 35:30 with 7:01
  start, XLS 35:29 with 7:02 start).

**Consequences:**
- The live site currently shows the outdated "etter listemøte" values in those cells;
  importing the XLS is also a data correction.
- Cross-verification must **never hard-fail on inequality** — different revisions are a
  legitimate state only an admin can adjudicate. It must render a diff for approval.

### What the XLS lacks vs the PDF

The `Dv.Nr.` column holds only the base shift number (`3006`), not the PDF's suffix
annotations (`3006_SKNO`, `3139_LHM`, `5002-bm73_N05_5`). Verified consumers:
`df_utils` delt-dagsverk matching, consecutive-shift flags, and the shift-timeline image
lookup (`shift-timeline.js` → `/api/shift-image/...`) all extract the numeric prefix only.
The suffixes are **display-only**, but they carry real annotations (SKNO/LHM/HLD are
second-line depot/location notes in the PDF).

**Decision (user-confirmed, revised 2026-07-08):** enrich dagsverk display strings from
the PDF when one is available (see "Dagsverk enrichment" below); cells the PDF cannot
enrich show the clean XLS base number.

### What the XLS adds

Per-day `KL.TID`/`Tj.t`, per-week sums, and totals — enabling arithmetic self-validation
that the PDF path never had (day values must sum to the week rows, week rows to the total).

## Decisions (user-confirmed 2026-07-08)

1. **Verification policy:** import is prepared from the XLS; the diff vs the PDF is shown
   in the admin UI; admin explicitly approves before anything goes live. No diffs → proceed
   directly with an "ingen avvik" note.
2. **Dagsverk display (revised):** XLS base numbers are the canonical data; when a PDF
   is available its suffix annotations (`3006_SKNO`) are merged onto matching cells as a
   display enrichment. Originally "clean base numbers only"; revised same day at user
   request.
3. **Admin UX:** one upload field with content auto-detection (timeskjema or PDF), plus an
   optional separate "verifiserings-PDF" field.

## Design

### Guiding principle

The new parser is a **new producer of the exact same JSON structure** `ShiftScraper`
emits. Everything downstream — `validate_turnus_json`, `shift_stats.Turnus`,
`db_utils.add_shifts_to_turnus_set`, `DataframeManager`, templates — is untouched.
`validate_turnus_json` (in `app/utils/pdf/scraper_validator.py`) remains the single
source-agnostic gate every ingestion path passes.

### 1. New module: `app/utils/timeskjema_parser.py`

Standalone (no Flask imports), sibling of `app/utils/pdf/`.

- `sniff_format(file_bytes) -> "timeskjema" | "pdf" | "unknown"`
  - `%PDF` magic → `"pdf"`.
  - ISO-8859-1-decodable text containing a `Timeskjema for` header **and** `Turnus:` lines
    → `"timeskjema"`.
  - OLE2 magic (`D0 CF 11 E0`), HTML, or anything else → `"unknown"` with a clear error
    message. Never attempt a best-effort parse of an unknown format.
- `parse_timeskjema(path) -> list[{name: turnus_dict}]`
  - Output schema identical to `ShiftScraper`: per day `ukedag`, `tid` (list), `start`,
    `slutt`, `dagsverk`, `is_consecutive_shift: False`, `is_consecutive_receiver: False`;
    per turnus `kl_timer`, `tj_timer`. Turnus names normalized the same way
    (`OSL 09 Østre Linje` → `OSL_09_Østre_Linje`).
  - The hardcoded `False` consecutive-flags are not a regression: `ShiftScraper` also
    always emits `False`; the real values are computed at runtime in
    `df_utils.py:176-181` from the double-shifts JSON.
  - Duplicate turnus names need no parser-level check: `validate_turnus_json` already
    rejects them (`scraper_validator.py:112-114`).
  - Implements parsing facts 1–9 above. All violations collected as per-turnus error
    strings and raised/returned — a structural surprise anywhere fails the whole import
    (no partial imports).
- Internal arithmetic self-check (import-blocking):
  - Sum of day `KL.TID` == `Sum uke` `KL.TID` for each accounting week; same for `Tj.t`.
  - Sum of week sums == `Totalsummer for turnus`.
  - Exact HH:MM arithmetic, no tolerance — same document, same units.
- Warn-level check: `Rutetermin:` end-year vs admin-supplied year-id (`R26` ↔ `2026`).
- Output then passes through the unchanged `validate_turnus_json`.

### 2. Cross-verification: `diff_turnus_data(primary, secondary)`

Pure function (suggested home: `app/utils/turnus_diff.py`). Returns a structured diff:

- turnuser present on only one side,
- per-cell `tid` differences (uke, dag, both values),
- per-cell `dagsverk` differences comparing **numeric prefix only** (PDF suffixes ignored),
- `kl_timer`/`tj_timer` differences.

Renderable in a template and serializable (stored alongside the staged import for the
approval step).

### 2b. Dagsverk enrichment: `enrich_dagsverk(xls_data, pdf_data)`

Pure function in the same module. For each day-cell where the XLS has a shift number and
the PDF cell's **numeric prefix equals it**, replace the XLS `dagsverk` string with the
PDF's full string (`3006` → `3006_SKNO`, `3139` → `3139_LHM`). Everything else — base
numbers differing (swapped/reworked shifts), turnus missing from the PDF, fridag/blank
cells — keeps the clean XLS value. A retimed shift with the same number still enriches
(same shift, new minutes).

Safety properties (why this can run unconditionally whenever a PDF exists):

- **Display-only by construction:** every consumer of `dagsverk` extracts the numeric
  prefix (verified above), and the prefix is never altered.
- **Ordering:** runs *after* `diff_turnus_data`, so the diff shown for approval compares
  unenriched data and is unaffected.
- **Revision-proof:** an outdated PDF simply enriches fewer cells; it can never inject a
  wrong shift number.

Accepted cosmetic consequence: cells the PDF cannot enrich (e.g. Ramme 10's reworked
weekend) show bare numbers next to enriched neighbours.

### 3. Admin flow (`app/routes/admin/turnus.py`)

`create_turnus_set` changes:

- `CreateTurnusSetForm`: the existing `pdf_file` field becomes a schedule-file field
  accepting `.xls/.tsv/.txt/.pdf` (update its `FileAllowed(['pdf'])`, `forms.py:50`);
  add optional `verify_pdf_file` (PDF only). Note the `use_existing_files` checkbox
  defaults to `True` (`forms.py:45`), so the upload flow sits behind unchecking it —
  keep that interplay working in the template's `toggleFileUploads()`.
- On POST: sniff the schedule file (`sniff_format` reads the upload stream — `seek(0)`
  the `FileStorage` before saving it).
  - **timeskjema** → `parse_timeskjema` → self-checks → `validate_turnus_json`.
    - Verification PDF attached: scrape it with `ShiftScraper`, run `diff_turnus_data`,
      then `enrich_dagsverk` (in that order — the diff must reflect unenriched data).
      The verification PDF is also stored (staged, then `turnusfiler/{year}/pdf/` on
      finalization) so refresh can re-apply enrichment.
      - No differences → proceed with the enriched data, flash
        "PDF-verifisering: ingen avvik".
      - Differences → **stage and render review page** (see staging below) with
        "Godkjenn import" / "Avbryt" buttons; the staged `pending_import.json` holds the
        enriched data. New endpoints live under `admin/import-turnusset/`:
        `GET  admin/import-turnusset/review/<year_id>` (review page),
        `POST admin/import-turnusset/approve/<year_id>`,
        `POST admin/import-turnusset/cancel/<year_id>`.
        Approval finalizes; nothing (live JSON, stats, DB rows) is written before
        approval. Cancel deletes the staged directory.
    - No verification PDF: proceed directly (validator gate only, no enrichment), as the
      PDF path does today.
  - **pdf** → existing `handle_pdf_upload` path, unchanged (fallback).
  - **unknown** → flash error, import refused.
- On finalization (direct or via approval), the timeskjema is stored as
  `turnusfiler/{year}/turnuser_{year}.xls` (mirroring the stored PDF).
- `refresh_turnus_set`: when a stored timeskjema exists, re-parse it through self-checks
  + validator **only — no diff step** (re-running cross-verification against the stored,
  possibly older PDF would re-surface the same known revision diff on every refresh
  forever) — but **re-apply `enrich_dagsverk`** from the stored PDF when one exists,
  otherwise every refresh would silently strip the suffixes back to bare numbers.
  Enrichment is safe to re-run unconditionally (see 2b); diffing is not. Fall back to
  scraping the stored PDF when no timeskjema exists; when neither file exists, flash an
  error and leave existing data unchanged (current behavior, message extended to name
  both files).
- UI language: Norwegian (existing convention).

#### Staging (approval state)

Everything the approval POST needs must survive the redirect to the review page, and
none of it may be publicly reachable. `turnusfiler/` lives inside `app/static/`
(`config.py:91-95`), which Flask serves — unapproved data must not be staged there.

- Stage to the Flask **instance dir**, outside static: `instance/pending_import/{year_id}/`
  (created on demand; the `instance/` dir does not exist yet), containing:
  - `pending_import.json` — the parsed, validated turnus data
  - `pending_diff.json` — the structured diff shown on the review page
  - `pending_meta.json` — form state (`name`, `year_identifier`, `is_active`), uploader
    username, timestamp
  - `turnuser_{year_id}.xls` — the uploaded file itself (moved to its final
    `turnusfiler/{year}/` home only on approval)
  - `turnuser_{year_id}.pdf` — the verification PDF, when one was uploaded (moved to
    `turnusfiler/{year}/pdf/` on approval so refresh can re-apply enrichment)
- Approval POST (CSRF-protected like every other POST) re-reads the staged files and
  completes everything `create_turnus_set` does after validation: write the live schedule
  JSON, generate stats, create the `TurnusSet` row, `add_shifts_to_turnus_set`, store the
  timeskjema file — then deletes the staged directory.
- Lifecycle edges: a new upload for the same `year_id` **overwrites** the pending
  directory (abandoned imports never block); the manage page shows a
  "venter på godkjenning" indicator per pending year so an abandoned staging is
  discoverable and can be cancelled from there.

### 4. Unchanged, deliberately

`scraper_validator.py`, JSON schema, `shift_stats`, `df_utils`, `double_shift_scanner`
(double shifts come from a separate PDF and are out of scope), kompdag logic, all
templates except the create-form and the new review page.

## Testing

- **Fixture:** a trimmed timeskjema file committed to `tests/fixtures/` (3–4 turnuser)
  covering: accounting-week offset (Sunday-night shift in next block), `&` artifacts,
  `0:00` midnight end, blank sleep-off rows, `X/O/T` fridager, the trailing
  station-summary section, ISO-8859-1 characters — with hand-verified expected JSON.
- **Golden test:** parse the full real `R26 endelig.xls` (skip-if-missing, same pattern as
  the existing PDF golden test in `tests/test_data_integrity.py`) and assert against a
  committed expected output.
- **Failure modes (each must produce a specific error, not a wrong parse):** OLE2 bytes;
  HTML bytes; shuffled weekday label; 41-row block; corrupted week-sum arithmetic;
  duplicate turnus name (caught by the unchanged `validate_turnus_json`, not the parser —
  assert the gate still catches it for timeskjema input); empty file.
- **Diff function:** known-diff datasets, including the suffix-vs-base-number equivalence
  (`3006_SKNO` == `3006`).
- **Enrichment:** matching base → PDF string adopted; differing base (swap) → XLS value
  kept; turnus missing from PDF → untouched; retimed same-number shift → still enriched;
  enrichment output still passes `validate_turnus_json`; refresh with stored PDF
  preserves suffixes, refresh without stored PDF yields bare numbers (documented, not a
  failure).
- **Routes:** timeskjema upload happy path; upload with verification PDF and no diffs;
  with diffs → staged → approve; → cancel; unknown format refused; PDF fallback still
  works. Existing fixtures/patterns from `tests/conftest.py`.
- **Reference invariant:** after importing R26 from XLS, kompdag reference counts in
  `tests/test_kompdag_routes.py` (OSL_01 R26 = `[4, 1, 3, 2, 2, 4]`) must be re-derived —
  the X/O swaps in OSL 02/07/15 don't change counts (X and O both trigger kompdager), but
  verify rather than assume.

## Risks / notes for the reviewer

1. **The 20-cell data change is intentional.** Importing the endelig XLS updates live data
   (OSL 02/07/15 fridag order, OSL 19/25/33 shift swaps, Ramme 10, minute retimings).
2. **Format drift:** the `.xls` is whatever the export tool emits today. The sniffing +
   hard structural checks are the defense; if Vy changes the export, the import must fail
   loudly rather than parse garbage.
3. **Dagsverk display (revised decision):** suffixes are kept via PDF enrichment (2b)
   when a PDF is available. Without one — or for cells the PDF can't match — bare numbers
   show. All logic uses the numeric prefix either way; only display varies.
4. **Staged-import lifecycle:** staging lives in `instance/pending_import/`, outside both
   the served static dir (no public URL) and every normal loading path
   (`DataframeManager` loads via the DB's `turnus_file_path`), and is deleted on
   approve/cancel and overwritten by a new upload for the same year.
5. **`kl_timer` semantics differ from summed spans** — see calibrated tolerance notes in
   `scraper_validator.py` (`_HOURS_TOL_LOW`/`_HOURS_TOL_HIGH`); the XLS path reuses the
   same validator unchanged.
6. **Cache invalidation:** after approval or refresh of a set that already exists,
   delete `kompdager_{turnus_set_id}` (the current refresh route never does — a latent
   bug this plan inherits and should fix; today's X/O swaps don't change kompdag counts,
   but future revisions can). `df_manager.reload_active_set()` already covers the
   dataframe cache for the active set.
7. Suggested implementation order: parser + fixtures → diff function → admin flow +
   review page + staging → golden test against real file → manual end-to-end import on
   a dev DB.
