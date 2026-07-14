# First-Time Admin Bootstrap

This guide covers creating the **first admin account** on a fresh database.

## Overview

For security, the app ships with **no default admin password**. A fresh
deployment therefore does **not** auto-create a guessable `admin`/`admin`
account. You bootstrap the first admin explicitly, using one of the two
options below, then log in at `/login` with the username **`admin`** (the
`DEFAULT_ADMIN_USERNAME` value) and a password you choose.

Both options require the schema to exist first:

```bash
venv/bin/alembic upgrade head
```

> Normal self-registration (`/register`) **cannot** create the first admin:
> it requires a pre-seeded NLF stub and always creates non-admin accounts.

---

## Option A — Built-in bootstrap (recommended)

Provide a strong password in the environment for a single startup. On boot,
`init_default_admin()` creates the admin automatically.

1. Set a strong, unique password in the environment. In `.env`:

   ```
   DEFAULT_ADMIN_USERNAME=admin          # optional; defaults to "admin"
   DEFAULT_ADMIN_PASSWORD=<a-strong-unique-password>
   ```

   Trivial values (`admin`, `password`, `changeme`, …, or a password equal to
   the username) are **refused** — the bootstrap is skipped and a warning is
   logged.

2. Start the app once so the admin is created:

   ```bash
   gunicorn -c gunicorn.conf.py "app:create_app()"   # production
   # or, in dev:
   venv/bin/python run.py
   ```

3. Log in at `/login` with `admin` + your password.

4. **Harden afterwards:**
   - Change the password from **Min Side → Endre passord**.
   - **Blank out** `DEFAULT_ADMIN_PASSWORD` in the environment so the account
     can't be silently recreated if it is ever deleted.

---

## Option B — One-off command (no secret in the environment)

If you'd rather not put a password in `.env` at all, create the admin with a
single command against the configured database (after `alembic upgrade head`):

```bash
venv/bin/python -c "from app.services.user_service import create_user; print(create_user('admin', 'PASTE-A-STRONG-PASSWORD', is_auth=1))"
```

This creates `admin` with `is_auth=1` and `email_verified=1`, so it can log in
immediately. Change the password from **Min Side → Endre passord** after first
login.

---

## Notes

- Login matches on **username**, not email. The account's email column is set
  to `"admin"`, which is never used for this account.
- The created account has `is_auth=1` (admin), `email_verified=1`, `is_stub=0`,
  `not_on_nlf_list=0`, so none of the login guards block it.
- **Existing deployments:** if the site was ever deployed with the old code, an
  `admin`/`admin` account likely already exists in the database — change or
  delete it now. Removing the code default does not touch existing rows.
