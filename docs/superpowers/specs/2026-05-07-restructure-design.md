# Restructure Design — Pre-Beta Cleanup

**Date:** 2026-05-07  
**Branch:** `restructure` (created from `development` before any changes)  
**Goal:** Restore oversight of the codebase and make it safe to change before 50-user beta in fall 2026.

---

## Overview

Four phases, executed in order. Each phase is independently releasable. The test suite must stay green throughout.

| Phase | Work | Risk |
|---|---|---|
| 1 | Site map document | Zero |
| 2 | Bug & performance fixes | Low |
| 3 | Split large route files | Moderate |
| 4 | CSRF audit | Separate task |

---

## Phase 1: Site Map

Write `docs/SITE_MAP.md` — a single reference document covering every route in the app.

Each entry includes:
- URL and HTTP method(s)
- Login required / admin only
- What it renders or returns
- What data it reads and writes

No code changes. This is the document to consult when you can't remember what a route does.

---

## Phase 2: Bug & Performance Fixes

Fix 2.1 must go first — the suite must be green before any further changes. The remaining 6 fixes (2.2–2.7) are independent and can be done in any order. The test suite must pass after each fix.

### 2.1 Fix failing test

`tests/test_auth_service.py::TestAuthorizedEmails::test_add_and_check` is currently failing. Fix this first so the suite is green before any further changes.

### 2.2 Fix tour state inconsistency (most important)

**Problem:** `inject_tour_state()` in `app/__init__.py` reads tour flags from `session`, but `DBUser` already has 6 persistent DB columns for this. The session reads make tour state reset whenever a user clears cookies or logs in from a new device.

**Name mapping** — only one key differs between session and DB column:

| Context processor reads | DB column |
|---|---|
| `session.get('has_seen_tour', 0)` | `has_seen_turnusliste_tour` ← different name |
| `session.get('has_seen_favorites_tour', 0)` | `has_seen_favorites_tour` |
| `session.get('has_seen_mintur_tour', 0)` | `has_seen_mintur_tour` |
| `session.get('has_seen_compare_tour', 0)` | `has_seen_compare_tour` |
| `session.get('has_seen_welcome', 0)` | `has_seen_welcome` |
| `session.get('has_seen_soknadsskjema_tour', 0)` | `has_seen_soknadsskjema_tour` |

**Fix:** Read from the DB columns instead of session, using the correct column names above. Cache the full result dict per user with key `tour_state_{user_id}`, TTL 60 seconds. Invalidate the cache key any time a tour-completion endpoint writes to `DBUser`.

No migration needed — the columns already exist.

### 2.3 Cache `has_min_turnus`

**Problem:** The context processor fires 3 DB queries on every page load (queries `DBUser`, `TurnusSet`, `Innplassering`) to compute `has_min_turnus`.

**Fix:** Cache the result with key `has_min_turnus_{user_id}`, TTL 60 seconds. Invalidate when admin writes innplassering for that user.

After fixes 2.2 and 2.3, the context processor should hit the DB at most once per 60 seconds per user, not on every request.

### 2.4 Fix N+1 in `update_favorite_order`

**File:** `app/services/favorites_service.py`

Current code loads all favorites then re-queries each one individually to update `order_index`. Use the already-loaded objects directly — no second query needed.

### 2.5 Fix O(n²) in favorites route

**File:** `app/routes/shifts.py` line 432

The `in` check against `fav_order_lst` (a list) runs inside a loop at line 432, making it O(n²). Convert `fav_order_lst` to a set before the loop.

### 2.6 Add DB indexes

New Alembic migration adds 3 indexes:

| Index name | Table | Columns |
|---|---|---|
| `ix_favorites_user_ts` | `favorites` | `(user_id, turnus_set_id)` |
| `ix_innplassering_ts_rullenr` | `innplassering` | `(turnus_set_id, rullenummer)` |
| `ix_user_activity_timestamp` | `user_activity` | `timestamp` |

Apply with `alembic upgrade head`.

### 2.7 Defer JS and remove duplicate meta tags

**File:** `app/templates/base.html`

- Add `defer` to Bootstrap JS and driver.js `<script>` tags
- Move the inline Bootstrap event listener block to just before `</body>` (it must run after deferred scripts load)
- Remove duplicate `<meta charset>` and `<meta viewport>` tags (currently appear twice)

---

## Phase 3: Code Split

Split the two oversized route files into sub-packages. **Blueprint names and all route URLs stay identical** — nothing in templates or JS needs to change.

### 3.1 Split `app/routes/shifts.py` (1450 lines)

Create `app/routes/shifts/` package:

```
app/routes/shifts/
    __init__.py         # creates Blueprint("shifts"), imports all sub-modules to register routes
    index.py            # GET /  → redirect to landing page
    turnusliste.py      # GET /turnusliste
                        # GET /switch-year/<int:turnus_set_id>
    oversikt.py         # GET /oversikt  (compare/statistics view)
    favorites.py        # GET /favorites
                        # GET /import-favorites
    mintur.py           # GET /mintur
                        # GET /mintur/export_ical
    turnusnokkel.py     # GET /turnusnokkel/<int:turnus_set_id>/<turnus_name>
    soknadsskjema.py    # GET+POST /soknadsskjema
```

The `before_request` hook, `_turnusliste_cache_key()`, and `_classify_shift_type()` helpers live in `__init__.py`.

**Dead code to remove in Phase 3:** `display_shift` was intentionally deleted in commit `bffe030` during a cleanup. Three orphaned pieces were left behind and should be removed together:
1. `api.py` — `GET /api/js_select_shift` endpoint (references the deleted route)
2. `app/static/js/modules/shift-selection.js` — calls `/api/js_select_shift` on `.clickable-row` click
3. `main.js` — imports and instantiates `ShiftSelection`

No template has a `.clickable-row` element, so none of this code ever runs. Remove all three as part of Phase 3.

### 3.2 Split `app/routes/admin.py` (1096 lines)

Create `app/routes/admin/` package:

```
app/routes/admin/
    __init__.py       # creates Blueprint("admin", url_prefix="/admin"), imports sub-modules
    dashboard.py      # GET /admin/dashboard, GET /admin/activity
    users.py          # user create/edit/delete/detail routes
    turnus.py         # turnus set CRUD, PDF strekliste upload
    employees.py      # stub/employee management
    emails.py         # authorized emails management
```

### 3.3 `app/routes/api.py` — no change

830 lines but each endpoint is short and self-contained. Splitting is lower priority than the two above.

### Safety procedure for Phase 3

1. Run `venv/bin/pytest` — must be green before starting
2. Create the package directory and `__init__.py`
3. Move routes one file at a time, running `pytest` after each move
4. Do a manual smoke test of the moved routes in the dev server before committing

---

## Phase 4: CSRF Audit (separate task)

Scoped as a dedicated follow-on task, not part of this implementation. Rushing CSRF alongside a restructure risks introducing subtle breakage in every form and `fetch()` call.

When that task runs it will cover:
- Enable Flask-WTF global CSRF protection
- Add CSRF tokens to all server-rendered forms
- Add `X-CSRFToken` header to all JS `fetch()` POST calls
- Verify every mutation endpoint is protected

---

## What is NOT in scope

- Splitting `api.py`
- Refactoring service layer
- Template restructure
- Any new features
- Any changes to the `feature/high-traffic-mode` branch

---

## Definition of done

- [ ] `docs/SITE_MAP.md` written and committed
- [ ] Test suite fully green (0 failures)
- [ ] Tour state reads from DB, not session; result cached
- [ ] `has_min_turnus` cached; context processor no longer queries DB on every request
- [ ] N+1 and O(n²) issues fixed
- [ ] DB indexes migration created and applied
- [ ] `base.html` JS deferred, duplicate meta tags removed
- [ ] `shifts.py` split into package, all routes working
- [ ] `admin.py` split into package, all routes working
- [ ] All changes on `restructure` branch
