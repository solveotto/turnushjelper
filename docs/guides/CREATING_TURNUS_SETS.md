# Adding a new turnus set (rutetermin)

A **turnus set** is one published shift rotation, named after its rutetermin
(`R26`, `R27`, ...). Adding one turns the employer's source files into
schedule JSON, stats, database rows, strekliste images and tables, and
finally makes it the live set the site serves.

This guide is the end-to-end procedure. The domain rules it depends on
(Timeskjema parsing traps, the `kl_timer` tolerance, strekliste layout
rules, kompdag counting) live in `CLAUDE.md` under "Turnus Data Sources &
Ingestion" and "Kompdager"; they are not repeated here.

> UI labels are Norwegian and quoted in **bold**. Paths and code are English.
> Every command runs from the project root with the `venv/bin/` prefix;
> nothing is on PATH.

## The short version

1. Drop the source files into `turnusdata/{rxx}/` (and `instance/protected/{rxx}/` for innplassering).
2. `scripts/probe_timeskjema.py` on the Timeskjema export.
3. **Opprett turnussett** with the Timeskjema and the verification PDF. Do not tick "aktivt" for a draft.
4. Read the validation flashes and adjudicate the review page.
5. Upload the streker PDF and press **Generer**. Read the gjennomgang report.
6. Upload the turnusnøkkel. Import the innplassering. Derive kompdag reference counts.
7. Commit the generated JSON, pull on the server, create the set there with **Bruk eksisterende filer**, restart.
8. Activate when the final edition lands. Export for nlfstreik. Run the `verify-turnus-data` skill.

Later revisions of the same rutetermin go through **Oppdater** (refresh),
never through a second create.

---

## 1. What you need

Everything arrives from the employer at different times. A first draft
usually has only the Timeskjema or the turnus PDF. That is fine: the parts
that depend on missing files simply stay off (kompdager show `–`, strekliste
tabs are empty, søknadsskjema will not generate). Never fake a missing file.

| File | Put it at | Purpose | In git? |
|---|---|---|---|
| Timeskjema export (`.xls`) | `turnusdata/{rxx}/turnuser_RXX.xls` | **Primary** schedule source | Yes |
| Turnus PDF | `turnusdata/{rxx}/pdf/turnuser_RXX.pdf` | Cross-check, or primary when there is no Timeskjema | No |
| Streker PDF | `turnusdata/{rxx}/streklister/{rxx}_streker.pdf` | Strekliste PNGs, strekliste tables, double shifts | No |
| Turnusnøkkel | `turnusdata/{rxx}/turnusnøkkel_RXX_org.xlsx` | Only calendar-date source. Kompdager, mintur dates, søknadsskjema | Yes |
| Innplassering PDF | `instance/protected/{rxx}/innplassering_RXX.pdf` | Who is placed on which tur. **PII** | No |

The create flow and the admin uploads write these paths for you. If you
place files by hand, match the naming exactly: refresh, the strekliste
generator and the status checks all look for these exact names.

Two things about the Timeskjema `.xls`: it is **not Excel**. It is
tab-separated ISO-8859-1 text that the employer's system labels `.xls`. A
real OLE2 Excel file or an HTML export is refused by the importer. And the
`Ruteterminperiode:` header inside it is wrong; the parser uses the
`Rutetermin:` dates.

**PII never goes under `app/static/`**, which is served without a session.
Innplassering, medlemsliste and ansiennitet live in `instance/protected/`.
`tests/test_protected_files.py` enforces it.

## 2. Probe the Timeskjema before uploading

```bash
venv/bin/python scripts/probe_timeskjema.py "path/to/new export.xls"
```

It diffs the file's structure against the committed R26 export and says in
seconds whether the parser will accept it. If the encoding is wrong,
`--convert` rewrites it losslessly. Do this before touching the admin UI;
a refused upload tells you much less than the probe does.

## 3. Create the set

Baseline first: `venv/bin/pytest -q` must be green and
`venv/bin/alembic current` must be at head on the database you are about to
import into. Check which database that is: `DB_TYPE` in `.env`.

Go to **Admin → Opprett turnussett**:

| Field | What to put |
|---|---|
| **Turnussett-navn** | Display name, e.g. "OSL Togvakter 2027" |
| **Årsidentifikator** | `R27`. Stored uppercased, must be unique, drives every file path |
| **Sett som aktivt turnussett** | Leave **unticked** for a draft. See section 9 |
| **Bruk eksisterende filer** | Only on the server, once the JSON is already in git. See section 8 |
| **Last opp turnusfil** | The Timeskjema `.xls`, or the turnus PDF if there is no Timeskjema yet |
| **Verifiserings-PDF (valgfritt)** | The turnus PDF, when you have both |

The importer sniffs the uploaded file by content, not by extension:

- **Timeskjema**: parsed, self-checked, validated. The year check warns if
  the file's rutetermin end year does not match the identifier. If a
  verification PDF was uploaded too, the PDF is scraped and every
  difference is staged on a review page. **Nothing is written to
  `turnusdata/` or the database until you approve.**
- **PDF only**: scraped by `ShiftScraper` with hardcoded pixel boxes. This
  is the fallback path for a first draft. If a new PDF edition breaks it,
  do not retune the scraper; wait for the Timeskjema.
- **Anything else**: refused.

What a successful create writes:

| Artifact | In git? |
|---|---|
| `turnusdata/{rxx}/turnus_schedule_RXX.json` | Yes |
| `turnusdata/{rxx}/turnus_stats_RXX.json` | Yes |
| `turnusdata/{rxx}/turnuser_RXX.xls` (copy of the upload) | Yes |
| `turnusdata/{rxx}/pdf/turnuser_RXX.pdf` (copy of the upload) | No |
| `TurnusSet` row and one `Shifts` row per turnus | DB |

Every outcome, success or failure, is logged to `app/logs/turnus_import.log`.

## 4. Read the validation result

Green **"Validering OK: N av N turnuser godkjent"** means the data passed
`validate_turnus_json`, the single gate every ingestion path goes through.
It checks structure, weekday labels, time formats, shift durations, total
hours, a summed-hours cross-check against the printed `kl_timer`,
duplicate or `UNKNOWN` names, turnus count and start/slutt consistency.

Red **"Validering feilet: N problem(er)"** means stop. Nothing was saved.
The first ten problems are flashed, the full list is in the log. The fix is
a corrected source file from the employer or a hardened validator, never a
hand-edited JSON and never a loosened tolerance to make one dataset fit.

### The review page

When the Timeskjema and the PDF disagree you land on
`/admin/import-turnusset/review/RXX` with every differing cell (turnus,
week, day, both values) and the totals. The pending import is also listed
on **Administrer turnussett** until you approve or cancel it.

**A difference is not a scrape error.** The two sources are often
different planning revisions: the R26 pair differed in 20 of about 2,394
cells, all genuine. Check the PDF's own printed text for a few of them,
decide which edition is the truth, and then **Godkjenn** or **Avbryt**.
Cancelling leaves the system unchanged.

## 5. Strekliste

On **Administrer turnussett**, upload `{rxx}_streker.pdf` with **Last opp
strekliste PDF**, then press **Generer PNG-bilder fra PDF**. That one step
does three things:

1. Renders one PNG per shift into `turnusdata/{rxx}/streklister/png/`.
2. Scans double and split shifts into `turnusdata/{rxx}/double_shifts_{rxx}.json` (tracked in git).
3. Parses every duty into the `strekliste_dagsverk` and `strekliste_aktivitet` tables.

It runs synchronously inside the request and takes about 35 s on the
servers, so the gunicorn unit needs `--timeout 300`. If the browser shows
"En feil oppstod under generering", the request died; look in
`/var/log/turnushjelper/error.log`, not journald. For routine regeneration
prefer the CLI form in `CLAUDE.md`, which also prints the per-shift errors
the admin route discards. A forced run builds into a temp directory and
swaps in only when complete, so an interrupted run leaves the old images
untouched.

Check the count: `ls turnusdata/{rxx}/streklister/png | wc -l` must equal
the number of shifts in the set (423 for R26). A different count means the
wrong PDF edition.

Then **read the review report before trusting the parse**:

```bash
venv/bin/python scripts/strekliste_gjennomgang.py --year RXX
```

It writes `turnusdata/{rxx}/streklister/gjennomgang_{rxx}.html` (gitignored,
not served) with every duty's PNG above the rows read from it, warnings
first. Around 35 of 463 R26 duties carry a warning, all genuine print
quirks. The duty-number join rule and the double-duty split were both found
in this report, not by the tests. If `tests/test_strekliste_geometry.py`
fails after a new PDF, the layout changed: report it, do not retune the
fallback constants.

## 6. Turnusnøkkel, innplassering, kompdager

**Turnusnøkkel.** Upload `turnusnøkkel_RXX_org.xlsx` on **Administrer
turnussett**. The upload drops the cached kompdag counts for the set. This
Excel (sheet `Turnusnøkkel`, 6 groups × 8 rows, dates in columns H–P) is
the only place calendar dates come from. Holiday dates are computed in
code, not read from the sheet's red font.

**Innplassering.** Either the button on **Administrer turnussett** or:

```bash
venv/bin/python scripts/import_innplassering.py --year RXX
```

The script prints which database it is about to write to. **Read that
line.** A wrong `DB_TYPE` once wrote the R26 innplassering into an empty
local SQLite file while production stayed unchanged. Then spot-check the
7.fører rows, whose linjenummer parsing is unverified:

```bash
venv/bin/python scripts/check_7th_drivers.py --year RXX
```

Importing the innplassering is also what moves drivers' **Min tur** page to
the new set. Mintur follows the newest set a driver is placed in, not the
active set, so this step is visible to users the moment it lands, even if
the set is not active yet.

**Kompdager.** With the nøkkel in place, derive the per-linje counts and
pin them as a reference assertion in `tests/test_kompdag_routes.py`,
mirroring the R26 line (`OSL_01 R26 = [4, 1, 3, 2, 2, 4]`):

```bash
venv/bin/python -c "from app import create_app; from app.services import turnus_service; from app.utils.kompdag_utils import count_kompdager; app=create_app(); app.app_context().push(); ts=turnus_service.get_turnus_set_by_year('RXX'); print(count_kompdager(ts['id']))"
```

Show the counts to a human before committing the assertion. If they look
wrong, the counting rules in `CLAUDE.md` are user-confirmed; suspect the
nøkkel or the schedule first.

## 7. Verify

Run the `verify-turnus-data` skill, or by hand:

```bash
venv/bin/pytest -q                                      # all green
venv/bin/pytest tests/test_shift_stats.py -q            # stored stats match recomputation
venv/bin/pytest tests/test_kompdag_routes.py -q         # reference counts
venv/bin/pytest tests/test_strekliste_geometry.py -q    # hour-axis calibration
```

Then open the set in the navbar selector as a normal user and look at
turnusliste, a few shift pages with streklister, and turnusnøkkel.

## 8. Get it onto the server

The generated JSON, the Timeskjema copy, the nøkkel and `double_shifts`
are tracked; the PDFs, PNGs and innplassering are not and must be copied
over separately (see `SERVER_RESTORE_GUIDE.md`).

Preferred flow:

1. Import locally as above, commit `turnusdata/{rxx}/` and the kompdag test.
2. On the host: `git pull`, `venv/bin/alembic upgrade head`.
3. Copy the streker PDF to `turnusdata/{rxx}/streklister/` and the innplassering PDF to `instance/protected/{rxx}/`.
4. **Opprett turnussett** with **Bruk eksisterende filer** ticked. Same validator, no re-scrape.
5. Strekliste **Generer**, innplassering import, as in sections 5 and 6.
6. `sudo systemctl restart turnushjelper`.

Restart is not optional. Production runs two gunicorn workers with
per-process caches; an import only clears the worker that served your
request, and the other keeps serving the old set for up to an hour. The
symptom is "some users see the new turnus, some the old", with no error
anywhere.

**Deploy status is per host.** `turnushjelper-2` is staging and
`turnushjelper-1` is production, and the names are easy to confuse. Record
host and commit SHA, never just a date.

## 9. Activate, and the changeover

"Active" means the set that turnusliste, favorites, oversikt and
søknadsskjema work on. Mintur is independent of it (section 6).

Activate with **Aktiver** on **Administrer turnussett** when the final
edition has landed, then restart the service. Users can browse any set from
the navbar selector in the meantime, so there is no need to activate a
draft.

For the weeks between the old rutetermin ending and the new one being
final, set `TRANSITION_NOTICE=` in `.env` to a short message. Those four
pages then show the notice instead of the old set. Mintur and the set
dropdown are unaffected. Remove the line and restart when the new set is
active.

After activation, export for nlfstreik:

```bash
venv/bin/python scripts/export_turnusplan.py --year RXX    # needs the nøkkel
venv/bin/python scripts/export_strekliste.py --year RXX
```

Both write `.json.gz` files into `turnusdata/{rxx}/` (gitignored) that an
nlfstreik admin uploads.

## 10. Revisions: refresh, not create

When a corrected Timeskjema or PDF arrives for a set that already exists,
replace the stored file at its exact path (section 1) and press
**Oppdater** on **Administrer turnussett**. Refresh re-ingests the stored
Timeskjema (PDF as fallback), runs the same validator, renames, adds and
removes `Shifts` rows while **preserving favourites**, and regenerates the
stats. On failure the existing data is untouched. It deliberately shows no
review diff, since the stored PDF may be an older revision.

Never create a second set for a revision. `year_identifier` is unique and
favourites belong to the set, so a second set would strand them.

If the streker PDF changed too, regenerate with force and re-read the
gjennomgang report. Stale PNGs from the previous PDF look correct until
someone regenerates.

## Things that have bitten before

- **Hand-editing schedule JSON** to pass validation. The validator is the
  product; fix the source or harden the validator.
- **Tuning `_HOURS_TOL_LOW` / `_HOURS_TOL_HIGH`** or the scraper pixel boxes
  for one dataset. They are calibrated against R25 and R26.
- **Treating review-page differences as errors** without reading the PDF's
  own text.
- **Running a script against the wrong database.** Every script reads
  `.env`; the innplassering importer prints its target, read it.
- **Not restarting after an import.** See section 8.
- **Seeding a real `year_identifier` in a test that deletes a turnus set.**
  Deleting a set deletes its PNGs through the real data path, and they are
  gitignored so `git status` stays clean. `tests/test_turnus_set_delete_guard.py`
  shows the safe pattern.
- **Regenerating stats for an existing set** for any reason other than
  `tests/test_shift_stats.py` failing.

## Troubleshooting

| Symptom | Cause |
|---|---|
| "Ukjent filformat ... Import avvist" | Real Excel or HTML, not the TSV Timeskjema. Run the probe |
| "Validering feilet" on create | Source data failed the gate. Full list in `app/logs/turnus_import.log` |
| "Feil ved skraping av PDF" | The PDF layout does not match the scraper's fixed boxes. Use the Timeskjema |
| "Verifiserings-PDF kunne ikke leses" | Scrape crashed. Re-upload without the verification PDF to import unchecked, or fix the PDF |
| "En feil oppstod under generering" | The strekliste request died, usually gunicorn timeout. Use the CLI |
| Wrong PNG count | Wrong streker PDF edition |
| Søknadsskjema will not generate | Nøkkel missing for the set |
| Kompdager show `–` | Nøkkel missing. Not an error |
| Some users see the old set | One worker not restarted |
| Mintur still shows the old set | Innplassering for the new set not imported |
