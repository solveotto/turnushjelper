# TODO — Remaining fixes from the 2026-07-12 codebase review

This document is an implementation brief for a follow-up agent. A full review of the
Python codebase was done on 2026-07-12 on branch `experimental/fabel_check`. Fifteen
fixes were already applied and verified (cache invalidation on turnus refresh, reorder
endpoints, open redirect, `verify_email` auto-login bypass, shift_matcher IndexError,
shift_stats summary-row bug + regenerated stats JSONs, and several smaller guards).
**This file only covers what was NOT implemented**, split into:

- **Part 1** — ready to implement, no decision needed.
- **Part 2** — do NOT implement until Solve (the project owner) has decided; each item
  lists the options to present.
- **Part 3** — optional small cleanups.

> **Status (2026-07-12 evening):** Part 1 is **DONE** (commit `c8f1aaa`,
> 254 passed). Task 5 is **DECIDED: Option A — implement it** (see the task).
> Task 6 is **CLOSED**: Solve decided to keep the søknadsskjema as it is; no
> change, no warning banner. Task 7 remains open (verification-first task).

## Ground rules — read before touching anything

1. Read `CLAUDE.md` first and follow it exactly (three-layer architecture,
   raw-SQLAlchemy session pattern, Norwegian UI text / English code).
2. `python` is **not** on PATH in this environment. Use `venv/bin/python` and
   `venv/bin/pytest`.
3. Baseline: `venv/bin/pytest -q` passes with **249 passed**. Run it before you start
   and after every task. Any new failure you introduce must be fixed before moving on.
4. Read every file you edit *before* editing it. Line numbers below were correct on
   2026-07-12 and may have drifted — locate code by the quoted snippets, not by line
   number alone.
5. Do **not**:
   - regenerate `turnus_stats_*.json` files (already regenerated; only regenerate if
     `tests/test_shift_stats.py::test_stored_stats_match_fresh_computation` tells you to),
   - change kompdag counting rules (`app/utils/kompdag_utils.py` — reference counts are
     asserted in `tests/test_kompdag_routes.py`),
   - change strekliste PNG geometry (`app/utils/pdf/strekliste_generator.py` — recently
     calibrated, covered by `tests/test_strekliste_geometry.py`),
   - commit or push unless Solve asks.

---

## Part 1 — Ready to implement

### Task 1: Versioned view-cache keys (per-user page caches survive a turnus refresh)

**Priority: highest of the remaining items.**

**Problem.** The rendered pages `/turnusliste` and `/oversikt` are cached per user with
keys `view/turnusliste/{user_id}/{ts_id}` (120 s) and `view/oversikt/{user_id}/{ts_id}`
(300 s). When an admin re-imports a turnus set, `invalidate_turnus_cache()` in
`app/utils/df_utils.py` drops the *data* caches, but the per-user *page* caches cannot
be dropped because Flask-Caching's SimpleCache cannot enumerate keys (one key per user,
users unknown). Users can see up to 120–300 s of stale rendered HTML after a refresh.

**Fix design: a per-turnus-set generation counter baked into the page-cache key.**
Bumping the counter changes every user's key at once, orphaning the old entries (they
expire naturally; `CACHE_THRESHOLD: 300` in `app/extensions.py` bounds memory).

**Steps.**

1. In `app/utils/df_utils.py`, extend the existing helper and add two new ones:

   ```python
   def get_turnus_cache_generation(turnus_set_id):
       """Monotonic counter bumped on every turnus-data invalidation.

       Baked into the per-user view-cache keys so bumping it invalidates all
       users' cached pages at once (SimpleCache cannot enumerate keys).
       """
       from app.extensions import cache
       return cache.get(f"turnus_gen_{turnus_set_id}") or 0


   def turnusliste_view_key(user_id, turnus_set_id):
       gen = get_turnus_cache_generation(turnus_set_id)
       return f"view/turnusliste/{user_id}/{turnus_set_id}/g{gen}"


   def oversikt_view_key(user_id, turnus_set_id):
       gen = get_turnus_cache_generation(turnus_set_id)
       return f"view/oversikt/{user_id}/{turnus_set_id}/g{gen}"
   ```

   And inside `invalidate_turnus_cache()` add, after the two existing deletes:

   ```python
   gen_key = f"turnus_gen_{turnus_set_id}"
   cache.set(gen_key, (cache.get(gen_key) or 0) + 1, timeout=0)  # 0 = no expiry
   ```

2. **CRITICAL:** every construction of these key strings must go through the two new
   helpers — a single missed call site silently breaks invalidation (mismatched keys).
   Find all of them with:

   ```
   grep -rn "view/turnusliste\|view/oversikt" app/
   ```

   As of 2026-07-12 the call sites are:
   - `app/routes/shifts/turnusliste.py` — `_turnusliste_cache_key()` (keep the
     `_flashes`/uuid bypass branch exactly as it is; only replace the normal-key return),
     and `switch_user_year()` which calls `cache.delete(_turnusliste_cache_key())` /
     `cache.delete(_oversikt_cache_key())` — these keep working unchanged since the
     key functions themselves change.
   - `app/routes/shifts/oversikt.py` — `_oversikt_cache_key()`.
   - `app/routes/api.py` — `_build_favorites_payload()` inside `toggle_favorite`
     (two `cache.delete(...)` lines), the two `cache.delete(...)` blocks added to
     `move_favorite` and `set_favorite_position`, and one delete in `mark_tour_seen`.
     All of these must call the new helpers instead of formatting strings inline.

   Note the ID types: routes use `current_user.get_id()` (a **string**), api handlers
   use the same. The helper just interpolates, so passing the string through is fine —
   but be consistent: always pass what the route's key function would have used,
   otherwise `"view/turnusliste/5/…"` vs `"view/turnusliste/None/…"` mismatches occur.

3. Verify:
   - `venv/bin/pytest -q` (especially `tests/test_oversikt_cache.py`,
     `tests/test_api_routes.py`).
   - Add a test in `tests/test_oversikt_cache.py`: request `/oversikt` twice (second
     hit cached), call `df_utils.invalidate_turnus_cache(ts_id)`, request again and
     assert the view function ran again (the existing tests in that file show how the
     cache is asserted — mirror their pattern).

**Pitfall.** Do not "improve" this by trying `cache.delete_many` with wildcards —
SimpleCache has no wildcard support. Do not drop the uuid flash-bypass branch.

---

### Task 2: `turnusnokkel_view` returns 500 for an unknown turnus set — make it 404

**Problem.** In `app/routes/shifts/turnusnokkel.py`:

```python
turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
year_identifier = turnus_set["year_identifier"]
```

`get_turnus_set_by_id` returns `None` for an unknown id, so
`/turnusnokkel/99999/OSL_01` raises `TypeError` → 500.

**Fix.** Add immediately after the lookup:

```python
if not turnus_set:
    abort(404)
```

and add `abort` to the `from flask import ...` line at the top of the file.

**Verify.** Add a route test (pattern: `tests/test_kompdag_routes.py` already tests
turnusnokkel routes — put it there or in a new file):

```python
def test_turnusnokkel_unknown_set_404(client, sample_user):
    login_user(client, sample_user["username"], sample_user["password"])
    resp = client.get("/turnusnokkel/99999/OSL_01")
    assert resp.status_code == 404
```

---

### Task 3: Enforce rullenummer uniqueness on registration/stub activation

**Problem.** `users.rullenummer` has no unique constraint, and two write paths set it
without checking for collisions (unlike `update_user`, which checks):

1. `activate_stub_user()` in `app/services/user_service.py`:
   ```python
   if rullenummer and not user.rullenummer:
       user.rullenummer = rullenummer
   ```
2. `create_user_with_email()` in the same file (takes a `rullenummer` kwarg).

If a registering user types a rullenummer that already belongs to someone else,
`get_innplassering_for_user()` (which joins on the rullenummer *string*) will show them
**another person's shift assignment** in mintur/minside.

**Fix.**

1. In `activate_stub_user`, replace the snippet above with:

   ```python
   if rullenummer and not user.rullenummer:
       taken = (
           db_session.query(DBUser)
           .filter(DBUser.rullenummer == str(rullenummer), DBUser.id != user_id)
           .first()
       )
       if taken:
           return False, "Rullenummeret er allerede i bruk av en annen bruker", None
       user.rullenummer = str(rullenummer)
   ```

2. In `create_user_with_email`, before constructing `new_user`, add:

   ```python
   if rullenummer:
       existing_rnr = (
           db_session.query(DBUser)
           .filter_by(rullenummer=str(rullenummer))
           .first()
       )
       if existing_rnr:
           return False, "Rullenummeret er allerede i bruk av en annen bruker", None
   ```

3. Check how `app/routes/registration.py` handles the failure path (it already flashes
   `message` on `success == False` — confirm nothing else is needed).

**Verify.** Add tests in `tests/test_user_service.py`: create user A with
rullenummer "12345", then `activate_stub_user(..., rullenummer="12345")` on a stub B →
expect `(False, ...)` and B's rullenummer unchanged. Run the full suite.

**Out of scope (do not do without asking):** adding a DB-level unique constraint via
Alembic. Production data may already contain duplicates; that migration needs a data
audit first.

---

### Task 4: Narrow the three `cache.clear()` calls (do this AFTER Task 1)

**Problem.** Three places nuke the entire application cache — including every
`turnus_data_*` entry, forcing expensive JSON reloads for all users — when they only
need to evict one user's cached pages/flags:

- `app/routes/registration.py` — `verify_email()`: `cache.clear()  # evict any stale cached pages...`
- `app/routes/admin/employees.py` — `reset_to_stub()`: `cache.clear()  # evict stale data-tour-seen...`
- `app/routes/admin/dashboard.py` (~line 68): `cache.clear()  # evict all cached pages...`
  — **read this file first**; it was not modified in the review and the surrounding
  context must be understood before changing it.

**Fix.** Replace each `cache.clear()` with targeted deletes for the affected user id
`uid` (and their username where relevant):

```python
from app.utils import df_utils, turnus_helpers

ts = turnus_helpers.get_user_turnus_set()  # or the active set, depending on context
ts_id = ts["id"] if ts else "none"
cache.delete(df_utils.turnusliste_view_key(uid, ts_id))
cache.delete(df_utils.oversikt_view_key(uid, ts_id))
cache.delete(f"tour_state_{uid}")
cache.delete(f"has_min_turnus_{uid}")
cache.delete(f"user_{username}")
```

Adjust per call site (e.g. `verify_email` runs unauthenticated — get the user id from
`user_data["id"]`; `reset_to_stub`/dashboard know the target user id). If a call site's
purpose is unclear after reading it, leave that one as `cache.clear()` and note why.

**Verify.** Full suite; manually reason through each site: "which cached values does
this action stale?" and confirm each is covered by a delete.

---

## Part 2 — Needs a decision from Solve first. Present options, do not implement.

### Task 5: Unauthenticated identity lookups `check_rullenummer` / `check_medlemsnummer`

> **DECIDED (Solve, 2026-07-12): Option A — implement it now.** Return only
> `{found: bool}` (plus `name_match` when the caller supplies a name); never
> echo name/seniority/ans_dato. Update the registration frontend and the tests
> in the same change, per the notes below.

`app/routes/api.py` exposes, without login (rate-limited 30/hour/IP):

- `GET /api/check-rullenummer?rullenummer=NNNNN` → `{found, name, seniority_nr, ans_dato}`
- `GET /api/check-medlemsnummer?medlemsnummer=NNNNN` → `{found, rullenummer, name}`

Both are used by the self-registration form (the name echo lets the registrant confirm
identity), but they let anyone slowly enumerate employee names, seniority numbers and
hire dates. Options to present:

- **A (minimal):** return only `{found: bool}` plus `name_match` when the caller
  supplies a name — never echo name/seniority/ans_dato. Requires updating the
  registration frontend: grep `check-rullenummer\|check-medlemsnummer` under
  `app/static/js/` and `app/templates/` and adjust what the UI displays.
- **B (middle):** require the medlemsnummer *and* a surname to match before returning
  the name.
- **C (status quo):** accept the exposure as a registration-UX tradeoff; optionally
  tighten the limiter (e.g. `10 per hour`).

If Solve picks A or B: the JSON response shape changes → update the JS in the same
change, and extend `tests/test_registration_routes.py` / `tests/test_api_routes.py`.

### Task 6: Søknadsskjema silently truncates favorites beyond 71

> **CLOSED (Solve, 2026-07-12): keep the søknadsskjema exactly as it is.**
> No warning banner, no layout change. Do not implement anything here.

`app/routes/shifts/soknadsskjema.py` builds a fixed 71-row table (`Alt.1`–`Alt.71`,
matching the union's paper form). A user with more than 71 favorites gets rows 72+
silently dropped from the generated docx/PDF. Options:

- **A:** show a warning banner on the page and flash on download when
  `len(fav_order_lst) > 71` ("Skjemaet har plass til 71 turer; favoritter utover dette
  tas ikke med."). No layout change. — *recommended, smallest.*
- **B:** grow the table dynamically past 71 rows. Only valid if the union accepts
  longer forms — that is Solve's call, not a code decision.

### Task 7: Verify the 7.fører `linjenummer` parsing in the innplassering scraper

`_parse_data_row_7forer()` in `app/utils/pdf/innplassering_scraper.py` takes
`texts[0]` as the linjenummer. But per the module docstring the 7.fører columns are
`linjenr | Ans | Fornavn | Etternavn | Rullenr | Tur | L` — the trailing **L** column
might be the real linje *within the target Tur*, in which case 7th drivers get the
wrong linje stored, and mintur shows them the wrong highlighted column and kompdag
count.

This is a **verification task first**:

1. Open `app/static/turnusfiler/r26/innplassering_R26.pdf` with pdfplumber
   (`venv/bin/python`, use `page.extract_words(x_tolerance=3, y_tolerance=2)`), find the
   `7.fører` section, and print a few raw data rows.
2. Compare `texts[0]` vs the trailing `L` value against what those drivers should have
   (ask Solve if ground truth is unclear).
3. Only if `texts[0]` is confirmed wrong: change the parser to read the `L` column,
   then tell Solve the innplassering PDF must be **re-imported** via the admin UI for
   the DB records to be corrected (the scraper only runs at import time).

---

## Part 3 — Optional cleanups (low value, zero risk; batch them if done at all)

1. **Stale module comment** in `app/utils/shift_stats.py` near the top:
   `'- Fridays that goes over 2 hours into saturay counts as weekend days.'` — the
   implemented rule is "Friday hours after 17:00 count as weekend". Fix the comment
   (and its typo) to match the code.
2. **Dead code:** `update_favorite_order()` in `app/services/favorites_service.py`
   has no callers (only the `db_utils` re-export). Either delete it (also remove it
   from the import list in `app/utils/db_utils.py`) or leave it — it was already made
   safe with an `ORDER BY`. If deleting, grep `update_favorite_order` across the repo
   including `tests/` first.
3. **`get_max_ordered_index()`** (same file): when called with `turnus_set_id=None`
   and no active set exists, it returns the max across *all* sets. Add `return 0` in
   the `else` branch when there is no active set, mirroring `get_favorite_lst`.
4. **Legacy fallbacks in `app/utils/turnusnokkel_gen.py`** (`get_turnusnøkkel_excel_data`,
   `generate_all_turnus_nokkel`) reference hardcoded R25 paths that no longer exist and
   are only reachable from dead/legacy paths. Candidates for deletion — but check for
   callers first (`grep -rn "TurnusnokkelGen\|generate_all_turnus_nokkel" app/ tests/`).

---

## Definition of done (per task)

- `venv/bin/pytest -q` → 249+ passed, 0 failed (count grows with new tests).
- New behavior covered by at least one test where the task says so.
- No changes outside the files the task names, unless a grep proved another call site.
- Part 2 tasks: a short written summary of options given to Solve, no code changes
  until an option is chosen.
