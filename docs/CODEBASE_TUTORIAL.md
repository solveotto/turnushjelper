# Shift Rotation Organizer — Codebase Tutorial

## 1. The Big Picture

This is a **Flask web application** for train operators at OSL to manage their shift schedules ("turnus"). The architecture follows a clean layered pattern:

```
Browser
  │
  ▼
Flask Routes (blueprints)       ← app/routes/*.py
  │
  ▼
Service Layer                   ← app/services/*.py
  │
  ▼
ORM Models + DB Session         ← app/models.py + app/database.py
  │
  ▼
SQLite (dev) / MySQL (prod)
```

---

## 2. Application Startup — The Factory Pattern

`app/__init__.py` uses Flask's **application factory pattern**:

```python
def create_app():
    app = Flask(__name__)
    app.config.from_object(AppConfig)  # reads from config.py → .env
    mail.init_app(app)
    cache.init_app(app)
    login_manager.init_app(app)
    Session(app)                       # filesystem-backed sessions
    init_default_admin()               # seeds admin if DB is empty
    for blueprint in blueprints:
        app.register_blueprint(blueprint)
    return app
```

- The factory pattern means you can call `create_app()` multiple times with different configs — the test suite uses this to spin up an in-memory SQLite instance without affecting the real DB.
- All Flask extensions (`cache`, `mail`, `login_manager`) are created in `app/extensions.py` **without** an app object, then bound later via `.init_app(app)`. This avoids circular imports between modules that need extensions.

---

## 3. Configuration — Everything from `.env`

`config.py` reads a `.env` file via `python-dotenv` and exposes everything as `AppConfig` class attributes:

```python
class AppConfig:
    SECRET_KEY = _env("SECRET_KEY")        # required — raises if missing
    DB_TYPE    = _env("DB_TYPE", "sqlite") # "sqlite" or "mysql"
    MAILGUN_API_KEY = _env("MAILGUN_API_KEY", "")
    # ... paths, SMTP, token expiry, etc.
```

`get_database_uri()` constructs the connection string dynamically:
- `DB_TYPE=sqlite` → `sqlite:///./dummy.db` (relative to project root)
- `DB_TYPE=mysql`  → `mysql+pymysql://user:pass@host/db`

**Why this matters:** The same codebase runs locally (SQLite, no config needed) and on PythonAnywhere (MySQL, via environment variables) without any code changes.

---

## 4. The Database Layer

Three files collaborate here:

| File | Responsibility |
|---|---|
| `app/database.py` | SQLAlchemy engine, `SessionLocal`, `get_db_session()` |
| `app/models.py` | All 6 ORM model classes |
| `migrations/versions/` | Alembic migration history |

The session pattern used throughout the codebase:

```python
db_session = get_db_session()   # always named db_session (not session!)
try:
    result = db_session.query(DBUser).filter_by(id=user_id).first()
    db_session.commit()
finally:
    db_session.close()           # always closed, even on exceptions
```

- The variable is called `db_session` (not `session`) because Flask also has a `session` object (the user's HTTP session cookie). Naming collisions here would be a subtle, hard-to-debug bug.
- `pool_pre_ping=True` means SQLAlchemy silently reconnects if MySQL dropped an idle connection — essential for the PythonAnywhere prod environment which has aggressive connection timeouts.
- `pool_recycle=300` discards connections older than 5 minutes for the same reason.

---

## 5. The Data Models

Six SQLAlchemy models in `app/models.py`:

```
DBUser                    ← the employee/user account
  │ 1:many
  ├── Favorites            ← their saved shift preferences (per turnus set)
  └── SoknadsskjemaChoice  ← their application form selections

TurnusSet                 ← a rotation year (e.g. "R25", "R26")
  │ 1:many
  └── Shifts               ← the individual shift titles in that year

AuthorizedEmails          ← registration whitelist (by rullenummer)
EmailVerificationToken    ← email verification + password reset tokens
```

A few non-obvious things:

- **Stub users** (`is_stub=1`): When an admin imports an employee PDF, employees get pre-seeded as `DBUser` rows with username `__stub_<rullenummer>` and a random unusable password. When they register, `activate_stub_user()` converts the stub to a real account. This preserves favorites that might have been pre-assigned.
- **`is_auth=1`** means admin (despite the confusing name — it's from an older naming convention).
- **Favorites have `order_index`**: Users can drag-reorder their favorite shifts. The DB stores an integer rank.

---

## 6. The Service Layer — Where Logic Lives

Rather than putting logic in routes, all business operations live in `app/services/`:

```
app/services/
├── turnus_service.py    ← turnus set CRUD (11 functions)
├── user_service.py      ← user management, stub users (20+ functions)
├── favorites_service.py ← favorites add/remove/reorder (7 functions)
└── auth_service.py      ← tokens, verification, password reset (12 functions)
```

**Return type convention** (consistent across all services):

| Operation type | Returns |
|---|---|
| Mutations | `(True, "success msg")` or `(False, "error msg")` |
| Queries | `dict \| None`, `list`, `bool` |
| Complex ops | `dict` with a `'success'` key |

Example:

```python
def add_favorite(user_id, title, order_index, turnus_set_id) -> bool:
    ...
    return True   # simple bool — just a write operation

def verify_token(token) -> dict:
    return {"success": True, "email": "..."} # carries extra data
```

- `app/utils/db_utils.py` is a **re-export facade** — it just imports and re-exports everything from the service modules. This preserved all 19 existing `from app.utils import db_utils` imports during the Phase 3 refactor without changing a single consumer file.
- Cross-service imports (e.g., `favorites_service` needing `turnus_service`) use **deferred imports inside function bodies** to avoid circular import errors at module load time.

---

## 7. Routes — The 7 Blueprints

All registered in `app/routes/main.py`:

| Blueprint | URL Prefix | Purpose |
|---|---|---|
| `auth` | `/` | Login, logout, password reset |
| `shifts` | `/` | Main views: turnusliste, favorites, compare, søknadsskjema |
| `admin` | `/admin` | Admin panel, user/turnus management |
| `api` | `/api` | JSON API for frontend JS |
| `downloads` | `/` | Excel/PDF export |
| `minside` | `/minside` | User profile page |
| `registration` | `/` | Sign-up flow |

The `@admin_required` decorator in `app/decorators.py` handles authorization cleanly:

```python
@admin.route("/admin/users")
@admin_required          # ← also includes @login_required
def users():
    ...
```

It's smart about the request type: returns **403 JSON** for AJAX requests, **redirect** for normal page loads.

---

## 8. The Turnus Data Flow

The "turnus" JSON file is the heart of the app. Here's how shift data moves:

```
PDF file
  │ (pdfplumber via app/utils/pdf/shiftscraper.py)
  ▼
turnus.json   ← stored in app/static/turnusfiler/
  │
  ▼
DataframeManager (df_utils.py)   ← in-memory cache, global per-process
  │
  ▼
Routes read from df_manager.turnus_data
```

The JSON has a tricky structure — metadata keys sit at the same level as week numbers:

```json
{
  "T001": {
    "1": { "1": {...}, "2": {...} },   ← week 1, days 1-7
    "2": { ... },
    "kl_timer": "37.5",               ← metadata! NOT a week
    "tj_timer": "40"
  }
}
```

**Never iterate week values without a type guard.** The canonical helpers in `app/utils/turnus_helpers.py` handle this:

```python
for turnus_name, week_nr, week_data in iter_turnus_weeks(turnus_data):
    # guaranteed: week_data is a dict of days
```

---

## 9. The Frontend Architecture

Templates use Jinja2 + Bootstrap 5. JS is split into ES modules under `app/static/js/modules/`:

**Key modules:**

| Module | Purpose |
|---|---|
| `shift-colors.js` | Applies CSS color classes based on shift start time |
| `color-adjustment.js` | User-customized colors from localStorage |
| `lazy-tables.js` | IntersectionObserver — only renders visible turnus tables |
| `favorites.js` | Drag-to-reorder, badge count updates |

**Shift color system** — purely start-time-based:

```
Before 06:00  →  .night-early  (dark blue)
06:00–07:59   →  .morning      (medium blue)
08:00–11:59   →  .midday       (sky blue)
12:00–16:59   →  .afternoon    (pink)
17:00+        →  .evening      (purple)
```

- `/turnusliste` has hundreds of table rows. Without `lazy-tables.js`, the browser renders all of them on page load, which is slow. The `<template data-lazy-table>` pattern defers rendering until the row scrolls into view — a big performance win with no visible difference to the user.
- `toggle_favorite` on the API returns both `favorites` (ordered list) AND `positions` (rank dict). If you ever add a code path that returns `{"status": "success"}` without those fields, the favorites badge in the UI will silently fail to update — no error, just stale state.

---

## 10. The Søknadsskjema Feature

The newest feature (`/soknadsskjema`) lets users generate a Word document application form.

**GET**: Renders the form, pre-fills personal info from `DBUser`, and loads the favorites list.

**POST**: Generates a `.docx` using `python-docx`:

```
DBUser (name, rullenummer, stasjoneringssted)
  +
get_favorite_lst() → [shift_title, ...]
  +
SoknadsskjemaChoice rows (linje_135, linje_246, h_dag, linjeprioritering)
  ↓
_build_soknadsskjema_doc() → NamedTemporaryFile
  ↓
send_file() → browser download → response.call_on_close(cleanup)
```

The `call_on_close` pattern ensures the temp file is deleted **after** the response is fully sent — not before, which would corrupt the download.

---

## 11. Database Migrations

Schema is managed exclusively by Alembic. Migration versions in order:

```
000_initial_schema.py                        ← all original tables
001_add_email_verification_tokens.py
002_authorized_emails_rullenummer_only.py    ← email no longer required
003_stub_users.py                            ← adds is_stub, stasjoneringssted, seniority_nr, etc.
006_soknadsskjema_choices.py                 ← the new feature's table
```

To apply all migrations: `alembic upgrade head`

---

## 12. Where to Start Exploring

Trace a user interaction end-to-end by following these entry points:

1. **User logs in** → `app/routes/auth.py:login()`
2. **Sees their turnus** → `app/routes/shifts.py:turnusliste()`
3. **Stars a shift** → `app/routes/api.py:toggle_favorite()` → `favorites_service.add_favorite()`
4. **Downloads application form** → `app/routes/shifts.py:soknadsskjema()` → `_build_soknadsskjema_doc()`
5. **Admin uploads new PDF** → `app/routes/admin.py` → `app/utils/pdf/shiftscraper.py`

The codebase is well-layered — routes are thin (validate input, call service, return response), services own the logic, and models own the data shape. Following that flow in any feature will give you a complete picture quickly.
