# Multi-Depot Turnus Sets

**Question:** What would it take to support different turnus sets for users from different depots (e.g., OSLO vs other locations)?

## Current Architecture

### TurnusSet model (`app/models.py`)
```python
class TurnusSet(Base):
    id               = Column(Integer, primary_key=True)
    name             = Column(String(255))
    year_identifier  = Column(String(10), unique=True)  # e.g. "R25", "R26"
    is_active        = Column(Integer, default=0)        # 1 = system-wide active set
    turnus_file_path = Column(String(500))
    df_file_path     = Column(String(500))
```

No depot/location field. `is_active` is system-wide — only one set is active at a time.

### User-to-set association
- No FK from `DBUser` to `TurnusSet`
- All users see all turnus sets
- Users pick a set per-session via `session['user_selected_turnus_set']`
- Fallback: system-wide `is_active=1` set from DB

### Key code paths
| Concern | File | Function |
|---------|------|----------|
| Resolve active set for user | `app/utils/turnus_helpers.py` | `get_user_turnus_set()` |
| System-wide active set | `app/services/turnus_service.py` | `get_active_turnus_set()` |
| All sets (for dropdown) | `app/services/turnus_service.py` | `get_all_turnus_sets()` |
| Admin switch (system-wide) | `app/routes/admin/turnus.py` | `switch_turnus_set()` POST |
| User switch (session) | `app/routes/shifts/turnusliste.py` | `switch_user_year()` |

Favorites are already scoped by `turnus_set_id` (no changes needed there).

---

## What Multi-Depot Support Would Require

### DB changes (minor, additive only)
- Add `depot` column to `TurnusSet` — tags which depot a set belongs to
- Add `depot` column to `DBUser` — determines which sets a user should see

Two new columns. No existing tables restructured, no new join tables. Two Alembic migrations.

### App logic changes (moderate)
- `get_all_turnus_sets()` — filter by current user's depot
- `get_user_turnus_set()` — fallback to active set *for their depot*, not system-wide
- Year-switcher dropdown in `base.html` — only show depot-relevant sets
- Admin UI — assign depot when creating/editing sets and users
- `switch_turnus_set()` admin route — "set active" concept needs to become per-depot

### What stays the same
- Favorites table and all favorites logic
- Session-based switching mechanism
- Cache key pattern (`view/turnusliste/{user_id}/{ts_id}`)
- Data loading pipeline, JSON files, PDF/Excel logic
- `turnus_helpers.py` resolution priority (session → DB fallback)

### Hardest design decision
The current `is_active=1` flag is one system-wide marker. With multiple depots it either becomes
per-depot (each depot has its own "active" set) or gets dropped entirely in favour of the session
choice + a per-user default. The per-depot `is_active` approach is simpler and keeps the existing
fallback logic mostly intact.

---

## Verdict
Medium-sized feature. No structural overhaul needed — two new DB columns and filtering logic in
a handful of places. The admin UI work is probably the most time-consuming part.
