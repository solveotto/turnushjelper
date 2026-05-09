# Pre-Beta Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore codebase oversight and eliminate known bugs/performance issues before 50-user beta, via a site map, 7 targeted fixes, and splitting two oversized route files.

**Architecture:** All changes on the `restructure` branch (from `development`). Phases are sequential: doc → fixes → split. The test suite (78 tests, run via `venv/bin/pytest`) must stay green after every task. Blueprint names and route URLs do not change — nothing in templates or JS breaks.

**Tech Stack:** Python 3.12, Flask 3.0, SQLAlchemy 2.0, Alembic (migrations in `migrations/versions/`), Bootstrap 5, vanilla JS modules.

---

## Task 1: Create the `restructure` branch

**Files:** none

- [ ] **Step 1: Create branch from `development`**

```bash
git checkout development
git checkout -b restructure
```

- [ ] **Step 2: Verify**

```bash
git branch --show-current
```
Expected output: `restructure`

---

## Task 2: Write the site map

**Files:**
- Create: `docs/SITE_MAP.md`

- [ ] **Step 1: Create the file with full content**

```markdown
# Site Map — Turnushjelper

Generated 2026-05-08. Update whenever routes are added or removed.

---

## Auth blueprint (`app/routes/auth.py`) — no URL prefix

| Method | URL | Login required | What it does |
|---|---|---|---|
| GET/POST | `/login` | No | Login form. POST validates credentials, writes tour flags to session, redirects to `/`. |
| GET | `/logout` | Yes | Clears session, logs activity event, redirects to `/login`. |
| GET/POST | `/forgot-password` | No | Request password reset. POST sends reset email via Mailgun. |
| GET/POST | `/reset-password/<token>` | No | Reset password using token from email. |

---

## Registration blueprint (`app/routes/registration.py`) — no URL prefix

| Method | URL | Login required | What it does |
|---|---|---|---|
| GET/POST | `/register` | No | Self-registration form (rate-limited: 10 POST/hour). Checks `AuthorizedEmails` for rullenummer, creates stub user, sends verification email. |
| GET | `/verify/<token>` | No | Activates account via email token; sets `email_verified=1` on `DBUser`. |
| GET/POST | `/resend-verification` | No | Resends the verification email for an unverified account. |

---

## Shifts blueprint (`app/routes/shifts.py`) — no URL prefix

| Method | URL | Login required | What it does |
|---|---|---|---|
| GET | `/` | Yes | Redirects to landing page configured by `AppConfig.LANDING_PAGE` (default: `turnusliste`). |
| GET | `/turnusliste` | Yes | Main turnus table. Renders all shifts for the user's selected turnus set. Heavy page — cached per user+turnus_set. |
| GET | `/switch-year/<int:turnus_set_id>` | Yes | Changes the user's selected turnus set in session; redirects to `/turnusliste`. |
| GET | `/favorites` | Yes | Shows the user's favorited shifts with weekly calendar view. |
| GET | `/oversikt` | Yes | Compare statistics across multiple turnus years. Reads from multiple `TurnusSet` DataframeManagers. |
| GET | `/mintur` | Yes | Personalised view for the user's own shift based on their `Innplassering` record. Redirects to `/turnusliste` if no innplassering. |
| GET | `/mintur/export_ical` | Yes | Downloads an `.ics` calendar file of the user's own shifts. |
| GET | `/turnusnokkel/<int:turnus_set_id>/<turnus_name>` | Yes | Shift key view (turnusnøkkel) for a named shift. |
| GET+POST | `/soknadsskjema` | Yes | Application form (søknadsskjema). GET renders it; POST saves choices to `SoknadsskjemaChoice`. Generates downloadable Word/PDF. |
| GET | `/import-favorites` | Yes | Import favorites from another turnus set. Renders preview of matches. |

---

## Downloads blueprint (`app/routes/downloads.py`) — no URL prefix

| Method | URL | Login required | What it does |
|---|---|---|---|
| GET | `/download_pdf` | Yes | Serves a PDF file from `static/turnusfiler/`. Filename passed as query param. |

---

## Minside blueprint (`app/routes/minside.py`) — prefix: `/minside`

| Method | URL | Login required | What it does |
|---|---|---|---|
| GET | `/minside/` | Yes | User profile page showing account info, rullenummer, stasjoneringssted. |
| POST | `/minside/change-password` | Yes | Changes the user's password after verifying current password. |

---

## API blueprint (`app/routes/api.py`) — prefix: `/api`

| Method | URL | Login required | What it does |
|---|---|---|---|
| POST | `/api/toggle_favorite` | Yes | Add/remove a shift from favorites. Returns updated favorites list + positions dict for DOM update. |
| POST | `/api/move-favorite` | Yes | Reorder a favorite (drag-drop). Updates `order_index` in DB. |
| POST | `/api/set-favorite-position` | Yes | Set a favorite to a specific position. |
| POST | `/api/generate-turnusnokkel` | Yes | Generate turnusnøkkel PDF/Word for a shift. |
| POST | `/api/import-favorites-preview` | Yes | Preview which favorites can be imported from another turnus set. |
| POST | `/api/import-favorites-confirm` | Yes | Confirm and apply the favorites import. |
| GET | `/api/get-turnus-sets-for-import` | Yes | List turnus sets available for favorites import. |
| GET | `/api/shift-image/<int:turnus_set_id>/<shift_nr>` | No | Serve a strekliste image file. |
| POST | `/api/mark-tour-seen` | Yes | Mark a named guided tour as completed. Writes to `DBUser.has_seen_*` column. |
| POST | `/api/soknadsskjema-choice` | Yes | Save a soknadsskjema checkbox selection to `SoknadsskjemaChoice`. |
| GET | `/api/check-rullenummer` | No | Check if a rullenummer exists in `AuthorizedEmails`. Used during registration. |
| ~~POST~~ | ~~`/api/js_select_shift`~~ | — | **Dead code — being removed in Phase 3.** `display_shift` route was deleted; this endpoint would 500 if called. |

---

## Admin blueprint (`app/routes/admin.py`) — prefix: `/admin`, admin-only

| Method | URL | What it does |
|---|---|---|
| GET | `/admin/dashboard` | Overview: user counts, turnus sets, PDF upload status. |
| GET | `/admin/activity` | Activity log — last 200 events + per-user stats. |
| POST | `/admin/reset-tour` | Reset all guided tour flags to 0 for all users. Clears full cache. |
| GET/POST | `/admin/create_user` | Create a new user directly (admin bypass of self-registration). |
| GET/POST | `/admin/edit_user/<int:user_id>` | Edit user details (name, email, rullenummer, etc.). |
| POST | `/admin/delete_user/<int:user_id>` | Delete a user. |
| POST | `/admin/toggle_auth/<int:user_id>` | Toggle admin status for a user. |
| GET | `/admin/turnus-sets` | List all turnus sets; shows status of turnusnøkkel, innplassering, strekliste. |
| GET/POST | `/admin/create-turnus-set` | Create a turnus set by uploading a PDF. Runs `shiftscraper` to extract JSON. |
| POST | `/admin/switch-turnus-set` | Set a turnus set as the global active set. |
| POST | `/admin/refresh-turnus-set/<int:turnus_set_id>` | Re-run the PDF scraper on an existing set. |
| GET | `/admin/turnusnokkel-status/<int:turnus_set_id>` | JSON: check if turnusnøkkel file exists for set. |
| POST | `/admin/upload-turnusnokkel/<int:turnus_set_id>` | Upload a turnusnøkkel Excel file. |
| GET | `/admin/innplassering-status/<int:turnus_set_id>` | JSON: check if innplassering data exists for set. |
| POST | `/admin/import-innplassering/<int:turnus_set_id>` | Import innplassering from Excel file. |
| POST | `/admin/delete-turnus-set/<int:turnus_set_id>` | Delete a turnus set and all its data. |
| GET | `/admin/authorized-emails` | List all authorized rullenummer entries. |
| POST | `/admin/add-authorized-email` | Add a single authorized rullenummer. |
| POST | `/admin/delete-authorized-email/<int:email_id>` | Remove an authorized rullenummer. |
| POST | `/admin/bulk-add-emails` | Bulk-add authorized rullenummer entries from text. |
| GET | `/admin/strekliste-status/<int:turnus_set_id>` | JSON: check if strekliste images exist for set. |
| POST | `/admin/upload-strekliste/<int:turnus_set_id>` | Upload strekliste PDF and generate timeline images. |
| POST | `/admin/generate-strekliste/<int:turnus_set_id>` | Re-generate strekliste images from existing PDF. |
| POST | `/admin/delete-strekliste-images/<int:turnus_set_id>` | Delete generated strekliste images. |
| GET | `/admin/user/<int:user_id>` | Detailed user view: activity log, favorites, innplassering. |
| GET | `/admin/employees` | List all employees (stub + registered). |
| POST | `/admin/import-employees` | Import employees from Excel. |
| POST | `/admin/upload-ansinitet` | Upload ansienitet PDF. |
| POST | `/admin/sync-employees` | Sync stub users against imported employee list. |
| POST | `/admin/add-employee` | Add a single employee manually. |
| POST | `/admin/cleanup-missing-stubs` | Remove stub users with no matching employee record. |
| POST | `/admin/reset-to-stub/<int:user_id>` | Downgrade a registered user back to stub. |
| POST | `/admin/delete-employee/<int:user_id>` | Delete an employee record entirely. |

---

## Database models (`app/models.py`)

| Model | Table | Purpose |
|---|---|---|
| `DBUser` | `users` | User account — credentials, rullenummer, tour flags, stasjoneringssted |
| `AuthorizedEmails` | `authorized_emails` | Whitelist of rullenummer allowed to self-register |
| `EmailVerificationToken` | `email_verification_tokens` | Email verification and password-reset tokens |
| `TurnusSet` | `turnus_sets` | A named turnus year (e.g. "T25") with associated file paths |
| `Favorites` | `favorites` | User's favorited shifts per turnus set, with order |
| `Shifts` | `shifts` | Shift titles per turnus set (populated from PDF scrape) |
| `SoknadsskjemaChoice` | `soknadsskjema_choices` | User's checkbox selections on the application form |
| `UserActivity` | `user_activity` | Page view and login/logout events |
| `Innplassering` | `innplassering` | Which shift a rullenummer is assigned to in a turnus set |

---

## Services (`app/services/`)

| File | Responsibility |
|---|---|
| `user_service.py` | User CRUD, password hashing, stub management |
| `auth_service.py` | Login, tokens, password reset, authorized email management |
| `turnus_service.py` | TurnusSet CRUD, active set management |
| `favorites_service.py` | Favorites add/remove/reorder per user+turnus_set |
| `activity_service.py` | Log and query user activity events |
| `innplassering_service.py` | Read innplassering records for a user |
```

- [ ] **Step 2: Commit**

```bash
git add docs/SITE_MAP.md
git commit -m "docs: add site map covering all routes, models, and services"
```

---

## Task 3: Fix the failing test (Phase 2.1)

**Files:**
- Modify: `tests/test_auth_service.py:11-17`

**Context:** `test_add_and_check` was written against an older API where `add_authorized_email` accepted just an email. The current API requires `rullenummer` (email is optional and ignored by `is_email_authorized`).

- [ ] **Step 1: Run the failing test to confirm the failure**

```bash
venv/bin/pytest tests/test_auth_service.py::TestAuthorizedEmails::test_add_and_check -v
```
Expected: FAIL — `assert False is True` (because `add_authorized_email` returns `(False, "Rullenummer er påkrevd")` when `rullenummer` is `None`).

- [ ] **Step 2: Fix the test**

Replace lines 11-17 in `tests/test_auth_service.py`:

```python
def test_add_and_check(self, patch_db, sample_user):
    success, _ = auth_service.add_authorized_email(
        email="allowed@test.com", rullenummer="12345", added_by=sample_user["id"]
    )
    assert success is True
    assert auth_service.is_email_authorized("allowed@test.com", rullenummer="12345") is True
    assert auth_service.is_email_authorized("other@test.com", rullenummer="99999") is False
```

- [ ] **Step 3: Run the test to confirm it passes**

```bash
venv/bin/pytest tests/test_auth_service.py::TestAuthorizedEmails::test_add_and_check -v
```
Expected: PASS

- [ ] **Step 4: Run the full suite to confirm no regressions**

```bash
venv/bin/pytest -q
```
Expected: 0 failures

- [ ] **Step 5: Commit**

```bash
git add tests/test_auth_service.py
git commit -m "fix: update test_add_and_check to match current add_authorized_email API (requires rullenummer)"
```

---

## Task 4: Fix tour state reads + cache has_min_turnus (Phase 2.2 + 2.3)

**Files:**
- Modify: `app/__init__.py` (rewrite `inject_tour_state`)
- Modify: `app/routes/api.py:726-749` (add cache invalidation in `mark_tour_seen`)

**Context:** `inject_tour_state` currently reads 6 tour flags from `session`, but `DBUser` already has persistent DB columns for these. The session reads cause tour state to reset on new devices/cleared cookies. `has_min_turnus` also runs 3 DB queries on every page load with no caching.

Both fixes modify the same function. Do them together.

- [ ] **Step 1: Rewrite `inject_tour_state` in `app/__init__.py`**

Replace the entire `inject_tour_state` function (lines 58-120) with:

```python
@app.context_processor
def inject_tour_state():
    if current_user.is_authenticated:
        from app.models import Innplassering, TurnusSet
        from app.utils.pdf_downloads import get_pdf_downloads
        from app.utils.turnus_helpers import get_user_turnus_set
        from flask import url_for

        # Tour flags — read from DB columns, cached 60s per user.
        # Only one key differs from the session key name: has_seen_tour → has_seen_turnusliste_tour.
        tour_cache_key = f"tour_state_{current_user.id}"
        tour_state = cache.get(tour_cache_key)
        if tour_state is None:
            db_session = get_db_session()
            try:
                db_user = db_session.query(DBUser).filter_by(id=current_user.id).first()
                if db_user:
                    tour_state = {
                        "has_seen_tour": db_user.has_seen_turnusliste_tour or 0,
                        "has_seen_favorites_tour": db_user.has_seen_favorites_tour or 0,
                        "has_seen_mintur_tour": db_user.has_seen_mintur_tour or 0,
                        "has_seen_compare_tour": db_user.has_seen_compare_tour or 0,
                        "has_seen_welcome": db_user.has_seen_welcome or 0,
                        "has_seen_soknadsskjema_tour": db_user.has_seen_soknadsskjema_tour or 0,
                    }
                else:
                    tour_state = {
                        "has_seen_tour": 0, "has_seen_favorites_tour": 0,
                        "has_seen_mintur_tour": 0, "has_seen_compare_tour": 0,
                        "has_seen_welcome": 0, "has_seen_soknadsskjema_tour": 0,
                    }
            finally:
                db_session.close()
            cache.set(tour_cache_key, tour_state, timeout=60)

        # has_min_turnus — cached 60s per user.
        min_turnus_key = f"has_min_turnus_{current_user.id}"
        has_min_turnus = cache.get(min_turnus_key)
        if has_min_turnus is None:
            db_session = get_db_session()
            try:
                db_user = db_session.query(DBUser).filter_by(id=current_user.id).first()
                has_min_turnus = False
                if db_user and db_user.rullenummer:
                    active_ts = db_session.query(TurnusSet).filter_by(is_active=1).first()
                    if active_ts:
                        has_min_turnus = db_session.query(Innplassering).filter_by(
                            turnus_set_id=active_ts.id,
                            rullenummer=str(db_user.rullenummer),
                        ).first() is not None
            finally:
                db_session.close()
            cache.set(min_turnus_key, has_min_turnus, timeout=60)

        # PDF downloads — cached per turnus set.
        turnus_set = get_user_turnus_set()
        pdf_downloads = []
        if turnus_set:
            year_id = turnus_set["year_identifier"].lower()
            pdf_cache_key = f"pdf_downloads_{year_id}"
            pdf_downloads = cache.get(pdf_cache_key)
            if pdf_downloads is None:
                raw = get_pdf_downloads(AppConfig.turnusfiler_dir, year_id)
                pdf_downloads = [
                    {
                        "display_name": item["display_name"],
                        "url": url_for(
                            "static",
                            filename=f'turnusfiler/{year_id}/pdf/{item["filename"]}',
                        ),
                    }
                    for item in raw
                ]
                cache.set(pdf_cache_key, pdf_downloads, timeout=300)

        return {
            **tour_state,
            "has_min_turnus": has_min_turnus,
            "pdf_downloads": pdf_downloads,
            "global_turnus_set": turnus_set,
        }

    return {
        "has_seen_tour": 0,
        "has_seen_favorites_tour": 0,
        "has_seen_mintur_tour": 0,
        "has_seen_compare_tour": 0,
        "has_seen_welcome": 0,
        "has_seen_soknadsskjema_tour": 0,
        "has_min_turnus": False,
        "pdf_downloads": [],
        "global_turnus_set": None,
    }
```

- [ ] **Step 2: Invalidate `tour_state_{user_id}` cache in `mark_tour_seen` (`app/routes/api.py`)**

In `mark_tour_seen`, after `db_session.commit()` (currently line 731), add one line:

```python
db_session.commit()
cache.delete(f"tour_state_{current_user.id}")  # invalidate context processor cache
```

- [ ] **Step 3: Run the full test suite**

```bash
venv/bin/pytest -q
```
Expected: 0 failures

- [ ] **Step 4: Manual smoke test**

Start the dev server (`python run.py`) and:
1. Log in — confirm the navbar renders without errors
2. Open DevTools Network tab, reload — confirm no 500 errors
3. Navigate to `/turnusliste` — page renders normally

- [ ] **Step 5: Commit**

```bash
git add app/__init__.py app/routes/api.py
git commit -m "perf: read tour flags from DB columns (not session); cache tour state and has_min_turnus per user (60s TTL)"
```

---

## Task 5: Fix N+1 in `update_favorite_order` (Phase 2.4)

**Files:**
- Modify: `app/services/favorites_service.py:63-76`

**Context:** The function loads all favorites then re-queries each one individually to update `order_index`. The already-loaded objects can be updated directly.

- [ ] **Step 1: Write a test verifying `update_favorite_order` sets indices correctly**

Add to `tests/test_favorites_service.py`:

```python
class TestUpdateFavoriteOrder:
    def test_updates_order_index(self, patch_db, db_session, sample_user):
        ts = TurnusSet(name="Test Set", year_identifier="T26", is_active=1)
        db_session.add(ts)
        db_session.commit()

        favorites_service.add_favorite(sample_user["id"], "D1", 0, ts.id)
        favorites_service.add_favorite(sample_user["id"], "N2", 1, ts.id)
        favorites_service.add_favorite(sample_user["id"], "K3", 2, ts.id)

        result = favorites_service.update_favorite_order(sample_user["id"], ts.id)
        assert result is True

        # Verify indices are assigned 0, 1, 2 in DB
        from app.models import Favorites
        rows = db_session.query(Favorites).filter_by(
            user_id=sample_user["id"], turnus_set_id=ts.id
        ).order_by(Favorites.order_index).all()
        assert [r.order_index for r in rows] == [0, 1, 2]
```

- [ ] **Step 2: Run the test to confirm it passes (it tests existing behaviour, not a new failure)**

```bash
venv/bin/pytest tests/test_favorites_service.py::TestUpdateFavoriteOrder -v
```
Expected: PASS (the logic is correct, just inefficient)

- [ ] **Step 3: Replace the inner loop in `update_favorite_order`**

In `app/services/favorites_service.py`, replace lines 63-76:

```python
        current_favorites = db_session.query(Favorites).filter_by(
            user_id=user_id,
            turnus_set_id=turnus_set_id
        ).all()

        for index, favorite in enumerate(current_favorites):
            favorite.order_index = index
```

(Remove the second inner `db_session.query(Favorites).filter_by(...)` call entirely — use the already-loaded `favorite` object from the first query.)

- [ ] **Step 4: Run tests**

```bash
venv/bin/pytest tests/test_favorites_service.py -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/services/favorites_service.py tests/test_favorites_service.py
git commit -m "perf: fix N+1 in update_favorite_order — update loaded objects instead of re-querying each one"
```

---

## Task 6: Fix O(n²) in favorites route (Phase 2.5)

**Files:**
- Modify: `app/routes/shifts.py:422-433`

**Context:** `fav_order_lst` is a list. The `in` check at line 432 inside a loop is O(n) per iteration → O(n²) total. Convert to set for O(1) lookup.

- [ ] **Step 1: Apply the fix in `app/routes/shifts.py`**

In the `favorites()` function, after line 422:
```python
fav_order_lst = db_utils.get_favorite_lst(current_user.get_id(), turnus_set_id)
```

Add one line immediately after:
```python
fav_set = set(fav_order_lst)
```

Then on line 432, change:
```python
            if name in fav_order_lst:
```
to:
```python
            if name in fav_set:
```

- [ ] **Step 2: Run the full test suite**

```bash
venv/bin/pytest -q
```
Expected: 0 failures

- [ ] **Step 3: Commit**

```bash
git add app/routes/shifts.py
git commit -m "perf: convert fav_order_lst to set before loop in favorites() to fix O(n²) membership check"
```

---

## Task 7: Add DB indexes (Phase 2.6)

**Files:**
- Create: `migrations/versions/010_add_performance_indexes.py`

- [ ] **Step 1: Generate a new migration**

```bash
venv/bin/alembic revision -m "add performance indexes"
```

This creates a new file in `migrations/versions/` with an auto-generated revision ID. Note the filename — you will replace its content in the next step.

- [ ] **Step 2: Replace the migration file content**

Open the newly generated file and replace its entire contents with:

```python
"""add performance indexes

Revision ID: 010_add_performance_indexes
Revises: <PASTE_THE_DOWN_REVISION_FROM_GENERATED_FILE>
Create Date: 2026-05-08
"""
from typing import Sequence, Union
from alembic import op

revision: str = "010_add_performance_indexes"
down_revision: Union[str, None] = "<PASTE_THE_DOWN_REVISION_FROM_GENERATED_FILE>"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_favorites_user_ts", "favorites", ["user_id", "turnus_set_id"])
    op.create_index("ix_innplassering_ts_rullenr", "innplassering", ["turnus_set_id", "rullenummer"])
    op.create_index("ix_user_activity_timestamp", "user_activity", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_favorites_user_ts", table_name="favorites")
    op.drop_index("ix_innplassering_ts_rullenr", table_name="innplassering")
    op.drop_index("ix_user_activity_timestamp", table_name="user_activity")
```

**Important:** Copy the `down_revision` value from the generated file before overwriting — it must point to the current HEAD migration or Alembic will reject it. Rename the file to `010_add_performance_indexes.py` to match the convention.

- [ ] **Step 3: Apply the migration**

```bash
venv/bin/alembic upgrade head
```
Expected: no errors. `alembic current` should show `010_add_performance_indexes`.

- [ ] **Step 4: Run the full test suite**

```bash
venv/bin/pytest -q
```
Expected: 0 failures

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/010_add_performance_indexes.py
git commit -m "perf: add DB indexes on favorites(user_id, turnus_set_id), innplassering(turnus_set_id, rullenummer), user_activity(timestamp)"
```

---

## Task 8: Defer JS + remove duplicate meta tags (Phase 2.7)

**Files:**
- Modify: `app/templates/base.html`

**Context:** Bootstrap JS and driver.js are loaded synchronously in `<head>`, blocking HTML parsing. The inline Bootstrap event listener must move to end of `<body>` because deferred scripts execute after parsing. Lines 7-11 duplicate the charset and viewport meta tags from lines 4-5.

- [ ] **Step 1: Remove duplicate meta tags (lines 7-11)**

Delete these lines from `<head>`:
```html
        <meta charset="utf-8" />
        <meta
            name="viewport"
            content="width=device-width, initial-scale=1, shrink-to-fit=no"
        />
```
Keep the first occurrence (lines 4-5). The `<head>` should have exactly one `<meta charset>` and one `<meta name="viewport">`.

- [ ] **Step 2: Add `defer` to Bootstrap JS and driver.js**

Change the Bootstrap bundle script tag from:
```html
        <script
            src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
            integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz"
            crossorigin="anonymous"
        ></script>
```
to:
```html
        <script
            src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
            integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz"
            crossorigin="anonymous"
            defer
        ></script>
```

Change the driver.js script tag from:
```html
        <script src="https://cdn.jsdelivr.net/npm/driver.js@1.3.1/dist/driver.js.iife.js"></script>
```
to:
```html
        <script src="https://cdn.jsdelivr.net/npm/driver.js@1.3.1/dist/driver.js.iife.js" defer></script>
```

- [ ] **Step 3: Move the inline Bootstrap event listener to end of `<body>`**

Remove this block from `<head>`:
```html
        <script>
            document.addEventListener("show.bs.modal", function () {
                queueMicrotask(function () {
                    document.body.style.paddingRight = "";
                });
            });
        </script>
```

Add it at the very end of `<body>`, just before `</body>`:
```html
    <script>
        document.addEventListener("show.bs.modal", function () {
            queueMicrotask(function () {
                document.body.style.paddingRight = "";
            });
        });
    </script>
</body>
```

- [ ] **Step 4: Smoke test in browser**

Start the dev server and open any page. Check browser console — no JS errors. Open a modal (if applicable) — it works without padding glitch.

- [ ] **Step 5: Run tests**

```bash
venv/bin/pytest -q
```
Expected: 0 failures

- [ ] **Step 6: Commit**

```bash
git add app/templates/base.html
git commit -m "perf: defer Bootstrap and driver.js; remove duplicate meta charset/viewport tags"
```

---

## Task 9: Remove dead code (Phase 3 prep)

**Files:**
- Modify: `app/routes/api.py:22-33` (remove `select_shift` endpoint)
- Modify: `app/static/js/main.js` (remove ShiftSelection import + instantiation)
- Delete: `app/static/js/modules/shift-selection.js`

**Context:** `display_shift` route was intentionally deleted in commit `bffe030`. Three orphaned pieces reference it and should be removed together. No template has `.clickable-row`, so the JS code never fires.

- [ ] **Step 1: Remove `select_shift` from `app/routes/api.py`**

Delete lines 22-33 entirely:
```python
@api.route("/js_select_shift", methods=["POST"])
def select_shift():
    data = request.get_json() or {}
    shift_title = data.get("shift_title")

    if shift_title:
        # Redirect to the display_shift page instead of returning JSON
        from flask import redirect, url_for

        return redirect(url_for("shifts.display_shift", shift_title=shift_title))
    else:
        return jsonify({"status": "error", "message": "No shift title provided"})
```

- [ ] **Step 2: Remove ShiftSelection from `app/static/js/main.js`**

Remove line 4:
```js
import { ShiftSelection } from './modules/shift-selection.js';
```

Remove lines 57-59:
```js
        if (document.querySelector('.clickable-row')) {
            this.modules.shiftSelection = new ShiftSelection();
        }
```

- [ ] **Step 3: Delete the dead module file**

```bash
rm app/static/js/modules/shift-selection.js
```

- [ ] **Step 4: Run full tests**

```bash
venv/bin/pytest -q
```
Expected: 0 failures

- [ ] **Step 5: Commit**

```bash
git add app/routes/api.py app/static/js/main.js
git rm app/static/js/modules/shift-selection.js
git commit -m "chore: remove dead shift-selection code (display_shift route was deleted in bffe030)"
```

---

## Task 10: Split `shifts.py` into a package (Phase 3.1)

**Files:**
- Create: `app/routes/shifts/` (directory)
- Create: `app/routes/shifts/__init__.py`
- Create: `app/routes/shifts/index.py`
- Create: `app/routes/shifts/mintur.py`
- Create: `app/routes/shifts/turnusliste.py`
- Create: `app/routes/shifts/favorites.py`
- Create: `app/routes/shifts/oversikt.py`
- Create: `app/routes/shifts/turnusnokkel.py`
- Create: `app/routes/shifts/soknadsskjema.py`
- Delete: `app/routes/shifts.py`

**Context:** `shifts.py` is 1450 lines. Python resolves `from app.routes.shifts import shifts` identically whether `shifts` is a module or a package — no changes needed in `app/routes/main.py`.

**Pattern:** Each sub-file imports the `shifts` blueprint from the package `__init__.py`. The `__init__.py` creates the blueprint first, then imports sub-modules at the bottom to register their routes.

- [ ] **Step 1: Verify tests pass before starting**

```bash
venv/bin/pytest -q
```
Expected: 0 failures. If not, fix before continuing.

- [ ] **Step 2: Create the package directory**

```bash
mkdir app/routes/shifts
```

- [ ] **Step 3: Create `app/routes/shifts/__init__.py`**

```python
import logging

from flask import Blueprint

shifts = Blueprint("shifts", __name__)

_TRACKED_ENDPOINTS = {"shifts.turnusliste", "shifts.oversikt", "shifts.favorites"}

logger = logging.getLogger(__name__)


@shifts.before_request
def log_page_view():
    from flask_login import current_user
    from flask import request
    if not current_user.is_authenticated:
        return
    if request.endpoint not in _TRACKED_ENDPOINTS:
        return
    from app.services.activity_service import log_event
    page = request.endpoint.split(".")[-1]
    log_event(current_user.id, "page_view", details=page)


def _classify_shift_type(start_str: str, end_str: str) -> str:
    """Map shift start/end times to a Norwegian shift-type label.

    Uses a simplified 4-label system intentionally different from the
    5-class color system in shift-classifier.js — all pre-08:00 starts
    are "Tidlig" regardless of whether they start before or after 06:00.
    """
    sh, sm = (int(x) for x in start_str.split(":"))
    eh, em = (int(x) for x in end_str.split(":"))
    start_mins = sh * 60 + sm
    end_mins = eh * 60 + em
    overnight = end_mins < start_mins

    if start_mins < 8 * 60:
        return "Tidlig"
    if start_mins < 12 * 60:
        return "Dag"
    if overnight and end_mins >= 4 * 60:
        return "Natt"
    return "Ettermiddag"


# Import sub-modules last so they can import `shifts` from this __init__.py
from app.routes.shifts import index, mintur, turnusliste, favorites, oversikt, turnusnokkel, soknadsskjema  # noqa: E402,F401
```

**Important:** Copy `_classify_shift_type` verbatim from `shifts.py` lines 40-59. Replace the `...` placeholder above with the full function body.

- [ ] **Step 4: Create `app/routes/shifts/index.py`**

Move from `shifts.py` lines 78-84:

```python
from flask import redirect, url_for
from flask_login import login_required

from app.routes.shifts import shifts


@shifts.route("/")
@login_required
def index():
    from config import AppConfig
    landing = AppConfig.LANDING_PAGE or "mintur"
    return redirect(url_for(f"shifts.{landing}"))
```

- [ ] **Step 5: Create `app/routes/shifts/mintur.py`**

Move from `shifts.py` lines 87-351 (functions: `_load_mintur_data`, `mintur`, `export_ical`).

File header:
```python
import logging
import os
from datetime import date

from flask import Blueprint, redirect, render_template, request, send_file, session, url_for
from flask_login import current_user, login_required

from app.routes.shifts import shifts
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set, iter_turnus_days
from app.services.innplassering_service import get_innplassering_for_user

logger = logging.getLogger(__name__)
```

Then copy `_load_mintur_data`, `mintur`, and `export_ical` verbatim from `shifts.py`.

- [ ] **Step 6: Run tests after mintur.py is created**

```bash
venv/bin/pytest -q
```
Expected: 0 failures.

- [ ] **Step 7: Create `app/routes/shifts/turnusliste.py`**

Move from `shifts.py`: `_turnusliste_cache_key` (lines 27-37), `turnusliste` (lines 353-411), `switch_user_year` (lines 394-411).

File header:
```python
import logging
import uuid

from flask import redirect, render_template, session, url_for
from flask_login import current_user, login_required

from app.extensions import cache
from app.routes.shifts import shifts
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set
from app.services.innplassering_service import get_innplassering_for_user

logger = logging.getLogger(__name__)
```

- [ ] **Step 8: Run tests**

```bash
venv/bin/pytest -q
```
Expected: 0 failures.

- [ ] **Step 9: Create `app/routes/shifts/favorites.py`**

Move from `shifts.py`: `favorites` (lines 413-450), `import_favorites` (lines 1405-end).

File header:
```python
import logging

from flask import render_template
from flask_login import current_user, login_required

from app.routes.shifts import shifts
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set

logger = logging.getLogger(__name__)
```

- [ ] **Step 10: Run tests**

```bash
venv/bin/pytest -q
```
Expected: 0 failures.

- [ ] **Step 11: Create `app/routes/shifts/oversikt.py`**

Move from `shifts.py`: `oversikt` (lines 453-565).

File header:
```python
import logging

from flask import render_template
from flask_login import current_user, login_required

from app.routes.shifts import shifts, _classify_shift_type
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set

logger = logging.getLogger(__name__)
```

- [ ] **Step 12: Run tests**

```bash
venv/bin/pytest -q
```
Expected: 0 failures.

- [ ] **Step 13: Create `app/routes/shifts/turnusnokkel.py`**

Move from `shifts.py`: `turnusnokkel_view` (lines 567-702).

File header:
```python
import logging
import os

from flask import render_template, request, send_file
from flask_login import current_user, login_required

from app.routes.shifts import shifts
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set
from config import AppConfig

logger = logging.getLogger(__name__)
```

- [ ] **Step 14: Run tests**

```bash
venv/bin/pytest -q
```
Expected: 0 failures.

- [ ] **Step 15: Create `app/routes/shifts/soknadsskjema.py`**

Move from `shifts.py`: all helper functions (`_set_table_col_widths` lines 704-795, `_add_cell_border` lines 797-815, `_arial` lines 818-825, `_get_soknadsskjema_choices` lines 827-851, `_build_soknadsskjema_doc` lines 852-1062, `_build_soknadsskjema_pdf` lines 1064-1301) and the `soknadsskjema` route (lines 1303-1403).

File header:
```python
import logging
import os
import tempfile

from flask import redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.database import get_db_session
from app.extensions import cache
from app.models import DBUser, SoknadsskjemaChoice
from app.routes.shifts import shifts
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set
from config import AppConfig

logger = logging.getLogger(__name__)
```

- [ ] **Step 16: Run tests**

```bash
venv/bin/pytest -q
```
Expected: 0 failures.

- [ ] **Step 17: Delete the original `shifts.py`**

```bash
git rm app/routes/shifts.py
```

Git will remove the file. The package directory `app/routes/shifts/` is already tracked.

- [ ] **Step 18: Run full tests + smoke test**

```bash
venv/bin/pytest -q
```
Expected: 0 failures.

Then start dev server (`python run.py`) and manually visit `/`, `/turnusliste`, `/favorites`, `/mintur`, `/oversikt`.

- [ ] **Step 19: Commit**

```bash
git add app/routes/shifts/
git commit -m "refactor: split shifts.py (1450 lines) into shifts/ package — routes unchanged"
```

---

## Task 11: Split `admin.py` into a package (Phase 3.2)

**Files:**
- Create: `app/routes/admin/` (directory)
- Create: `app/routes/admin/__init__.py`
- Create: `app/routes/admin/dashboard.py`
- Create: `app/routes/admin/users.py`
- Create: `app/routes/admin/turnus.py`
- Create: `app/routes/admin/employees.py`
- Create: `app/routes/admin/emails.py`
- Delete: `app/routes/admin.py`

**Same pattern as Task 10.** `from app.routes.admin import admin` continues to work unchanged.

- [ ] **Step 1: Verify tests pass**

```bash
venv/bin/pytest -q
```

- [ ] **Step 2: Create the package directory**

```bash
mkdir app/routes/admin
```

- [ ] **Step 3: Create `app/routes/admin/__init__.py`**

```python
from flask import Blueprint

admin = Blueprint("admin", __name__, url_prefix="/admin")

# Import sub-modules last so they can import `admin` from this __init__.py
from app.routes.admin import dashboard, users, turnus, employees, emails  # noqa: E402,F401
```

- [ ] **Step 4: Create `app/routes/admin/dashboard.py`**

Move from `admin.py`: `admin_dashboard` (line 26), `activity_log` (line 51), `reset_tour` (line 63).

File header:
```python
from flask import flash, redirect, render_template, url_for, current_app
from flask_login import current_user
import os

from app.database import get_db_session
from app.decorators import admin_required
from app.extensions import cache
from app.models import DBUser
from app.routes.admin import admin
from app.utils import db_utils
```

- [ ] **Step 5: Run tests**

```bash
venv/bin/pytest -q
```

- [ ] **Step 6: Create `app/routes/admin/users.py`**

Move from `admin.py`: `create_user` (line 88), `edit_user` (line 107), `delete_user` (line 146), `toggle_auth` (line 163), `user_detail` (line 826).

File header:
```python
from flask import flash, redirect, render_template, url_for
from app.database import get_db_session
from app.decorators import admin_required
from app.extensions import cache
from app.forms import CreateUserForm, EditUserForm
from app.models import DBUser
from app.routes.admin import admin
from app.services import user_service
from app.utils import db_utils
```

- [ ] **Step 7: Run tests**

```bash
venv/bin/pytest -q
```

- [ ] **Step 8: Create `app/routes/admin/turnus.py`**

Move from `admin.py`: `manage_turnus_sets` (180), `create_turnus_set` (197), `handle_pdf_upload` (318), `switch_turnus_set` (362), `refresh_turnus_set` (381), `turnusnokkel_status` (469), `upload_turnusnokkel` (488), `innplassering_status` (517), `import_innplassering_route` (545), `delete_turnus_set` (584), `strekliste_status` (676), `upload_strekliste` (703), `generate_strekliste` (732), `delete_strekliste_images` (799).

File header:
```python
import json
import os

from flask import flash, jsonify, redirect, render_template, request, url_for, current_app
from app.database import get_db_session
from app.decorators import admin_required
from app.extensions import cache
from app.forms import CreateTurnusSetForm, UploadStreklisteForm
from app.routes.admin import admin
from app.utils import db_utils
from app.utils.pdf import strekliste_generator
from app.utils.pdf.double_shift_scanner import scan_double_shifts
from config import AppConfig
```

- [ ] **Step 9: Run tests**

```bash
venv/bin/pytest -q
```

- [ ] **Step 10: Create `app/routes/admin/employees.py`**

Move from `admin.py`: `manage_employees` (855), `import_employees` (902), `upload_ansinitet_pdf` (948), `sync_employees` (990), `add_employee` (1025), `cleanup_missing_stubs` (1055), `reset_to_stub` (1064), `delete_employee` (1078).

File header:
```python
from flask import flash, jsonify, redirect, render_template, request, url_for, current_app
from app.database import get_db_session
from app.decorators import admin_required
from app.extensions import cache
from app.models import DBUser
from app.routes.admin import admin
from app.services import user_service
from app.utils import db_utils
from config import AppConfig
```

- [ ] **Step 11: Run tests**

```bash
venv/bin/pytest -q
```

- [ ] **Step 12: Create `app/routes/admin/emails.py`**

Move from `admin.py`: `manage_authorized_emails` (615), `add_authorized_email` (627), `delete_authorized_email` (647), `bulk_add_authorized_emails` (656).

File header:
```python
from flask import flash, redirect, render_template, request, url_for
from app.database import get_db_session
from app.decorators import admin_required
from app.routes.admin import admin
from app.services import auth_service
```

- [ ] **Step 13: Run tests**

```bash
venv/bin/pytest -q
```

- [ ] **Step 14: Delete the original `admin.py`**

```bash
git rm app/routes/admin.py
```

- [ ] **Step 15: Run full tests + smoke test**

```bash
venv/bin/pytest -q
```
Expected: 0 failures.

Start dev server and visit `/admin/dashboard`, `/admin/employees`, `/admin/turnus-sets`.

- [ ] **Step 16: Commit**

```bash
git add app/routes/admin/
git commit -m "refactor: split admin.py (1096 lines) into admin/ package — routes unchanged"
```

---

## Final verification

- [ ] Run full test suite one last time:

```bash
venv/bin/pytest -v
```
Expected: all 78+ tests pass, 0 failures.

- [ ] Check git log looks clean:

```bash
git log --oneline restructure ^development
```

All commits should be on `restructure`. The branch is ready to review and merge.
