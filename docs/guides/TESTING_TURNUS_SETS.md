# Testing Turnus Sets

Everything for verifying turnus sets, in two phases:

- **Phase A — Dev machine.** Point-by-point verification of the moving parts:
  the validation gate, the scraper, the create/refresh/delete flows, logging,
  and downstream consumers. Safe to run locally (no real users; deleting a set
  only touches local data). Run this when the validator/scraper code changes,
  or to shake out a dev machine.
- **Phase B — Staging → production.** The manual checklist for landing a **real
  new rutetermin** on the servers: favorites isolation, kompdager, innplassering
  / Min tur, strekliste PNGs, activation, and rollback. Run this once or twice a
  year when a new rutetermin arrives — always on staging (`turnushjelper-2`)
  first, then the short smoke path on production (`turnushjelper-1`).

Which one you need: touching validator/scraper code → **Phase A**. A real new
set arriving → **Phase B** (its Part 0 sends you to run the dev tests first).

Related guides:
- `CREATING_TURNUS_SETS.md` — *how* the import works, form fields, artifacts
- `.claude/skills/import-rutetermin/SKILL.md` — the step-by-step ingestion run

> Two terminals help throughout: one to run the app, one to watch the log.

---
---

# Phase A — Dev machine (validator, scraper, flows)

## A0. Prerequisites

1. Activate the virtualenv and ensure `.env` exists with at least:
   ```
   SECRET_KEY=anything
   DB_TYPE=sqlite
   SQLITE_PATH=./dummy.db
   ```
2. Apply migrations: `alembic upgrade head`
3. Check existing sets on **Admin → Administrer turnussett**:
   - **Empty DB (fresh dev machine):** Section A2.2 creates the active R26 set — do it first;
     it doubles as the happy-path test.
   - **R26 already exists but inactive:** just use the activate/switch action (A2.7).
   - **R26 already exists and active:** for the happy-path *create* test use the throwaway
     `R26COPY` copy instead (see the note in A2.2).

---

## A1. Automated tests (fast, no UI)

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
   Expect: pass; the `TestScraperRoundtrip` tests `skip` unless a PDF is present (Section A3).
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

## A2. Manual end-to-end (admin UI)

### A2.1 Setup
1. Start the app: `python run.py` (http://localhost:8080).
2. In a second terminal, watch the audit log:
   ```bash
   tail -f app/logs/turnus_import.log
   ```
3. Log in as an admin and go to **Admin → Administrer turnussett**.

### A2.2 Happy path — create the active set from existing files (no PDF needed)
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
> mkdir -p turnusdata/r26copy
> cp turnusdata/r26/turnus_schedule_R26.json turnusdata/r26copy/turnus_schedule_R26COPY.json
> cp turnusdata/r26/turnus_stats_R26.json    turnusdata/r26copy/turnus_stats_R26COPY.json
> ```
> then create with id `R26COPY`, and `rm -rf turnusdata/r26copy` afterwards.

### A2.3 Failure path — create from the broken fixture
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

### A2.4 Crash path — unreadable PDF
1. Create a junk file: `echo "not a pdf" > /tmp/junk.pdf`
2. **Opprett turnussett**: Årsidentifikator `R26CRASH`, **uncheck** "Bruk eksisterende filer",
   upload `/tmp/junk.pdf`, submit.
3. Expect: red **`Feil ved skraping av PDF: ...`**, no set created.
4. Log: a **stack trace** under `Turnus import CRASHED R26CRASH (user=...)`.

### A2.5 Happy path via real PDF (only if you have `turnuser_R26.pdf`)
1. **Opprett turnussett** with a new year id, upload the real PDF.
2. Expect: scrape → green `Validering OK` → set created → INFO log.
3. This is the only path that exercises the **scraper** end-to-end (Sections A2.2–A2.4 feed JSON).

### A2.6 Refresh (re-scrape, preserves favorites) — needs the PDF on disk
1. Ensure the source PDF is at `turnusdata/r26/pdf/turnuser_R26.pdf`.
2. On **Administrer turnussett**, use the **refresh** action for R26.
3. Expect: green `Validering OK`, a summary of renamed/added/removed/unchanged shifts,
   favorites preserved, INFO log. On a (deliberately) bad PDF: summarized red flash +
   `Eksisterende turnusdata er ikke endret.` and the old data untouched.

### A2.7 Activate / switch
1. Use the **switch/activate** action on a non-active set.
2. Expect: it becomes active; the data manager reloads and the site serves its data.

### A2.8 Delete (cleanup)
1. Delete the throwaway sets you created (`Happy test`, etc.).
2. Expect: the set, its shifts, favorites, and søknadsskjema choices for it are removed
   (cascade — fine on dev). On dev only; never casually delete an active set in production.

---

## A3. Golden-file regression test (scraper output is locked)

1. Drop the real source PDF at `tests/fixtures/turnuser_R26.pdf`.
2. Run:
   ```bash
   pytest tests/test_data_integrity.py::TestScraperRoundtrip -v
   ```
3. Expect: scraped names, count, `tid`, `dagsverk`, totals, and `start`/`slutt` all match the
   committed `turnus_schedule_R26.json`. This is the safety net for any future scraper change.

---

## A4. Verify the start/slutt fix specifically

After a real scrape/refresh (A2.5/A2.6) or by inspecting the regenerated committed file:
```bash
python -c "import json; d=json.load(open('turnusdata/r26/turnus_schedule_R26.json')); \
x=d[0]['OSL_01']['1']['1']; print('start',x['start'],'slutt',x['slutt'])"
```
Expect: `start` and `slutt` are **strings** consistent with `tid` (previously `start` was a
list and `slutt` was empty on cross-midnight shifts).

---

## A5. Verify logging routing

After running A2.2–A2.4:
```bash
grep -c 'OK ' app/logs/turnus_import.log        # successful imports recorded
grep -c 'FAILED\|CRASHED' app/logs/turnus_import.log
grep -c 'FAILED' app/logs/app.log               # failures also propagate to app.log
```
Expect: `turnus_import.log` holds success (INFO) + failure (WARNING) + crash (stack trace);
`app.log` holds the WARNING/crash but **not** the INFO success lines.

---

## A6. Verify downstream consumers (the set actually works)

With a valid active set:
1. Browse the turnusliste / oversikt pages — shifts render.
2. Mark a favorite, reload — it persists.
3. View stats (night/weekend counts) — populated and plausible.
4. Generate a søknadsskjema (requires the turnusnøkkel template uploaded for the set).
5. Strekliste / innplassering features if used.

---

## Appendix: regenerate the broken fixture

If you removed `turnusdata/r26broken/`, recreate it:
```bash
python - <<'PY'
import json, copy, os
root="turnusdata"
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
Clean up when done: `rm -rf turnusdata/r26broken` (it is untracked).

---
---

# Phase B — Staging → production import checklist

The two things that must not break: **importing a new turnusset**, and
**favorites (adding, sorting, and staying the right user's)**. A new rutetermin
arrives once or twice a year, always shortly before it is needed, so this
checklist exists to make the import boring.

Run it on **staging (`turnushjelper-2`) first**, then the short smoke path on
**production (`turnushjelper-1`)**. Every step has a **Forventet** line — if
what you see differs, stop and investigate rather than continuing.

## Handy one-liners

Run from the repo root on the host you are testing. Both work on SQLite (dev)
and MySQL (prod).

**Favorites per turnus set** — the snapshot everything else is compared against:

```bash
venv/bin/python -c "from app.database import get_db_session; from sqlalchemy import text; print(*get_db_session().execute(text('SELECT turnus_set_id, COUNT(*), COUNT(DISTINCT user_id) FROM favorites GROUP BY turnus_set_id ORDER BY turnus_set_id')), sep=chr(10))"
```

**Orphaned favorites** — rows pointing at a shift title that no longer exists
in their set (a refresh that removed shifts leaves these behind):

```bash
venv/bin/python -c "from app.database import get_db_session; from sqlalchemy import text; print(*get_db_session().execute(text('SELECT f.turnus_set_id, f.user_id, f.shift_title FROM favorites f LEFT JOIN shifts s ON s.title=f.shift_title AND s.turnus_set_id=f.turnus_set_id WHERE s.id IS NULL')), sep=chr(10))"
```

**Turnus sets and which is active:**

```bash
venv/bin/python -c "from app.database import get_db_session; from sqlalchemy import text; print(*get_db_session().execute(text('SELECT id, year_identifier, name, is_active FROM turnus_sets ORDER BY id')), sep=chr(10))"
```

---

## Part 0 — Preconditions (staging)

- [ ] **On the dev machine, not the server:** `venv/bin/pytest -q` is green on
      the SHA you are about to deploy. pytest is deliberately not in
      `requirements.txt`, so the servers don't have it — and the suite builds
      its own in-memory SQLite database, so running it on staging would test
      nothing the dev machine doesn't.
- [ ] Dev, staging and prod are on the same commit — `git rev-parse --short HEAD`
      on each. Write them down; the hostnames are near-identical and a
      PII exposure once survived ten days because a fix logged as "done on
      prod" had only been verified on staging.
- [ ] `systemctl cat turnushjelper | grep timeout` shows `--timeout 300`.
      **Forventet:** present. Without it, strekliste generation is killed at
      gunicorn's 30 s default and the browser shows "En feil oppstod under
      generering", which means *the request died*, not that anything was
      reported.
- [ ] Take the favorites snapshot (one-liner above) and paste it somewhere you
      can compare against later. This is the reference for Parts 3 and 4.
- [ ] Run the orphan check. **Forventet:** empty. If it is not empty *before*
      you start, note the rows so you don't blame the import for them.

---

## Part 1 — Dry run, before the real files arrive

Do this once, well ahead of time. The point is that the first time you touch
the import flow is not the same day the real file lands.

- [ ] Make a throwaway copy of the current set's JSON (recipe in Phase A §A2.2
      — `R26COPY`).
- [ ] Create it through **Admin → Opprett turnussett** with **Bruk eksisterende
      filer** ticked and **Sett som aktivt turnussett** unticked.
      **Forventet:** green `Validering OK: N av N turnuser godkjent`.
- [ ] Upload a turnusnøkkel `.xlsx` to it. **Forventet:** kompdag badges show
      numbers on the linje buttons.
- [ ] Activate it, then activate the real set again. **Forventet:** the switch
      works both ways and the site serves the right data after a restart.
- [ ] Delete the throwaway set. **Forventet:** the confirm dialog shows the
      impact counts, and the deletion only goes through when you type the year
      identifier back.
- [ ] `rm -rf turnusdata/r26copy`.

---

## Part 2 — Import the new set (staging)

> **Create it inactive.** Never tick "Sett som aktivt turnussett" on the create
> form. A set with no innplassering, no turnusnøkkel and no strekliste-PNGs
> breaks Min tur, kompdag badges and shift images for every user at once, from
> the moment it goes active.

### 2.1 Upload and validation

- [ ] **Admin → Opprett turnussett.** Fill in Navn and Årsidentifikator (e.g.
      `R27`), **untick "Bruk eksisterende filer"**, choose the Timeskjema file.
      **Note:** the checkbox is ticked by default, and leaving it ticked while
      selecting a file silently ignores the file and validates whatever JSON is
      already on disk.
- [ ] Watch the log in a second terminal: `tail -f app/logs/turnus_import.log`.
- [ ] Submit. **Forventet:** green `Validering OK: N av N turnuser godkjent`
      and an INFO line in the log.
      **On failure:** a red flash listing the problems, and *nothing written to
      disk or DB*. Fix the source or ask for a new export — **never hand-edit
      the schedule JSON to get past the validator.**
- [ ] If you supplied a verification PDF: the diff-approval page appears.
      **Forventet:** differences are normal — the two sources can be different
      planning revisions (R26's two sources differed in 20 of ~2 394 day-cells).
      Adjudicate them; do not expect equality and do not treat a diff as a
      failed import.
- [ ] Check the set exists and is **inactive** (turnus-sets one-liner above).

### 2.2 Turnusnøkkel (calendar dates + kompdager)

- [ ] Upload `turnusnøkkel_{RXX}_org.xlsx` on the set's row. The filename must
      be exact — Norwegian `ø`, `_org` suffix, uppercase year id.
- [ ] **Forventet:** `/admin/turnusnokkel-status/<id>` reports
      `has_template: true`.
- [ ] Open turnusliste for the new set (via the year switcher, see Part 3).
      **Forventet:** kompdag badges show **numbers**, not `–`, and the numbers
      **differ between linjer**. All-zero or all-identical means the counting
      never saw the schedule properly — stop and check before going further.

### 2.3 Innplassering (Min tur)

- [ ] Import the innplassering PDF on the set's row.
      **Forventet:** the record count matches the number of rullenummer you
      expect for the rutetermin.
- [ ] `venv/bin/python scripts/check_rullenummer_duplicates.py`
      **Forventet:** no duplicates.
- [ ] Confirm the PDF landed in `instance/protected/`, **not** under
      `app/static/` — nothing under `app/static/` is authenticated.

### 2.4 Strekliste PNGs

- [ ] Upload the streker PDF for the set.
- [ ] Generate **from the CLI, not the admin button** — the admin route runs
      synchronously and occupies one of two workers for its whole duration:

      ```bash
      nohup venv/bin/python -c "import app.utils.pdf.strekliste_generator as sg; r=sg.generate_all_images('r27', force=True); print(r['total'], len(r['generated']), r['errors'][:5])" > /tmp/strekliste.log 2>&1 &
      ```

      **Forventet:** the printed error list is empty. Per-shift failures do not
      abort the run — the admin button throws them away, this form prints them.
- [ ] `ls turnusdata/r27/streklister/png | wc -l`
      **Forventet:** one PNG per shift in the set. A wildly different number
      means the wrong PDF edition (for r26 the correct count is **423**; 492 is
      the wrong edition).
- [ ] Open **two** generated PNGs side by side with the source PDF.
      **Forventet:** the hour ruler lines up with the bars. Stale PNGs from a
      previous edition look perfectly correct on their own — comparing against
      the PDF is the only way to catch a swap that was never regenerated.

### 2.5 Restart

- [ ] `sudo systemctl restart turnushjelper`
      The cache is per-process and there are two gunicorn workers, so an
      invalidation triggered by your admin request only ever reaches the worker
      that served it. Restarting is the only thing that clears both.

---

## Part 3 — User data must not get mixed up

Run this **while the old set is still active**, using two accounts in two
separate browsers (or one normal + one private window) — call them **A** and
**B**. Use test accounts, not real users' accounts.

- [ ] A favorites three shifts in the old set; B favorites three *different*
      shifts.
      **Forventet:** each sees only their own list on `/favorites`, and only
      their own stars/pills on `/turnusliste`.
- [ ] A reorders their list.
      **Forventet:** B's order is unchanged after reloading B's page.
- [ ] A switches to the new set with the year switcher and favorites one shift
      there, then switches back to the old set.
      **Forventet:** the old-set list is exactly as it was — the new favorite
      does not appear there, and nothing was renumbered.
- [ ] Run the favorites snapshot one-liner.
      **Forventet:** identical to the Part 0 snapshot except for the rows you
      deliberately added, and the new favorite is counted under the *new*
      set's id.
- [ ] **Min tur:** log in as a user whose rullenummer is in the new
      innplassering.
      **Forventet:** they see **their own** shift. A user who is not in the
      innplassering must see no Min tur at all — never somebody else's.
- [ ] Make a søknadsskjema choice in one set, switch to the other.
      **Forventet:** the choice does not follow along.

---

## Part 4 — Activation

- [ ] Re-run the favorites snapshot and keep it.
- [ ] **Admin → Administrer turnussett →** activate the new set.
- [ ] `sudo systemctl restart turnushjelper`.
- [ ] Re-run the favorites snapshot.
      **Forventet: byte-identical to the line before.** Activation only flips
      `is_active`; it must never move, clear or renumber a single favorite. Any
      change here is a stop-everything finding.
- [ ] Log in as A.
      **Forventet:** the favorites list in the new set is **empty**, and
      `/import-favorites` offers the old set as a source. This is by design —
      favorites are per set and users carry them over themselves.
- [ ] Use `/import-favorites` as A. **Forventet:** the preview shows matched
      shifts, confirming adds them, and running it a second time adds nothing
      new.
- [ ] Switch back to the old set with the year switcher.
      **Forventet:** A's original old-set favorites are still there, in their
      original order.
- [ ] Check the "Min tur" nav item.
      **Forventet:** it appears — but give it up to a minute. The nav flag is
      cached 60 s per user and is not invalidated by activation, so a brief
      absence right after the switch is known and not worth chasing.
- [ ] Run the orphan check one-liner. **Forventet:** still empty.

---

## Part 5 — Favorites: add, remove, sort

Run against the newly active set. Also worth re-running on its own after any
change to the favorites code — it does not depend on an import.

**Adding**

- [ ] Add a favorite with the star on `/turnusliste`.
      **Forventet:** the pill shows the next free number, and the star, the
      `/favorites` page and the compare modal on `/oversikt` all agree.
- [ ] Double-click the star fast, twice in a row.
      **Forventet:** no duplicate entry, no error page.

**Removing**

- [ ] Remove a favorite from the *middle* of the list.
      **Forventet:** the remaining pills are numbered `1, 2, 3 …` with no gap.
      A skipped number is the classic regression here.

**Sorting**

- [ ] Move an item up, then down.
      **Forventet:** the change survives a page reload.
- [ ] Look at the first and last item.
      **Forventet:** the top item's ↑ button and the bottom item's ↓ button are
      disabled.
- [ ] Click the `#N` pill and type a position: `1`, then the last number, then
      a number larger than the list, then `0`, then a word.
      **Forventet:** the first two move it; a too-large number puts it last; `0`
      and a word are rejected and change nothing.
- [ ] Log out and back in. **Forventet:** identical order.
- [ ] Open `/favorites` in two tabs, reorder in tab 1, reload tab 2.
      **Forventet:** tab 2 shows the new order. Then press Back in tab 2 —
      **Forventet:** still the new order, never the old one.

**Two-worker check (staging/prod only — cannot be done on the dev machine)**

- [ ] Reorder the list, then request the page ~20 times in a row and compare
      the pill order each time (browser reload works; `curl` with the session
      cookie is faster).
      **Forventet:** every response shows the same order. A response that
      alternates between two orders means a per-user page cache has been
      reintroduced — that caused two shipped bugs and was deliberately removed.

---

## Part 6 — Production cutover (short smoke test)

Only after Parts 2–5 pass on staging. Same import steps on
`turnushjelper-1`, then:

- [ ] Favorites snapshot **before** activation, and again **after** activation
      + restart. **Forventet:** identical.
- [ ] Kompdag badges show numbers.
- [ ] PNG count matches the shift count; two images spot-checked against the
      PDF.
- [ ] One real-ish run as a test user: add a favorite, move it, reload.
- [ ] Orphan check: empty.
- [ ] **Write down host + SHA + date.** Not just the date.

---

## Part 7 — Rollback and red flags

**To back out an activation:** reactivate the previous set and restart the
service. Users' old-set favorites were never touched, so they come straight
back.

**Do not delete the new set** once users have started favoriting in it —
`delete_turnus_set` permanently removes every user's `Favorites`,
`SoknadsskjemaChoice` and `Innplassering` rows for that set. The delete form
shows the blast radius (number of favorites and how many users they belong to);
read those numbers before typing the identifier.

**Stop immediately if:**

- validation fails and the proposed fix is editing the schedule JSON by hand
- kompdag badges show `–` after the turnusnøkkel was uploaded
- the PNG count is far off the shift count, or images don't line up with the PDF
- the favorites snapshot changes across activation
- the orphan check returns rows after an import that only *added* a set
- a user reports seeing someone else's shift under Min tur

---

## What is already covered by automated tests

Don't spend manual time re-checking these; run `venv/bin/pytest -q` on the dev
machine instead (Phase A §A1 gives the per-area commands).

| Area | Test file |
|---|---|
| Reorder endpoints: up/down, boundaries, position clamping, renumbering, legacy duplicate indices | `tests/test_favorites_reorder.py` |
| Favorites isolation across users and across turnus sets; activation leaves favorites untouched | `tests/test_favorites_isolation.py` |
| Refresh keeps favorites on renamed shifts; orphans them on removed shifts | `tests/test_turnus_refresh_favorites.py` |
| No per-user page caching / stale favorites | `tests/test_view_freshness.py` |
| Delete impact counts + typed confirmation | `tests/test_turnus_set_delete_guard.py` |
| Validator, committed R25/R26 data integrity | `tests/test_scraper_validator.py`, `tests/test_data_integrity.py` |
| Kompdag reference counts (OSL_01 R26 = `[4, 1, 3, 2, 2, 4]`) | `tests/test_kompdag_routes.py` |
| Strekliste geometry and atomic PNG swap | `tests/test_strekliste_geometry.py`, `tests/test_strekliste_atomic_swap.py` |
| PII files stay out of `app/static/` | `tests/test_protected_files.py` |

The manual steps above are the ones that cannot be automated here: real source
files, real PDFs and image alignment, the two-worker cache behaviour, and the
browser-side reorder UI.
