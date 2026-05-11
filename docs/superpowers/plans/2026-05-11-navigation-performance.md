# Navigation Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make page navigation feel faster by prefetching pages on hover (instant.page) and caching the expensive `/oversikt` route.

**Architecture:** Two independent changes — a single script tag in the base template for instant.page, and a `@cache.cached` decorator on the `/oversikt` route following the existing pattern in `turnusliste.py`.

**Tech Stack:** Flask-Caching (already configured), instant.page 5.2.0 (CDN)

---

### Task 1: Add instant.page to base template

**Files:**
- Modify: `app/templates/base.html` (bottom of `<head>`, after existing scripts)

- [ ] **Step 1: Add the script tag**

In `app/templates/base.html`, add this line after the main.js script block (lines 34–38), before the favicon `<link>`:

```html
<script src="//instant.page/5.2.0" type="module" integrity="sha384-jnZyxPjiipYXnSU+ygvrkboMaBy1u5T7OcKSfBQcqhYs3XLDlPJYS1gASAlpEqF"></script>
```

> Note: Verify the integrity hash at https://instant.page — the hash above is for 5.2.0. If it differs, use the one from the site.

- [ ] **Step 2: Smoke test**

Start the dev server (`python run.py`) and navigate between at least two routes. Open browser DevTools → Network tab and confirm:
- No console errors
- On hovering a nav link for ~65ms, a prefetch request fires for that URL before you click

- [ ] **Step 3: Commit**

```bash
git add app/templates/base.html
git commit -m "perf: add instant.page prefetch for faster navigation"
```

---

### Task 2: Cache the /oversikt route

**Files:**
- Modify: `app/routes/shifts/oversikt.py`
- Test: `tests/test_oversikt_cache.py` (create new)

The `/oversikt` route builds a `DataframeManager` for the user's turnus set and additional ones per innplassering row on every request. Adding `@cache.cached` with a per-user, per-turnus-set key (same pattern as `/turnusliste`) eliminates this cost after the first load.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_oversikt_cache.py`:

```python
"""Tests for /oversikt cache key function."""
import pytest


class TestOversiktCacheKey:
    def test_returns_per_user_per_ts_key(self, monkeypatch):
        from app.routes.shifts.oversikt import _oversikt_cache_key

        monkeypatch.setattr(
            "app.routes.shifts.oversikt.get_user_turnus_set",
            lambda: {"id": 42, "name": "R26"},
        )
        mock_user = type("U", (), {"get_id": lambda self: "7"})()
        monkeypatch.setattr("app.routes.shifts.oversikt.current_user", mock_user)
        monkeypatch.setattr("app.routes.shifts.oversikt.session", {})

        assert _oversikt_cache_key() == "view/oversikt/7/42"

    def test_bypasses_cache_when_flashes_pending(self, monkeypatch):
        from app.routes.shifts.oversikt import _oversikt_cache_key

        monkeypatch.setattr(
            "app.routes.shifts.oversikt.get_user_turnus_set",
            lambda: {"id": 42, "name": "R26"},
        )
        mock_user = type("U", (), {"get_id": lambda self: "7"})()
        monkeypatch.setattr("app.routes.shifts.oversikt.current_user", mock_user)
        monkeypatch.setattr(
            "app.routes.shifts.oversikt.session",
            {"_flashes": [("info", "saved")]},
        )

        key = _oversikt_cache_key()
        assert key.startswith("view/oversikt/7/42/flash/")

    def test_handles_no_turnus_set(self, monkeypatch):
        from app.routes.shifts.oversikt import _oversikt_cache_key

        monkeypatch.setattr(
            "app.routes.shifts.oversikt.get_user_turnus_set",
            lambda: None,
        )
        mock_user = type("U", (), {"get_id": lambda self: "7"})()
        monkeypatch.setattr("app.routes.shifts.oversikt.current_user", mock_user)
        monkeypatch.setattr("app.routes.shifts.oversikt.session", {})

        assert _oversikt_cache_key() == "view/oversikt/7/none"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_oversikt_cache.py -v
```

Expected: `ImportError` — `_oversikt_cache_key` does not exist yet.

- [ ] **Step 3: Implement the cache key function and decorator**

In `app/routes/shifts/oversikt.py`, make the following changes:

**Replace the existing imports block** at the top of `app/routes/shifts/oversikt.py` with:

```python
import uuid

from flask import render_template, session
from flask_login import current_user, login_required

from app.extensions import cache
from app.routes.shifts import shifts
from app.services.innplassering_service import get_innplassering_for_user
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set, iter_turnus_days
```

(Adds `import uuid`, `session` to the flask import, and `from app.extensions import cache`.)

**Add cache key function** (before the route function):

```python
def _oversikt_cache_key():
    ts = get_user_turnus_set()
    ts_id = ts["id"] if ts else "none"
    if session.get("_flashes"):
        return f"view/oversikt/{current_user.get_id()}/{ts_id}/flash/{uuid.uuid4()}"
    return f"view/oversikt/{current_user.get_id()}/{ts_id}"
```

**Add decorator** to the route (between `@login_required` and `def oversikt()`):

```python
@shifts.route("/oversikt")
@login_required
@cache.cached(timeout=300, key_prefix=_oversikt_cache_key)
def oversikt():
    ...
```

- [ ] **Step 4: Add oversikt cache invalidation to the favorites toggle API**

In `app/routes/api.py`, find the block around line 53–55 that deletes the turnusliste cache key and add an equivalent line immediately after:

```python
# existing line:
_cache.delete(f"view/turnusliste/{user_id}/{turnus_set_id}")
# add:
_cache.delete(f"view/oversikt/{user_id}/{turnus_set_id}")
```

Without this, a user who toggles a favorite and then navigates back to `/oversikt` will see a stale `favoritt` list for up to 300s.

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_oversikt_cache.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
pytest
```

Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add app/routes/shifts/oversikt.py app/routes/api.py tests/test_oversikt_cache.py
git commit -m "perf: cache /oversikt route per user and turnus set (300s TTL)"
```
