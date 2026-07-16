# Testing the Security Fixes

How to verify the 2026-07 security review fixes — first on your **development
machine** (SQLite, plain HTTP), then on the **staging server** `turnushjelper-2`
(MySQL, nginx, HTTPS) before promoting to production.

The fixes under test:

| # | Fix | Commit |
|---|-----|--------|
| 1 | No default `admin`/`admin` account | `8d8ac4d` |
| 2 | Session cookie `Secure`/`HttpOnly`/`SameSite` | `bc66b1f` |
| 3 | ProxyFix behind nginx (real client IP + https links) | `d0a6618` |
| 4 | Case-insensitive usernames | `76526d4` |
| 5 | `year_identifier` path-traversal guard | `4cec272` |

> **No database migration is required.** None of these fixes changed `app/models.py`,
> so there is no Alembic step — deploy is just code + config + restart.

---

## Part A — Development machine (SQLite, http://localhost:8080)

In dev, `DB_TYPE=sqlite`, so by design `SESSION_COOKIE_SECURE=0` and
`TRUSTED_PROXY_COUNT=0` (secure cookies and proxy trust are **off** — correct for
plain-HTTP localhost).

### A0. Automated tests (the fastest, broadest check)

```bash
venv/bin/pytest -q                      # expect: 289 passed
# Or just the security-relevant suites:
venv/bin/pytest tests/test_user_service.py::TestInitDefaultAdmin \
                tests/test_user_service.py::TestCaseInsensitiveUsernames \
                tests/test_sa_session_interface.py \
                tests/test_app_factory.py \
                tests/test_forms.py -q
```

Confirm the dev config resolves as expected:

```bash
venv/bin/python -c "from config import AppConfig as c; print('secure=',c.SESSION_COOKIE_SECURE,'proxy=',c.TRUSTED_PROXY_COUNT)"
# expect: secure= False proxy= 0
```

Start the dev server for the manual checks below:

```bash
venv/bin/python run.py            # http://localhost:8080
```

### A1. No default admin (fix #1)

> **The bootstrap messages only fire when there is no `admin` user yet.** If an
> admin already exists, `init_default_admin()` returns early and logs **nothing** —
> that is correct behaviour, not a failure. Your normal `dummy.db` already
> contains an `admin` user, so you will never see these messages against it.
> Use a **throwaway** DB (below), which also avoids creating an admin in your real dev DB.

```bash
# fresh scratch DB — no DEFAULT_ADMIN_PASSWORD set
SQLITE_PATH=./scratch.db venv/bin/alembic upgrade head
SQLITE_PATH=./scratch.db venv/bin/python run.py
```
- **Expect** in `app/logs/app.log` (and on the console): `DEFAULT_ADMIN_PASSWORD not set — skipping admin bootstrap`, and `admin`/`admin` login fails.
- Now weak password → still refused:
  ```bash
  SQLITE_PATH=./scratch.db DEFAULT_ADMIN_PASSWORD=admin venv/bin/python run.py
  ```
  **Expect:** `DEFAULT_ADMIN_PASSWORD is trivially weak — refusing to bootstrap`.
- Strong password → admin created and can log in:
  ```bash
  SQLITE_PATH=./scratch.db DEFAULT_ADMIN_PASSWORD='S3cure-Boot!pw' venv/bin/python run.py
  ```
  Log in at `/login` as `admin` / `S3cure-Boot!pw`.

**Cleanup — order matters:** stop the server (**Ctrl-C**) *first*, and only then
delete the scratch DB:

```bash
# 1. Ctrl-C the running server
rm -f scratch.db          # 2. only after the server has stopped
```

> ⚠️ **Do not `rm scratch.db` while the server is running.** SQLite notices the
> file was unlinked out from under it and downgrades the connection to
> read-only (`SQLITE_READONLY_DBMOVED`). Every write then fails with
> `sqlite3.OperationalError: attempt to write a readonly database` — typically
> first seen on an `INSERT INTO flask_sessions` when you load a page. Reads keep
> working off the open file handle, so the app looks half-alive. The cure is to
> restart the server (the DB was never corrupted).

Quick one-shot check without starting the server at all (prints the warning and exits):

```bash
SQLITE_PATH=./scratch.db venv/bin/python -c "from app import create_app; create_app()"
tail -n 5 app/logs/app.log
rm -f scratch.db          # safe: no server is holding it
```

### A2. Session cookie flags (fix #2)

Inspect the cookie the app sets (any page issues a session cookie via the CSRF token):

```bash
curl -si http://localhost:8080/login | grep -i 'set-cookie'
```
- **Expect (dev/HTTP):** `HttpOnly; SameSite=Lax` **and NO `Secure`** (a Secure
  cookie would never be sent over HTTP and would break local login — that's why
  it's off in dev).
- Browser alternative: DevTools → Application → Cookies → `session` → `HttpOnly` ✓,
  `SameSite` = Lax, `Secure` unchecked.

### A3. ProxyFix (fix #3)

Off in dev by design — covered by `tests/test_app_factory.py`. Nothing to click;
the important verification is on staging (A/B behind nginx).

### A4. Case-insensitive usernames (fix #4)

1. Register (or create) a user with a mixed-case name, e.g. `TestCase`.
2. Log out, then log in as `testcase` (all lowercase) → **succeeds**.
3. Try to register/create another account `TESTCASE` (different email) →
   **rejected** as already taken.

### A5. `year_identifier` path traversal (fix #5)

As an admin, open **Create Turnus Set** and submit `../evil` (or `a/b`) in the
Årsidentifikator field → **rejected** with “Kun bokstaver og tall er tillatt”.
A normal value like `R99` is accepted.

---

## Part B — Staging server `turnushjelper-2` (MySQL, nginx, HTTPS)

Staging runs the production stack: `DB_TYPE=mysql` → `SESSION_COOKIE_SECURE=1`
and `TRUSTED_PROXY_COUNT=1` (defaults), behind nginx at
`https://staging.turnushjelper.no`.

### B0. Deploy

```bash
ssh deploy@turnushjelper-2
cd /home/deploy/turnushjelper

# Optional but recommended: back up the DB first (see BACKUP_SETUP.md)
venv/bin/python scripts/backup/daily_mysql_backup.py

git rev-parse HEAD          # <-- record this SHA; it's your rollback target (B6)
git pull origin main
sudo systemctl restart turnushjelper
sudo systemctl status turnushjelper          # active (running)?
sudo journalctl -u turnushjelper -n 50 --no-pager   # startup errors?
```

Confirm the production config resolves correctly (run from the project root so
`.env` is loaded):

```bash
venv/bin/python -c "from config import AppConfig as c; print('secure=',c.SESSION_COOKIE_SECURE,'proxy=',c.TRUSTED_PROXY_COUNT)"
# expect: secure= True proxy= 1
```

### B1. No default admin (fix #1)

- Try `admin` / `admin` at `https://staging.turnushjelper.no/login` → **must fail**.
- If a legacy weak admin exists from before the fix, check and remediate:
  ```bash
  # in the MySQL client
  SELECT id, username, is_auth, is_stub FROM users WHERE username='admin';
  ```
  If that row exists and its password is still `admin`/`uxtest1234`, change it
  (via the admin UI or a password reset) or delete it. The code fix does **not**
  touch existing rows.
- To bootstrap a fresh admin, follow `docs/guides/ADMIN_BOOTSTRAP.md`.

### B2. Session cookie flags (fix #2)

```bash
curl -si https://staging.turnushjelper.no/login | grep -i 'set-cookie'
```
- **Expect (prod/HTTPS):** `Secure; HttpOnly; SameSite=Lax` — the `Secure` flag
  is now present. Also verify a normal browser login still works end-to-end.

### B3. ProxyFix — real client IP + https links (fix #3)

The single most telling end-to-end check:

1. Trigger a **password-reset email** to yourself (`/forgot-password`).
2. Open the email → the reset link **must start with `https://`** (not `http://`).
   This proves nginx's `X-Forwarded-Proto` is being read via ProxyFix.

Optionally confirm the app sees the real client IP (not `127.0.0.1`) — the rate
limiter now buckets per real IP. You can spot-check in the app/journal logs while
hitting a rate-limited route (`/register`, 10/hour) from your own machine.

> nginx already forwards the needed headers (verified: `proxy_params` sets
> `X-Forwarded-For` and `X-Forwarded-Proto` inside the app `location`). If email
> links ever come out `http://`, re-check those headers.

### B4. Case-insensitive usernames (fix #4)

Log in to an existing account using a different case than it was registered with
(e.g. account `ola` → log in as `Ola`) → **succeeds**. On MySQL this already
worked; the fix makes it consistent and testable — a quick confirmation is enough.

### B5. `year_identifier` path traversal (fix #5)

As an admin on staging, submit `../evil` in **Create Turnus Set** → **rejected**.

### B6. Rollback (if anything misbehaves)

No DB migration was applied, so rollback is clean — reset to the SHA you recorded
in B0 before pulling:

```bash
git reset --hard <SHA-recorded-in-B0>
sudo systemctl restart turnushjelper
```

---

## Promote to production

Once every check on staging passes, the same `git pull` + `systemctl restart`
applies to the production domain. Before/after promoting, complete the
operational follow-ups:

- Production admin password is **not** `uxtest1234` and not a weak value.
- No leftover `admin`/`admin` row in the production DB.
- A production password-reset email link renders as `https://`.
