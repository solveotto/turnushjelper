# Creating a New Turnus Set

A **turnus set** is one published shift-rotation schedule (e.g. `R26`). Creating one ingests
a source PDF into structured JSON, registers it in the database, and — once activated — makes
it the live schedule the whole site serves.

Everything funnels through a single validation gate (`validate_turnus_json`): **nothing is
written to disk and no database row is created until the scraped data passes validation.** A
bad PDF is rejected with an error and leaves existing data untouched.

> UI labels are Norwegian; this guide quotes them in **bold**. Code/paths are English.

## Quick reference

| Action | Where | Automated or manual |
|---|---|---|
| Scrape PDF → schedule JSON | "Opprett turnussett" | **Automatic** on create |
| Validate scraped data | (the gate) | **Automatic** — blocks bad data |
| Generate stats JSON | create flow | **Automatic** |
| Insert `TurnusSet` + `Shifts` rows | create flow | **Automatic** |
| Set as active / switch active set | "Administrer turnussett" | **Manual** (unless ticked at create) |
| Upload turnusnøkkel template (xlsx) | "Administrer turnussett" | **Manual** |
| Upload strekliste PDF + generate images | "Administrer turnussett" | **Manual** |
| Import innplassering PDF | "Administrer turnussett" | **Manual** (optional) |
| Re-scrape / refresh an existing set | "Administrer turnussett" | **Manual** |

---

## Before you start (what you need)

- **The turnus schedule PDF** — the source document containing all turnuser. This is the only
  required input. *(Obtained externally; the PDF is not stored in git.)*
- Optional, for full functionality of the set:
  - **turnusnøkkel** Excel template (`turnusnøkkel_{YEAR}_org.xlsx`) — needed to generate the
    søknadsskjema (application form).
  - **strekliste** PDF — used to render the per-shift strekliste images and to detect double
    / split shifts.
  - **innplassering** PDF — maps drivers to specific shifts (optional feature).

---

## Step 1 — Create the set (the only automated step)

Go to **Admin → "Opprett turnussett"** and fill in the form:

| Field | Meaning |
|---|---|
| **Turnussett-navn** | Display name, e.g. "OSL Togvakter 2026" |
| **Årsidentifikator** | Short ID, e.g. `R26` (stored uppercased; drives all file paths) |
| **Sett som aktivt turnussett** | If ticked, this becomes the live set immediately |
| **Bruk eksisterende filer** | Use already-present JSON in `turnusfiler/{year}/` instead of uploading a PDF |
| **Last opp PDF-fil** | Upload the source PDF to scrape (when *not* using existing files) |

Then press **"Opprett turnussett"**.

### What happens automatically when you submit

1. **Save PDF** → `app/static/turnusfiler/{year}/pdf/turnuser_{YEAR}.pdf`.
2. **Scrape** → `ShiftScraper` reads the PDF and builds the schedule in memory.
3. **Validate (the gate)** → `validate_turnus_json` checks structure, weekday labels, time
   formats, shift durations and total hours. **Nothing is written until this passes.**
4. **Write JSON** → `turnus_schedule_{YEAR}.json`.
5. **Generate stats** → `turnus_stats_{YEAR}.json` (shift counts, night/weekend hours, etc.).
6. **Create DB row** → inserts the `TurnusSet`.
7. **Import shift names** → inserts a `Shifts` row per turnus name (e.g. `OSL_01`).
8. **Activate (if ticked)** → marks it active and reloads the live data manager.

On success you'll see green flashes: **"Validering OK: X av Y turnuser godkjent."** and
**"Turnussett {YEAR} opprettet!"**, then a redirect to **"Administrer turnussett"**.

### If validation fails

You'll get red **"Valideringsfeil: …"** messages describing each problem (e.g. a shift on the
wrong day, an implausible total). **The PDF is deleted and no JSON/DB row is created** — the
system is unchanged. Fix the source PDF and re-upload.

> The "**Bruk eksisterende filer**" path skips scraping but runs the **same** validation gate
> on the existing JSON, so it is protected identically.

---

## Step 2 — Manual follow-up (on "Administrer turnussett")

Creating the set does **not** do these — each is a separate manual action per set:

1. **Activate the set** (if you didn't tick "Sett som aktivt" at creation) — switches the live
   schedule and reloads the data manager. Only one set is active at a time.
2. **Upload turnusnøkkel template** — upload `turnusnøkkel_{YEAR}_org.xlsx`. Required before
   the søknadsskjema (application form) can be generated for this set.
3. **Upload strekliste PDF, then "Generer" images** — renders the per-shift strekliste PNGs.
   This step **also runs the double-shift scanner**, producing `double_shifts_{year}.json`
   (double/split shift markers).
4. **Import innplassering PDF** *(optional)* — upload the innplassering PDF to populate the
   `Innplassering` table (driver → shift mapping).

### Re-scraping later (refresh)

Use **refresh** on an existing set to re-run the scrape against the stored PDF after a
correction. It runs the same validation gate; on success it **renames/adds/removes** shift
rows while **preserving users' favorites**, and regenerates the stats JSON. **On failure the
existing data is left untouched.**

---

## Files & data produced

| Artifact | Created by | In git? |
|---|---|---|
| `turnusfiler/{year}/pdf/turnuser_{YEAR}.pdf` | PDF upload | No (gitignored) |
| `turnusfiler/{year}/turnus_schedule_{YEAR}.json` | Scrape (Step 1) | Yes |
| `turnusfiler/{year}/turnus_stats_{YEAR}.json` | Stats (Step 1) | Yes |
| `turnusfiler/{year}/turnusnøkkel_{YEAR}_org.xlsx` | Manual upload (Step 2) | Yes |
| `turnusfiler/{year}/double_shifts_{year}.json` | Strekliste generate (Step 2) | No (gitignored) |
| strekliste PNG images | Strekliste generate (Step 2) | No (gitignored) |
| `turnusfiler/{year}/innplassering_{YEAR}.pdf` + `Innplassering` rows | Innplassering import (Step 2) | No (gitignored) |
| `TurnusSet` row, `Shifts` rows | Create flow (Step 1) | DB |

---

## Manual checklist

- [ ] Obtain the source turnus PDF.
- [ ] **Opprett turnussett**: name, year ID, upload PDF (or use existing files).
- [ ] Review validation flashes — green = saved, red = rejected (fix PDF and retry).
- [ ] Activate the set (if not done at creation).
- [ ] Upload the turnusnøkkel template (for søknadsskjema).
- [ ] Upload strekliste PDF and generate images (also scans double shifts).
- [ ] *(Optional)* Import the innplassering PDF.

---

## Troubleshooting

- **Red "Valideringsfeil" on create** → the scrape produced data that failed a check. Nothing
  was saved; correct the PDF and re-upload. Common causes: a shift mapped to the wrong
  day/column, an implausible total, or a missing day.
- **"Feil ved skraping av PDF"** → the PDF could not be read at all (corrupt, or an
  unexpected layout the scraper's fixed coordinates don't match). The scraper relies on a
  fixed PDF layout — a re-exported or rescaled PDF can break extraction.
- **Søknadsskjema won't generate** → the turnusnøkkel template for this set is missing
  (Step 2.2).
- **No strekliste / double-shift data** → strekliste PDF not uploaded or images not generated
  (Step 2.3).

> **Planned hardening:** stricter validation (recomputed-hours cross-check, duplicate/count
> checks), a summarized error display, and a dedicated `app/logs/turnus_import.log` audit
> trail are described in `turnus_scraping_hardening_plan.md`. Update this guide once those land.
