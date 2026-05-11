---
title: Navigation Performance Improvements
date: 2026-05-11
status: approved
---

## Goal

Make page-to-page navigation feel faster with minimal code change and no architectural risk.

## Changes

### 1. instant.page (base.html)

Add one `<script>` tag to the bottom of `<head>` in `app/templates/base.html`.

instant.page intercepts hover/focus events on `<a>` tags and prefetches the target page in the background. By the time the user clicks, the HTML is already fetched. No configuration, no Flask changes, no impact on existing JS.

Tag to add:
```html
<script src="//instant.page/5.2.0" type="module" integrity="sha384-jnZyxPjiipYXnSU+ygvrkboMaBy1u5T7OcKSfBQcqhYs3XLDlPJYS1gASAlpEqF"></script>
```

### 2. Cache /oversikt (oversikt.py)

`/oversikt` is the most expensive uncached route: it builds a `DataframeManager` for the user's turnus set and additional ones per innplassering row on every request.

Add `@cache.cached` using the same pattern as `/turnusliste`:
- Per-user, per-turnus-set cache key
- Flash-message bypass (unique key when flashes pending)
- Timeout: 300s (longer than turnusliste's 120s — oversikt data changes even less often)
- Cache invalidation: `toggle_favorite` in `app/routes/api.py` must also delete `view/oversikt/{user_id}/{ts_id}` immediately after the existing turnusliste invalidation (api.py ~line 55). Without this, the `favoritt` list rendered in the oversikt modal stays stale for up to 300s after a favorite toggle.

Cache key format: `view/oversikt/{user_id}/{ts_id}`

### 3. Skip /favorites caching

The favorites page renders the user's current favorites list. It changes whenever the user toggles a star. Caching it without invalidation wired into the toggle API would show stale content. Not worth the complexity.

## Files Changed

| File | Change |
|------|--------|
| `app/templates/base.html` | Add instant.page `<script>` tag |
| `app/routes/shifts/oversikt.py` | Add `_oversikt_cache_key()` + `@cache.cached` |
| `app/routes/api.py` | Add oversikt cache invalidation in `toggle_favorite` |
