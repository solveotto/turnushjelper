# High-Traffic Mode — Operator Runbook

This guide covers what to do when the site becomes slow or unresponsive.

## Current State (as of 2026-05-25)

These improvements are already active in `main`/`development`:

| Feature | Status |
|---|---|
| SQLAlchemy-backed sessions | Active |
| Shared data caches (`turnus_data_*`, `kompdager_*`) | Active |
| Per-user route cache on `/turnusliste` and `/oversikt` | **Removed** (2026-07-28) |
| MySQL connection pool (10/20) | Active |
| Gunicorn gthread config | Available (`gunicorn.conf.py`) |

`/turnusliste` and `/oversikt` render fresh on every request — measured at **33 ms**
and **17 ms** with the data caches warm. The per-user page cache they replaced saved
about that much while storing a **3.7 MiB** entry per user per worker, and made every
writer of user state responsible for invalidating it (two stale-favorites bugs). If
page caching is ever needed again, key it on the turnus set alone, never on the user.

## Step 1: Check what's slow

```bash
# App errors
sudo journalctl -u turnushjelper --since "1 hour ago"
sudo tail -f /var/log/turnushjelper/error.log

# MySQL connections
sudo mysql -e "SHOW STATUS LIKE 'Threads_connected';"
```

- If you see MySQL "too many connections" errors → reduce `pool_size` in `app/database.py`
- If you see slow `/turnusliste` loads → check whether `turnus_data_*` / `kompdager_*` are
  being repopulated on every request (the render itself is ~33 ms; a cold kompdag count
  parses the nøkkel Excel). The page is 3.7 MiB, so also rule out client bandwidth.

## Step 2: Restart the app

```bash
sudo systemctl restart turnushjelper
```

This clears the in-process `SimpleCache` (Flask-Caching `simple` backend). Do this first.

## Step 3: Scale up gunicorn workers

Edit `/etc/systemd/system/turnushjelper.service` and increase `--workers`:

```bash
sudo systemctl edit turnushjelper
# or edit the service file directly and reload:
sudo systemctl daemon-reload && sudo systemctl restart turnushjelper
```

`gunicorn.conf.py` default: 2 workers × 4 threads = 8 concurrent requests.
Each worker uses ~150–200 MB RAM — check available memory with `free -h` before scaling.

```python
workers = 4    # on a CX32 or larger
threads = 4
```

## Session behaviour on first deploy

When the SQLAlchemy session backend was activated, all existing filesystem session IDs became invalid. Users were logged out once. This is a one-time event.

Future deploys do not log users out (sessions persist in the DB).
