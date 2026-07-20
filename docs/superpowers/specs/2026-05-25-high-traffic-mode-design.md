# High-Traffic Mode Design

**Date:** 2026-05-25  
**Status:** Approved (post-review)

## Background

The "break-glass" high-traffic mode was described in CLAUDE.md but never implemented as a branch. Most features turned out to already be present in `development`:

| Feature | Status |
|---|---|
| Route cache on `/turnusliste` (120s) | Already done |
| Cache invalidation in `toggle_favorite` | Already done |
| Cache invalidation in `switch_user_year` | Already done |
| MySQL pool size 10/20 | Already done |
| SQLAlchemy-backed sessions | **Missing** |
| `gunicorn.conf.py` | **Missing** |

This spec covers only the two missing pieces.

## 1. SQLAlchemy-Backed Sessions

### Problem

Current session storage is filesystem-based (`SESSION_TYPE = "filesystem"`). Under load, filesystem I/O for every request adds latency and contention. Sessions also can't be shared across multiple processes cleanly.

### Approach

Write a custom `SessionInterface` subclass (`app/utils/sa_session_interface.py`) using the existing `engine` and `SessionLocal` from `app/database.py`. No new dependencies.

The flask-session library's built-in SQLAlchemy backend was rejected because it requires Flask-SQLAlchemy, which the project deliberately avoids.

### Schema

New table `flask_sessions`:

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | auto-increment |
| `session_id` | String(255) | unique, indexed |
| `data` | LargeBinary | JSON-serialized session dict (UTF-8 bytes) |
| `expiry` | DateTime | used to prune stale sessions |

Created via Alembic migration `011_flask_sessions.py`.

Serialization uses JSON (UTF-8 bytes), not pickle — session dicts hold only
JSON-safe primitives, and JSON removes the pickle deserialization gadget surface
should the DB ever be compromised. Legacy pickle rows written before the
cut-over fail to parse and are treated as a fresh session (a one-time logout).

### Session Interface

`app/utils/sa_session_interface.py` implements `open_session()` and `save_session()`.

**`open_session()`:**
- Read signed `session_id` from cookie
- Look up row in `flask_sessions` by `session_id`
- If row not found or `expiry < now`: return empty session
- JSON-decode `data` and return (unparseable legacy rows → empty session)

**`save_session()`:**

1. **Empty session (logout):** If the session is empty, delete the DB row and clear the cookie. Do not upsert an empty dict — Flask-Login relies on the cookie being cleared.

2. **Non-empty session (upsert):**
   - Expiry: if `session.permanent` is `True`, use `app.permanent_session_lifetime` (Flask's `PERMANENT_SESSION_LIFETIME` config, default 31 days). If `False` (non-permanent / no "remember me"), use a short server-side TTL of 1 hour — the session expires on the server but the cookie remains until browser close.
   - Upsert strategy:
     - **SQLite:** `INSERT OR REPLACE INTO flask_sessions ...` (handles unique constraint atomically)
     - **MySQL:** `INSERT ... ON DUPLICATE KEY UPDATE data=..., expiry=...`
     - Implementation uses a try/except on `IntegrityError` as a portable fallback if dialect-specific syntax is avoided.

3. **Expired-session cleanup:** On ~1% of `save_session()` calls (random check), delete all rows where `expiry < now`. Avoids a background job while keeping the table bounded.

### Integration

In `app/__init__.py`, replace:
```python
from flask_session import Session
...
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = AppConfig.sessions_dir
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_KEY_PREFIX"] = "session:"
Session(app)
```

With:
```python
from app.utils.sa_session_interface import SqlAlchemySessionInterface
app.session_interface = SqlAlchemySessionInterface()
```

Also remove `Flask-Session==0.8.0` from `requirements.txt` (dead dependency once the custom interface is in place).

### Deployment Note

On first deploy, all existing filesystem session IDs become invalid. Users are logged out once. This is expected.

### Testing

`tests/test_sa_session_interface.py` covers:
- New session (no cookie): returns empty session
- Existing session: loads correctly from DB
- Modified session: saves updated data
- Empty session (logout): deletes DB row, clears cookie
- Expired session: treated as new session
- `session.permanent = True`: uses `PERMANENT_SESSION_LIFETIME`
- `session.permanent = False`: uses 1-hour server-side TTL

Works identically on SQLite (dev) and MySQL (prod). The `flask_sessions` table is created via `alembic upgrade head`, or `Base.metadata.create_all()` in tests.

## 2. Gunicorn Config

`gunicorn.conf.py` at project root.

**Scope:** This file only applies when gunicorn is run explicitly (VPS deployment or a manual process). **PythonAnywhere's standard WSGI hosting runs its own WSGI container — it does not use gunicorn automatically.** The file is included for VPS readiness and manual use.

```python
workers = 2          # safe for PythonAnywhere memory limits; tune up on VPS
worker_class = "gthread"
threads = 4          # 2 workers × 4 threads = 8 concurrent requests
timeout = 60
keepalive = 5
bind = "0.0.0.0:8080"
accesslog = "-"
errorlog = "-"
```

`gthread` is appropriate for I/O-bound Flask (DB queries, file reads).

## Files Changed

- `app/utils/sa_session_interface.py` — new file, custom session interface
- `migrations/versions/011_flask_sessions.py` — new Alembic migration
- `app/__init__.py` — swap session config, remove `flask_session` import
- `requirements.txt` — remove `Flask-Session==0.8.0`
- `gunicorn.conf.py` — new file at project root
- `tests/test_sa_session_interface.py` — new test file
- `docs/guides/HIGH_TRAFFIC_MODE.md` — operator runbook
