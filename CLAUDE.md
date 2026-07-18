# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Turnushjelper** is a Flask web app for transit shift workers (Oslo/OSL) to manage their shift schedules ("turnus"). Workers can browse the shift rotation schedule, mark favorites, build a personal schedule, and generate an application form for shift preference.

## Commands

**`python`, `pytest`, and `alembic` are NOT on PATH on the dev machine — always use the `venv/bin/` prefix.**

```bash
# Run development server (port 8080, debug on by default)
venv/bin/python run.py

# Run all tests
venv/bin/pytest

# Run a single test file
venv/bin/pytest tests/test_favorites_service.py

# Run a single test or class
venv/bin/pytest tests/test_auth_service.py::TestVerifyPassword::test_correct_password_returns_true

# Stop on first failure, no output truncation
venv/bin/pytest -x -s

# Database migrations
venv/bin/alembic upgrade head          # apply all pending migrations
venv/bin/alembic current               # show current revision
venv/bin/alembic downgrade -1          # roll back one migration
venv/bin/alembic revision --autogenerate -m "description"  # generate from model changes
```

## Environment Setup

Copy `.env.example` to `.env`. Minimum required for local dev:

```
SECRET_KEY=any-random-string
DB_TYPE=sqlite
SQLITE_PATH=./dummy.db
```

**First-time admin:** there is no default admin password — a fresh database
does not auto-create an `admin`/`admin` account. Bootstrap the first admin via
`docs/guides/ADMIN_BOOTSTRAP.md` (set a strong `DEFAULT_ADMIN_PASSWORD` for one
startup, or run the one-off `create_user(..., is_auth=1)` command).

## Architecture

The app follows a strict three-layer pattern: **Routes → Services → Database**.

```
app/routes/       ← Flask blueprints (HTTP, no business logic)
app/services/     ← Business logic (called by routes)
app/models.py     ← SQLAlchemy ORM models
app/database.py   ← Engine + get_db_session()
```

Blueprints registered in `app/routes/main.py`: `auth`, `shifts`, `admin`, `api`, `downloads`, `minside`, `registration`.

### Database Session Pattern

The project uses **raw SQLAlchemy sessions**, not Flask-SQLAlchemy's `db.session`. Every service function follows this pattern:

```python
def some_service():
    db_session = get_db_session()
    try:
        # ... do work ...
        db_session.commit()
        return result
    except Exception as e:
        db_session.rollback()
        return error
    finally:
        db_session.close()
```

Never use `db.session` — it does not exist here.

### Two User Classes

- `DBUser` (SQLAlchemy model, table `users`) — ORM object stored in DB
- `User` (Flask-Login `UserMixin`) — lightweight wrapper used in `current_user`. `is_auth=1` means admin.

`current_user.is_admin` maps to `DBUser.is_auth`. Use `@admin_required` from `app/decorators.py` (includes `@login_required`).

### Turnus Data

Static JSON files live in `app/static/turnusfiler/{year_id}/`:
- `turnus_schedule_{ID}.json` — full schedule
- `turnus_stats_{ID}.json` — stats/dataframe
- `double_shifts_{id}.json` — double shift data

Active turnus set is stored in `TurnusSet` table (`is_active=1`). `DataframeManager` in `app/utils/df_utils.py` loads and caches the JSON into a pandas DataFrame.

**PII files never go under `app/static/`** — everything there is served without authentication. `medlemsliste.xlsx`, `ansinitet.pdf`, and `innplassering_{YEAR}.pdf` live in `instance/protected/` via `app/utils/protected_paths.py` (`AppConfig.protected_dir`); enforced by `tests/test_protected_files.py`. See `docs/guides/PROTECTED_FILES.md`.

The schedule JSON is an abstract 6-week rotation with no calendar dates. The only calendar-date source is the Excel template `turnusnøkkel_{YEAR}_org.xlsx` (sheet `Turnusnøkkel`, 6 groups × 8 rows, dates in columns H–P). A worker on linje `j` follows rotation week `((g + j - 1) % 6) + 1` during nøkkel group `g`.

### Turnus Data Sources & Ingestion

- **Primary source is the "Timeskjema" export** (decided 2026-07-08; parser lives on branch `ny_shift_ingress`). The employer's `.xls` export is **not real Excel** — it is tab-separated ISO-8859-1 text. The PDF scraper (`ShiftScraper`, hardcoded pixel bounding boxes) is the cross-verification and fallback path only; do not invest in the pixel-extraction engine.
- **`validate_turnus_json`** (`app/utils/pdf/scraper_validator.py`) is the single source-agnostic gate every ingestion path passes — harden the validator, not the extractors. Consumers (e.g. kompdag counting) require string week/day keys (JSON round-trip form); in-memory parser output has int keys — always go through the written JSON.
- **Cross-source verification must never hard-fail on inequality** — sources can be different planning revisions. Verified example: the two R26 sources in `app/static/turnusfiler/r26/` differ in 20 of ~2,394 day-cells (`Oslo R26 etter listemøte.pdf`, printed 09.10.2025, vs the later `R26 endelig.xls`) despite carrying the same dataset label. Render a diff for admin adjudication instead of failing.
- **Timeskjema TSV parsing traps**: accounting-week grouping (Sunday-night shifts are listed in the next week's Sum-uke block), a trailing station-summary section with its own `Totalsummer` row, `&` suffixes on values, and the `Ruteterminperiode:` header being wrong (use the `Rutetermin:` dates).
- **Hours cross-check calibration**: `kl_timer` = paid time after unpaid-break deductions; the raw sum of shift spans is always ≥ `kl_timer`, by 0 to ~10h. Hence the one-sided band `_HOURS_TOL_LOW`/`_HOURS_TOL_HIGH` in `scraper_validator.py`. `tj_timer` (service hours) is much larger and not usable as an anchor. Re-run the calibration against committed R25/R26 data before retuning these tolerances — never assume summed spans equal `kl_timer`.
- **Strekliste PNGs**: ruler/crop geometry auto-calibrates per page from the PDF's printed 0–23 hour header (`compute_page_geometry` / `get_hour_label_positions` in `app/utils/pdf/strekliste_generator.py`, with the legacy hand-calibrated constants as fallback; golden anchors for r26 in `tests/test_strekliste_geometry.py`: hour 0 at x≈103.5, hour 23 at ≈793.5, 30 pt/hour). The PNGs are generated files (not in git), so **stale PNGs from the previous PDF look correct until someone regenerates** — always regenerate after any streker-PDF swap. If a future PDF misaligns, check `get_hour_label_positions` against it rather than re-tuning the fallback constants.

### Kompdager

All logic lives in `app/utils/kompdag_utils.py`. A kompdag is generated when a rostered fridag falls on a helge-/høytidsdag (overenskomsten §5.13.1). Holiday dates are **computed** (fixed dates + Easter-offset formula in `_easter()`), never read from the Excel's red font (which is manually colored and incomplete) and never fetched externally. Counting rules (all user-confirmed):

- `X`, `O`, `T` fridager trigger a kompdag; blank days **adjacent to a night shift** (any shift crossing midnight, including e.g. 15:35–00:20) do not — they are the sleep-off part of the shift span. Adjacency wraps across the rotation (week 1 day 1 ← week 6 day 7).
- Holidays falling on a **Sunday** never trigger (so 1. påskedag and 1. pinsedag never do; 17. mai doesn't in years when it's a Sunday).
- Holidays **after 12. desember of the rutetermin's final calendar year** belong to the next rutetermin and don't count. A rutetermin spans two calendar years (R26 = des 2025 – des 2026), so holidays are unioned across both years — jul in the *leading* December counts.

Display vs counting: the red date marking in turnusnøkkel/mintur uses the **full** holiday set (`get_holidays_for_dates`); only the count applies the exclusions (`get_kompdag_holidays`). Counts are per linje (they differ a lot between linjer). Shown as badges on the linje buttons in turnusnøkkel, as `Kompdager (maks)` = `"4 (L1)"` in turnusliste/favorites, and as the exact count for the user's linje in mintur. When the nøkkel Excel is missing, `count_kompdager()` returns `None` → templates show `–`/hide badges (never fake zeros).

Reference counts (asserted in `tests/test_kompdag_routes.py`): OSL_01 R26 = `[4, 1, 3, 2, 2, 4]`. If counting rules change, re-derive these before updating the tests.

### Caching

Flask-Caching (in-memory, simple). Key patterns:
- `tour_state_{user_id}` — 60s
- `has_min_turnus_{user_id}` — 60s
- `pdf_downloads_{year_id}` — 300s
- `turnus_data_{turnus_set_id}` — loaded in DataframeManager
- `kompdager_{turnus_set_id}` — 3600s, per-linje kompdag counts

When modifying a user's DB columns, invalidate the relevant cache keys.

### Frontend

`app/static/js/main.js` is the ES module entry point, importing from `app/static/js/modules/`. Each module is a class. CSS is organized in `app/static/css/` by `base/`, `components/`, `layout/`, and per-feature files.

UI language is **Norwegian**. Code and comments are in English.

## Code Style

- Norwegian UI text, English code/comments
- Purple gradient theme: `#667eea` to `#764ba2`
- CSS classes: `.modern-card`, `.card-header-modern`, `.form-control-modern`
- Pages extending `base.html` use `{% block extra_css %}` for additional CSS
- Standalone pages (login, register) link CSS directly in `<head>`
- Bootstrap 5 + Bootstrap Icons (`bi-*`)
- No inline `<style>` blocks — shared CSS files only

## Testing

Tests use an **in-memory SQLite database** with per-test transaction rollback (never persists state). Three fixture layers in `tests/conftest.py`:

- `db_session` — raw SQLAlchemy session for inserting seed data directly
- `patch_db` — also monkeypatches `get_db_session` in all service modules; **required when calling service functions**
- `client` — Flask test client with CSRF disabled, depends on `patch_db`

Pre-built fixtures: `sample_user` (regular, `is_auth=0`), `admin_user` (`is_auth=1`) — both return `{"id", "username", "password"}`.

```python
# Service test pattern
def test_something(patch_db, db_session):
    ts = TurnusSet(name="T26", year_identifier="T26", is_active=1)
    db_session.add(ts); db_session.commit()
    result = turnus_service.get_active_turnus_set()
    assert result["name"] == "T26"

# Route test pattern
from tests.conftest import login_user
def test_route(client, sample_user):
    login_user(client, sample_user["username"], sample_user["password"])
    resp = client.get("/favorites")
    assert resp.status_code == 200
```

Patch at the **use site**, not the definition site: `monkeypatch.setattr("app.routes.shifts.mintur._load_mintur_data", ...)`.

## Migrations

Schema changes always go through Alembic. After modifying `app/models.py`:
1. `venv/bin/alembic revision --autogenerate -m "description"` — review the generated file before applying
2. `venv/bin/alembic upgrade head`

Tests use `Base.metadata.create_all()` directly and do not go through Alembic.
