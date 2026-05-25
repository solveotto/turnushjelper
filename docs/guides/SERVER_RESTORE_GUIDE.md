# Full Server Restore Guide

This guide walks through restoring turnushjelper from scratch — for example after a PythonAnywhere account wipe, accidental data loss, or migration to a new host. It also explains how to simulate a restore locally for testing.

---

## What "full restore" means

A complete restore has three independent parts:

| Part | Source | Script / tool |
|---|---|---|
| **Code** | Git repository | `git clone` |
| **Database** | SQL dump (local or off-site) | `restore_from_offsite.py` / `restore_backup.py` |
| **Config** | `.env` backup (off-site) | rsync / manual |

Sessions (`app/utils/sessions/`) are ephemeral — they do not need to be restored.

---

## Before You Start

Gather or verify you have access to:

- [ ] Git repo URL
- [ ] SSH key for the off-site backup server (or a manual `.env` copy)
- [ ] PythonAnywhere credentials (or target host access)
- [ ] Virtualenv Python version (3.12)

---

## Phase 1: Restore the Code

```bash
# On PythonAnywhere Bash console (or your target host)
git clone https://github.com/YOUR_USER/turnushjelper.git ~/mysite
cd ~/mysite
```

---

## Phase 2: Set Up the Python Environment

```bash
mkvirtualenv --python=python3.12 turnushjelper_venv
workon turnushjelper_venv
pip install -r requirements.txt
```

Verify the install:

```bash
python -c "from app import create_app; print('OK')"
```

---

## Phase 3: Restore the `.env` File

### Option A — Automated (from off-site backup server)

```bash
python app/scripts/backup/restore_from_offsite.py
```

The script lists all remote backups by date. Select the one you want, type `RESTORE`, and it will:

1. Download the SQL dump to the project root
2. Download the matching `.env` backup (saved as `env_YYYYMMDD_HHMMSS.restored`)

Then activate the `.env`:

```bash
cp env_YYYYMMDD_HHMMSS.restored .env
```

### Option B — Manual

Copy `.env.example` to `.env` and fill in all production values:

```bash
cp .env.example .env
nano .env
```

Required fields for production:

```env
SECRET_KEY=<production secret>
DB_TYPE=mysql
MYSQL_HOST=solveottooren.mysql.pythonanywhere-services.com
MYSQL_USER=solveottooren
MYSQL_PASSWORD=<password>
MYSQL_DATABASE=solveottooren$turnuser
MAILGUN_API_KEY=<key>
MAILGUN_DOMAIN=mail.turnushjelper.no
MAILGUN_REGION=eu
SENDER_EMAIL=noreply@mail.turnushjelper.no
SENDER_NAME=Turnushjelper
TOKEN_EXPIRY_HOURS=48
UNVERIFIED_CLEANUP_DAYS=14
MAX_VERIFICATION_EMAILS_PER_DAY=3
```

---

## Phase 4: Restore the Database

### Option A — From off-site backup (continuation of Phase 3A)

The script printed the local SQL file path. Run:

```bash
mysql -h solveottooren.mysql.pythonanywhere-services.com \
      -u solveottooren \
      -p \
      'solveottooren$turnuser' < backup_YYYYMMDD_HHMMSS.sql
```

Then ensure migrations are stamped at the current head:

```bash
alembic current   # should show the latest revision
# If it shows nothing, stamp it:
alembic stamp head
```

### Option B — From a local backup on the server

```bash
python app/scripts/backup/restore_backup.py
```

Pick the backup, type `RESTORE`, done.

### Option C — Fresh database (no backup)

If there is no usable backup:

```bash
alembic upgrade head
```

This creates all tables from scratch. You will need to re-import turnus data and re-create admin users manually.

---

## Phase 5: Configure PythonAnywhere

### 5.1 WSGI file

Go to **Web tab → WSGI configuration file** and ensure it starts with:

```python
import os
from dotenv import load_dotenv

project_folder = os.path.expanduser('~/mysite')
load_dotenv(os.path.join(project_folder, '.env'))

# ... rest of WSGI boilerplate ...
```

### 5.2 Virtualenv

In the **Web tab**, set the virtualenv path:

```
/home/solveottooren/.virtualenvs/turnushjelper_venv
```

### 5.3 Scheduled tasks

Re-create these in the **Tasks tab**:

| Time (UTC) | Command |
|---|---|
| 02:00 | `/home/solveottooren/mysite/venv/bin/python /home/solveottooren/mysite/app/scripts/backup/daily_mysql_backup.py` |
| 02:10 | `/home/solveottooren/mysite/venv/bin/python /home/solveottooren/mysite/app/scripts/backup/offsite_backup.py` |
| Daily | Cleanup unverified users (check existing task config) |

---

## Phase 6: Verify

Run these checks before reloading the web app:

```bash
workon turnushjelper_venv
cd ~/mysite

# 1. Config loads correctly
python -c "from config import AppConfig; print('DB:', AppConfig.DB_TYPE); print('KEY:', AppConfig.SECRET_KEY[:8] + '...')"

# 2. Database URI is correct
python -c "from config import get_database_uri; print(get_database_uri()[:60])"

# 3. App factory works
python -c "from app import create_app; app = create_app(); print('App OK')"

# 4. DB connection and schema are intact
python app/scripts/check_db.py

# 5. Alembic is at head
alembic current
```

Then reload the web app and manually verify:

- [ ] Login works
- [ ] Turnusliste loads with data
- [ ] Favorites can be toggled
- [ ] Admin panel is accessible at `/admin`
- [ ] A backup runs: `python app/scripts/backup/daily_mysql_backup.py`

---

## Simulating a Full Restore Locally

Use SQLite to test the entire restore flow without touching production.

### 1. Create a dump from your local SQLite DB

```bash
# Export current SQLite data as SQL
sqlite3 dummy.db .dump > local_backup.sql
```

### 2. Wipe and restore to a fresh SQLite DB

```bash
rm dummy.db
# Restore via Alembic (schema) then re-import data:
DB_TYPE=sqlite SQLITE_PATH=./dummy.db alembic upgrade head
# OR restore from a previous SQL dump (sqlite3 only):
sqlite3 dummy.db < local_backup.sql
```

### 3. Simulate a missing `.env`

```bash
mv .env .env.bak
# Confirm app fails cleanly:
python -c "from config import AppConfig" 2>&1
# Restore:
mv .env.bak .env
```

### 4. Simulate a missing database

```bash
mv dummy.db dummy.db.bak
DB_TYPE=sqlite SQLITE_PATH=./dummy.db alembic upgrade head
# Verify tables exist:
python -c "from app import create_app; app = create_app(); print('OK')"
# Then restore real data:
mv dummy.db.bak dummy.db
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `SECRET_KEY must be set` | `.env` not found or WSGI `load_dotenv()` missing |
| `Access denied` on MySQL | Password in `.env`; database name uses `$` not `$$` |
| `alembic current` returns nothing | DB has tables but no `alembic_version` row — run `alembic stamp head` |
| App starts but shows no turnus data | `df_manager` loads from DB on first request; check turnus_sets table has rows |
| Favorites not working | Check `favorites` table exists and foreign keys are intact |
| Off-site restore: `Permission denied` | SSH key path wrong in `.env`, or key not authorised on home server |

---

## Notes on the Live Server

- **Project path**: `/home/solveottooren/mysite/` (not `shift_rotation_organizer`)
- **Quota**: 1.0 GB total; currently ~60% full (617 MB used) — keep an eye on backup accumulation in `backups/`
- **`config.ini`**: still present on the server alongside `.env`. The app ignores it (config now reads only from `.env`), but it can serve as a manual credential reference during a restore. Do not delete it until you're confident all credentials are safely backed up elsewhere.
- **Virtualenv**: not inside `mysite/` — it lives in `/home/solveottooren/.virtualenvs/`. Use `workon <venv_name>` to activate.

---

## Related Guides

- [DATABASE_MIGRATIONS.md](DATABASE_MIGRATIONS.md) — Alembic reference
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) — First-time PythonAnywhere setup
- `app/scripts/backup/README.md` — Backup system details
