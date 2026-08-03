# Ny turnussett — manuell sjekkliste

The two things that must not break: **importing a new turnusset**, and
**favorites (adding, sorting, and staying the right user's)**. A new rutetermin
arrives once or twice a year, always shortly before it is needed, so this
checklist exists to make the import boring.

Run it on **staging (`turnushjelper-2`) first**, then the short smoke path on
**production (`turnushjelper-1`)**. Every step has a **Forventet** line — if
what you see differs, stop and investigate rather than continuing.

Related guides:
- `CREATING_TURNUS_SETS.md` — *how* the import works, form fields, artifacts
- `TESTING_TURNUS_SETS.md` — dev-machine verification of the validator/scraper
- `.claude/skills/import-rutetermin/SKILL.md` — the step-by-step ingestion run

---

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

- [ ] Make a throwaway copy of the current set's JSON (recipe in
      `TESTING_TURNUS_SETS.md` §2.2 — `R26COPY`).
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
machine instead.

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
