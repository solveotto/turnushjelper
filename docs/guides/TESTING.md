# Testing Guide

## Running tests

```bash
# Run the full suite
pytest

# Run quietly (one dot per test)
pytest -q

# Run a single test file
pytest tests/test_favorites_service.py

# Run a single test class
pytest tests/test_auth_service.py::TestVerifyPassword

# Run a single test function
pytest tests/test_auth_service.py::TestVerifyPassword::test_correct_password_returns_true

# Show full output on failure (no truncation)
pytest -s

# Stop after first failure
pytest -x
```

---

## What each test file covers

| File | What it tests |
|---|---|
| `test_models.py` | ORM model constraints (unique username, cascade deletes, etc.) |
| `test_user_service.py` | User CRUD: create, update, delete, password hashing |
| `test_auth_service.py` | Login, tokens, password reset, authorized emails |
| `test_turnus_service.py` | Turnus set CRUD, shift management |
| `test_favorites_service.py` | Add/remove/reorder favorites |
| `test_api_routes.py` | HTTP-level tests for `/api/toggle-favorite` |
| `test_auth_routes.py` | HTTP-level tests for `/login`, `/logout` |
| `test_mintur_export.py` | Shift classification logic + `/mintur/export_ical` route |
| `test_shift_stats.py` | Shift statistics calculation (night/early/afternoon rules) |
| `test_data_integrity.py` | Turnus JSON format validation (no DB needed) |
| `test_load.py` | Concurrent request stress test |
| `test_pdf_downloads.py` | PDF download list utility |

---

## How the test database works

Tests use an **in-memory SQLite database** — no files, no setup, always clean.

The key is the `db_session` fixture in `conftest.py`. It wraps each test in a transaction that gets rolled back at the end, so every test starts with a blank slate regardless of what the previous test inserted.

```
test starts
  └── connection opened
       └── transaction begun
            └── db_session yielded to test
                 └── test inserts / queries data
            └── transaction rolled back  ← all changes discarded
       └── connection closed
test ends (database is back to empty)
```

You never need to clean up after yourself in a test.

---

## The three fixture layers

**`db_session`** — gives you a raw SQLAlchemy session to insert test data directly:

```python
def test_something(db_session):
    user = DBUser(username="test", ...)
    db_session.add(user)
    db_session.commit()
    # test your logic
```

**`patch_db`** — use this when testing service functions. It monkeypatches `get_db_session` in all service modules so they use the same in-memory database as your test:

```python
def test_service_function(patch_db, db_session):
    # insert seed data directly
    db_session.add(TurnusSet(name="T26", year_identifier="T26", is_active=1))
    db_session.commit()

    # call service — it will use the same in-memory DB
    result = turnus_service.get_active_turnus_set()
    assert result["name"] == "T26"
```

**`client`** — use this when testing HTTP routes. It gives you a Flask test client with CSRF disabled:

```python
from tests.conftest import login_user

def test_route(client, sample_user):
    login_user(client, sample_user["username"], sample_user["password"])
    resp = client.get("/favorites")
    assert resp.status_code == 200
```

**Pre-built fixtures** for common seed data:

| Fixture | What it inserts |
|---|---|
| `sample_user` | A regular user (`is_auth=0`) |
| `admin_user` | An admin user (`is_auth=1`) |

Both return a dict with `id`, `username`, `password`.

---

## Writing a new service test

Pattern to follow — see `test_favorites_service.py` for a full example:

```python
from app.models import TurnusSet
from app.services import favorites_service


class TestAddFavorite:
    def test_adds_to_empty_list(self, patch_db, db_session):
        # 1. Insert required seed data
        ts = TurnusSet(name="T26", year_identifier="T26", is_active=1)
        db_session.add(ts)
        db_session.commit()

        # 2. Call the service function
        success, msg = favorites_service.add_favorite(
            user_id=1, turnus_set_id=ts.id, shift_title="OSL_01"
        )

        # 3. Assert the result
        assert success is True
        favorites = favorites_service.get_favorite_lst(1, ts.id)
        assert "OSL_01" in favorites
```

Rules:
- Use `patch_db` (not just `db_session`) when calling service functions — they call `get_db_session()` internally
- Insert all required foreign-key records first (TurnusSet before Favorites, etc.)
- Test one behaviour per test function

---

## Writing a new route test

Pattern to follow — see `test_api_routes.py` for a full example:

```python
from tests.conftest import login_user


class TestMyRoute:
    def test_requires_login(self, client):
        resp = client.get("/my-route")
        assert resp.status_code == 302  # redirect to login

    def test_returns_200_when_logged_in(self, client, sample_user):
        login_user(client, sample_user["username"], sample_user["password"])
        resp = client.get("/my-route")
        assert resp.status_code == 200

    def test_post_updates_data(self, client, sample_user):
        login_user(client, sample_user["username"], sample_user["password"])
        resp = client.post("/my-route", data={"field": "value"})
        assert resp.status_code == 302  # redirect after POST
```

For JSON API endpoints:

```python
import json

resp = client.post(
    "/api/some-endpoint",
    data=json.dumps({"key": "value"}),
    content_type="application/json",
)
assert resp.status_code == 200
data = resp.get_json()
assert data["status"] == "success"
```

---

## Patching external dependencies

When a route or service calls something you don't want to run in tests (file I/O, email, etc.), use `monkeypatch`:

```python
def test_with_mocked_data(client, monkeypatch, sample_user):
    login_user(client, sample_user["username"], sample_user["password"])

    # Replace the function at the location it's imported, not where it's defined
    monkeypatch.setattr(
        "app.routes.shifts.mintur._load_mintur_data",
        lambda uid: {"shift_title": "OSL_01", ...}
    )

    resp = client.get("/mintur/export_ical")
    assert resp.status_code == 200
```

**Important:** patch the path where the function is *used*, not where it's *defined*.
For example, `_load_mintur_data` is defined in `app.routes.shifts.mintur` and used there too,
so you patch `app.routes.shifts.mintur._load_mintur_data`.

---

## Common pitfalls

**`patch_db` vs `db_session`**

If you call a service function without `patch_db`, it opens its own database session pointing at the real database (or a different in-memory instance). Your test data won't be visible to it. Always use `patch_db` when testing service functions.

**Import order matters**

`conftest.py` sets environment variables before importing the app. If you import the app at the top of a test file (outside a function), it may run before the env vars are set. Keep app imports inside test functions or fixtures when in doubt.

**SQLite limitations**

The test database is SQLite even if production uses MySQL. Most things work the same, but SQLite doesn't enforce foreign key constraints by default. Tests that rely on cascade behaviour may pass locally but need real data integrity for confidence.

**`db_session.commit()` in tests**

Committing in a test is safe — it only flushes to the current connection's transaction. The outer rollback in `conftest.py` undoes it at the end of the test.
