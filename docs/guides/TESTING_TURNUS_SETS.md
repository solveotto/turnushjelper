# Testing Turnus Sets on a Development Machine

A point-by-point guide to verify everything related to turnus sets — the validation
gate, the scraper, the create/refresh/delete flows, logging, and downstream consumers.
Safe to run on a dev machine (no real users; deleting a set only affects local data).

> Two terminals help: one to run the app, one to watch the log.

---

## 0. Prerequisites

1. Activate the virtualenv and ensure `.env` exists with at least:
   ```
   SECRET_KEY=anything
   DB_TYPE=sqlite
   SQLITE_PATH=./dummy.db
   ```
2. Apply migrations: `alembic upgrade head`
3. Check existing sets on **Admin → Administrer turnussett**:
   - **Empty DB (fresh dev machine):** Section 2.2 creates the active R26 set — do it first;
     it doubles as the happy-path test.
   - **R26 already exists but inactive:** just use the activate/switch action (2.7).
   - **R26 already exists and active:** for the happy-path *create* test use the throwaway
     `R26COPY` copy instead (see the note in 2.2).

---

## 1. Automated tests (fast, no UI)

Run from the project root. Each line maps to part of the hardening.

1. **Validator + scraper helpers** — every check and pure helper:
   ```bash
   pytest tests/test_scraper_validator.py -v
   ```
   Expect: all pass.
2. **Committed data integrity** — R25/R26 pass the hardened validator (hours cross-check,
   start/slutt):
   ```bash
   pytest tests/test_data_integrity.py -v
   ```
   Expect: pass; the `TestScraperRoundtrip` tests `skip` unless a PDF is present (Section 3).
3. **Stats** — night classification + stored-vs-fresh freshness:
   ```bash
   pytest tests/test_shift_stats.py -v
   ```
4. **Full suite** — no regressions from this work:
   ```bash
   pytest -q
   ```
   Expect: the only failures are the pre-existing, unrelated ones (favorites/ical/admin-user
   sqlalchemy-session env issues). The turnus tests are all green.
5. **Mutation sanity check (optional)** — prove the tests can fail. Temporarily nudge a
   `DAG_POS` pixel bound in `shiftscraper.py` and confirm the golden roundtrip fails (only if
   a PDF is present); or comment out a validator check and confirm its unit test fails. Revert
   after.

---

## 2. Manual end-to-end (admin UI)

### 2.1 Setup
1. Start the app: `python run.py` (http://localhost:8080).
2. In a second terminal, watch the audit log:
   ```bash
   tail -f app/logs/turnus_import.log
   ```
3. Log in as an admin and go to **Admin → Administrer turnussett**.

### 2.2 Happy path — create the active set from existing files (no PDF needed)
On a fresh dev DB (no sets yet), create `R26` directly — this is both your happy-path test
and how you establish the active set everything else needs. The schedule/stats JSON already
exist on disk.
1. **Opprett turnussett**:
   - Navn: `OSL R26`
   - Årsidentifikator: `R26`
   - ✅ **Bruk eksisterende filer**, leave PDF empty
   - ✅ **Sett som aktivt turnussett**
   - Submit
2. Expect: green **`Validering OK: 57 av 57 turnuser godkjent.`** and the set is created and
   active.
3. Log: an **INFO** line `Turnus import OK R26 (user=...): 57 turnuser validated`.

> **If `R26` already exists in your DB** (`year_identifier` is unique), test the create flow
> against a throwaway copy instead:
> ```bash
> mkdir -p app/static/turnusfiler/r26copy
> cp app/static/turnusfiler/r26/turnus_schedule_R26.json app/static/turnusfiler/r26copy/turnus_schedule_R26COPY.json
> cp app/static/turnusfiler/r26/turnus_stats_R26.json    app/static/turnusfiler/r26copy/turnus_stats_R26COPY.json
> ```
> then create with id `R26COPY`, and `rm -rf app/static/turnusfiler/r26copy` afterwards.

### 2.3 Failure path — create from the broken fixture
1. Make sure the broken fixture exists (regenerate if cleaned up — see Appendix).
2. **Opprett turnussett**:
   - Navn: `Broken test`
   - Årsidentifikator: `R26BROKEN`
   - ✅ **Bruk eksisterende filer**, leave PDF empty
   - Submit
3. Expect: red **`Validering feilet: 7 problem(er) i turnussett R26BROKEN`** followed by the
   problem list (hours cross-check, start/slutt, ukedag, single-time day, duplicate name).
   **No set is created.**
4. Log: a **WARNING** line with the full problem list.

### 2.4 Crash path — unreadable PDF
1. Create a junk file: `echo "not a pdf" > /tmp/junk.pdf`
2. **Opprett turnussett**: Årsidentifikator `R26CRASH`, **uncheck** "Bruk eksisterende filer",
   upload `/tmp/junk.pdf`, submit.
3. Expect: red **`Feil ved skraping av PDF: ...`**, no set created.
4. Log: a **stack trace** under `Turnus import CRASHED R26CRASH (user=...)`.

### 2.5 Happy path via real PDF (only if you have `turnuser_R26.pdf`)
1. **Opprett turnussett** with a new year id, upload the real PDF.
2. Expect: scrape → green `Validering OK` → set created → INFO log.
3. This is the only path that exercises the **scraper** end-to-end (Sections 2.2–2.4 feed JSON).

### 2.6 Refresh (re-scrape, preserves favorites) — needs the PDF on disk
1. Ensure the source PDF is at `app/static/turnusfiler/r26/pdf/turnuser_R26.pdf`.
2. On **Administrer turnussett**, use the **refresh** action for R26.
3. Expect: green `Validering OK`, a summary of renamed/added/removed/unchanged shifts,
   favorites preserved, INFO log. On a (deliberately) bad PDF: summarized red flash +
   `Eksisterende turnusdata er ikke endret.` and the old data untouched.

### 2.7 Activate / switch
1. Use the **switch/activate** action on a non-active set.
2. Expect: it becomes active; the data manager reloads and the site serves its data.

### 2.8 Delete (cleanup)
1. Delete the throwaway sets you created (`Happy test`, etc.).
2. Expect: the set, its shifts, favorites, and søknadsskjema choices for it are removed
   (cascade — fine on dev). On dev only; never casually delete an active set in production.

---

## 3. Golden-file regression test (scraper output is locked)

1. Drop the real source PDF at `tests/fixtures/turnuser_R26.pdf`.
2. Run:
   ```bash
   pytest tests/test_data_integrity.py::TestScraperRoundtrip -v
   ```
3. Expect: scraped names, count, `tid`, `dagsverk`, totals, and `start`/`slutt` all match the
   committed `turnus_schedule_R26.json`. This is the safety net for any future scraper change.

---

## 4. Verify the start/slutt fix specifically

After a real scrape/refresh (2.5/2.6) or by inspecting the regenerated committed file:
```bash
python -c "import json; d=json.load(open('app/static/turnusfiler/r26/turnus_schedule_R26.json')); \
x=d[0]['OSL_01']['1']['1']; print('start',x['start'],'slutt',x['slutt'])"
```
Expect: `start` and `slutt` are **strings** consistent with `tid` (previously `start` was a
list and `slutt` was empty on cross-midnight shifts).

---

## 5. Verify logging routing

After running 2.2–2.4:
```bash
grep -c 'OK ' app/logs/turnus_import.log        # successful imports recorded
grep -c 'FAILED\|CRASHED' app/logs/turnus_import.log
grep -c 'FAILED' app/logs/app.log               # failures also propagate to app.log
```
Expect: `turnus_import.log` holds success (INFO) + failure (WARNING) + crash (stack trace);
`app.log` holds the WARNING/crash but **not** the INFO success lines.

---

## 6. Verify downstream consumers (the set actually works)

With a valid active set:
1. Browse the turnusliste / oversikt pages — shifts render.
2. Mark a favorite, reload — it persists.
3. View stats (night/weekend counts) — populated and plausible.
4. Generate a søknadsskjema (requires the turnusnøkkel template uploaded for the set).
5. Strekliste / innplassering features if used.

---

## Appendix: regenerate the broken fixture

If you removed `app/static/turnusfiler/r26broken/`, recreate it:
```bash
python - <<'PY'
import json, copy, os
root="app/static/turnusfiler"
d=json.load(open(f"{root}/r26/turnus_schedule_R26.json",encoding="utf-8"))
def workday(td):
    for w in range(1,7):
        for x in range(1,8):
            if len([t for t in td[str(w)][str(x)]["tid"] if ":" in t])==2: return w,x
    return 1,1
d.append({"OSL_01": copy.deepcopy(d[0]["OSL_01"])})           # duplicate name
d[1]["OSL_02"]["kl_timer"]="245:00"                            # hours cross-check
w,x=workday(d[2]["OSL_03"]); day=d[2]["OSL_03"][str(w)][str(x)]
day["start"]=list(day["tid"]); day["slutt"]=""                # start/slutt bug
d[3]["OSL_04"]["2"]["2"]["ukedag"]="Mandag"                   # wrong weekday
w,x=workday(d[4]["OSL_05"]); cell=d[4]["OSL_05"][str(w)][str(x)]
cell["tid"]=[cell["tid"][0]]                                  # single-time work day
os.makedirs(f"{root}/r26broken",exist_ok=True)
json.dump(d, open(f"{root}/r26broken/turnus_schedule_R26BROKEN.json","w"), indent=4)
print("broken fixture written")
PY
```
Clean up when done: `rm -rf app/static/turnusfiler/r26broken` (it is untracked).
