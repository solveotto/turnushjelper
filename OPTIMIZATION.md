# Performance Optimization Plan

## Summary of issues found

| # | Issue | Severity | File |
|---|-------|----------|------|
| 1 | Context processor runs 3 DB queries on every page load | Critical | `app/__init__.py:58-80` |
| 2 | N+1 query in `update_favorite_order` | High | `app/services/favorites_service.py:63-76` |
| 3 | O(n²) membership test in favorites route | Medium | `app/routes/shifts.py:279-282` |
| 4 | Missing DB indexes on hot query paths | Medium | `app/models.py` + new migration |
| 5 | Bootstrap JS + driver.js block HTML parsing | Medium | `app/templates/base.html:16,22` |
| 6 | Duplicate `<meta charset>` and `<meta viewport>` tags | Minor | `app/templates/base.html:4-9` |

---

## 1. Cache the context processor (CRITICAL)

`inject_tour_state()` in `app/__init__.py` fires on every request and hits the DB three times:
1. `DBUser` query (to read `rullenummer`)
2. `TurnusSet` query (active set)
3. `Innplassering` query (to compute `has_min_turnus`)

The `has_seen_tour` / `has_seen_favorites_tour` values come from Flask session (no DB cost). Only `has_min_turnus` needs to be cached.

**Fix:** Wrap the DB block with `cache.get/set` keyed by user ID, TTL=60s.

```python
@app.context_processor
def inject_tour_state():
    if current_user.is_authenticated:
        from app.models import Innplassering, TurnusSet
        cache_key = f"has_min_turnus_{current_user.id}"
        has_min_turnus = cache.get(cache_key)
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
            cache.set(cache_key, has_min_turnus, timeout=60)
        return {
            "has_seen_tour": session.get('has_seen_tour', 0),
            "has_seen_favorites_tour": session.get('has_seen_favorites_tour', 0),
            "has_min_turnus": has_min_turnus,
        }
    return {"has_seen_tour": 0, "has_seen_favorites_tour": 0, "has_min_turnus": False}
```

Note: if an admin updates innplassering, the cached value stays stale for up to 60s. That's acceptable. If you want immediate invalidation, call `cache.delete(f"has_min_turnus_{user_id}")` in the admin route that writes innplassering.

---

## 2. Fix N+1 in `update_favorite_order` (HIGH)

**File:** `app/services/favorites_service.py:63-76`

Current code loads all favorites, then re-queries each one individually:

```python
# BAD: re-queries objects already loaded
current_favorites = db_session.query(Favorites).filter_by(...).all()
current_shift_titles = [f.shift_title for f in current_favorites]
for index, shift_title in enumerate(current_shift_titles):
    favorite = db_session.query(Favorites).filter_by(shift_title=shift_title, ...).first()
    if favorite:
        favorite.order_index = index
```

**Fix:** Update the already-loaded objects directly:

```python
current_favorites = db_session.query(Favorites).filter_by(
    user_id=user_id,
    turnus_set_id=turnus_set_id
).all()

for index, favorite in enumerate(current_favorites):
    favorite.order_index = index

db_session.commit()
```

---

## 3. Fix O(n²) loop in favorites route (MEDIUM)

**File:** `app/routes/shifts.py:279-282`

`fav_order_lst` is a list. The `in` check inside the loop is O(n) per iteration, making the whole block O(n²).

```python
# BAD
for x in user_df_manager.turnus_data:
    for name, data in x.items():
        if name in fav_order_lst:   # O(n) list scan every time
            fav_dict_lookup[name] = data
```

**Fix:** Convert to a set first:

```python
fav_set = set(fav_order_lst)
for x in user_df_manager.turnus_data:
    for name, data in x.items():
        if name in fav_set:         # O(1) set lookup
            fav_dict_lookup[name] = data
```

---

## 4. Add missing DB indexes (MEDIUM)

Create a new Alembic migration:

```bash
alembic revision -m "add performance indexes"
```

Migration content:

```python
def upgrade():
    # favorites: most queries filter by (user_id, turnus_set_id)
    op.create_index('ix_favorites_user_ts', 'favorites', ['user_id', 'turnus_set_id'])
    # innplassering: context processor and mintur route filter by both columns
    op.create_index('ix_innplassering_ts_rullenr', 'innplassering', ['turnus_set_id', 'rullenummer'])
    # user_activity: admin dashboard orders by timestamp
    op.create_index('ix_user_activity_timestamp', 'user_activity', ['timestamp'])

def downgrade():
    op.drop_index('ix_favorites_user_ts', table_name='favorites')
    op.drop_index('ix_innplassering_ts_rullenr', table_name='innplassering')
    op.drop_index('ix_user_activity_timestamp', table_name='user_activity')
```

Then apply: `alembic upgrade head`

---

## 5. Defer blocking JS (MEDIUM)

**File:** `app/templates/base.html:16,22`

Bootstrap JS (line 16) and driver.js (line 22) are loaded synchronously in `<head>`, blocking HTML parsing. Add `defer` to both script tags.

Also, the inline `<script>` block on lines 17-21 references Bootstrap events and must be moved to the end of `<body>` (before `</body>`) so it runs after the deferred scripts are loaded.

---

## 6. Remove duplicate meta tags (MINOR)

**File:** `app/templates/base.html:4-9`

Lines 4-5 and 8-9 are identical duplicates:
- `<meta charset="UTF-8">` / `<meta charset="utf-8">`
- `<meta name="viewport" ...>` × 2

Remove lines 8-9 (keep the first occurrence on lines 4-5).

---

## Verification

After making changes:

```bash
# Run tests
pytest

# Apply DB migration
alembic upgrade head

# Start dev server and check pages manually
python run.py
```

Check in browser DevTools:
- Network tab: Bootstrap JS waterfall should no longer block parsing
- Console: no JS errors from deferred scripts
- Server logs: DB queries should not fire on every request (context processor cache hit after first load)
