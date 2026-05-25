# High-Traffic Mode — Operator Runbook

This guide covers what to do when the site becomes slow or unresponsive.

## Current State (as of 2026-05-25)

These improvements are already active in `main`/`development`:

| Feature | Status |
|---|---|
| SQLAlchemy-backed sessions | Active |
| 120s route cache on `/turnusliste` | Active |
| Cache invalidation on favorite toggle | Active |
| MySQL connection pool (10/20) | Active |
| Gunicorn gthread config | Available (`gunicorn.conf.py`) |

## Step 1: Check what's slow

- PythonAnywhere dashboard → Web tab → error log
- If you see MySQL "too many connections" errors → reduce `pool_size` in `app/database.py`
- If you see slow page loads → likely the `/turnusliste` cache miss; check cache hit rate

## Step 2: Restart the app

On PythonAnywhere: Web tab → Reload.

This clears the in-process `SimpleCache` (Flask-Caching `simple` backend). Do this first — it's free.

## Step 3: Upgrade PythonAnywhere plan

If the app is consistently slow (not spiky), upgrade to a higher PythonAnywhere plan tier for more workers and RAM.

## Step 4: Move to a VPS (Hetzner / DigitalOcean)

If you need more than PythonAnywhere can offer:

1. Provision a Linux VPS (Hetzner CX22 is a good starting point)
2. Clone the repo, install dependencies: `pip install -r requirements.txt`
3. Apply migrations: `alembic upgrade head`
4. Run with gunicorn: `gunicorn -c gunicorn.conf.py run:app`

### Gunicorn tuning

`gunicorn.conf.py` default: 2 workers × 4 threads = 8 concurrent requests.

**Note:** `gunicorn.conf.py` does NOT apply on PythonAnywhere's standard WSGI hosting — only on a VPS or if you run gunicorn manually.

To scale up on a VPS with more RAM:
```python
workers = 4    # each worker uses ~150–200 MB
threads = 4
```

## Session behaviour on first deploy

When the SQLAlchemy session backend was activated, all existing filesystem session IDs became invalid. Users were logged out once. This is a one-time event.

Future deploys do not log users out (sessions persist in the DB).
