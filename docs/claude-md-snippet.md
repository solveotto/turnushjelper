# Guided Tour System & Alembic Migrations

## Alembic (Database Migrations)

Schema changes are managed with Alembic. The config lives in `alembic.ini` and migrations in `migrations/`.

### Key files
- `alembic.ini` — config, points to `migrations/` directory
- `migrations/env.py` — loads `Base` and all models with Flask dependency stubs (so Alembic CLI works without Flask installed)
- `migrations/versions/` — migration scripts

### Workflow after changing `app/models.py`
```bash
alembic revision --autogenerate -m "description of change"
alembic upgrade head
```

### How it runs in production
`app/__init__.py` calls `_run_migrations()` after `create_tables()` on every app startup. This runs `alembic upgrade head` automatically. If Alembic fails (e.g. missing package), it logs a warning and the app still starts.

### env.py stubs
`migrations/env.py` stubs out `flask_login`, `bcrypt`, `app.extensions`, and the `app` package itself so that `app.models` can be imported without Flask. If you add new top-level imports to `models.py`, you may need to add corresponding stubs in `env.py`.

---

## Guided Tour (Driver.js)

Step-by-step onboarding popups using Driver.js v1.3.1 (loaded via CDN). Tour completion is tracked per-user in the database.

### Architecture
```
app/static/js/modules/guided-tour.js              — Tour manager (shared logic)
app/static/js/modules/tour-definitions/*.js        — Per-page step definitions
app/static/css/components/guided-tour.css          — Styling overrides
```

### How it works
1. Each page that has a tour adds `data-tour-seen="{{ has_seen_tour }}"` and `data-tour-page="pagename"` to its `.page-layout` div
2. `guided-tour.js` reads `data-tour-seen` — if `"0"`, auto-starts the tour after 1s
3. The "Hjelp" button in the navbar (`#start-tour-btn`) re-triggers the tour anytime
4. On tour complete/close, JS calls `POST /api/mark-tour-seen` with `{"tour_name": "pagename"}`
5. The API sets the corresponding `has_seen_X_tour` column to `1` in the `users` table

### Per-tour database tracking
Each tour has its own column on `DBUser` (e.g. `has_seen_turnusliste_tour`). This means users can complete tours independently — seeing one tour does NOT mark others as seen.

The `tour_columns` dict in `app/routes/api.py` → `mark_tour_seen()` maps tour names to column names and acts as a whitelist.

### Adding a new tour
1. Add column to `DBUser` in `app/models.py`: `has_seen_X_tour: Mapped[int] = mapped_column(Integer, default=0)`
2. Run migration: `alembic revision --autogenerate -m "add X tour tracking"` + `alembic upgrade head`
3. Create step definitions in `app/static/js/modules/tour-definitions/X-tour.js`
4. Add page detection case in `guided-tour.js` → `getStepsForCurrentPage()`
5. Add entry to `tour_columns` dict in `app/routes/api.py`
6. In the route, query `has_seen_X_tour` and pass as `has_seen_tour` to the template
7. Add `data-tour-seen="{{ has_seen_tour }}" data-tour-page="X"` to the template's container div

Full guide with code examples: `docs/adding-guided-tours.md`

### Tour step types
- **Anchored**: `{ element: '.selector', popover: {...} }` — highlights a specific UI element
- **Centered**: `{ popover: {...} }` (no `element`) — informational popup in the center of the screen
