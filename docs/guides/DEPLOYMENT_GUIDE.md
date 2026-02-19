# PythonAnywhere Deployment Guide — Phase 5 (.env Migration)

This guide covers deploying the config.ini → .env migration to PythonAnywhere.

## What Changed

`config.py` no longer reads `config.ini`. All configuration now comes from
environment variables, loaded from a `.env` file via `python-dotenv`.

---

## Step 1: Pull the Latest Code

Open a **Bash console** on PythonAnywhere:

```bash
cd ~/shift_rotation_organizer
git pull origin main
```

---

## Step 2: Install python-dotenv

Activate your virtualenv first, then install:

```bash
workon YOUR_VENV_NAME
pip install python-dotenv
```

Replace `YOUR_VENV_NAME` with your actual virtualenv name.

---

## Step 3: Create the `.env` File

Create the `.env` file with your **production** values:

```bash
nano ~/shift_rotation_organizer/.env
```

Paste the following, replacing placeholder values with your actual production credentials:

```env
# Flask
SECRET_KEY=your-production-secret-key

# Database
DB_TYPE=mysql

# MySQL (production)
MYSQL_HOST=solveottooren.mysql.pythonanywhere-services.com
MYSQL_USER=solveottooren
MYSQL_PASSWORD=your-mysql-password
MYSQL_DATABASE=solveottooren$turnuser

# Email — Mailgun
MAILGUN_API_KEY=your-mailgun-api-key
MAILGUN_DOMAIN=mail.turnushjelper.no
MAILGUN_REGION=eu
SENDER_EMAIL=noreply@mail.turnushjelper.no
SENDER_NAME=Turnushjelper

# Verification
TOKEN_EXPIRY_HOURS=48
UNVERIFIED_CLEANUP_DAYS=14
MAX_VERIFICATION_EMAILS_PER_DAY=3
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

> **Tip:** You can copy the values from your existing `config.ini` before deleting it.
> Run `cat ~/shift_rotation_organizer/config.ini` to view current values.

---

## Step 4: Update the WSGI File

Go to the **Web** tab on PythonAnywhere, click the **WSGI configuration file** link,
and add `dotenv` loading at the top (before the existing app import):

```python
import os
from dotenv import load_dotenv

project_folder = os.path.expanduser('~/shift_rotation_organizer')
load_dotenv(os.path.join(project_folder, '.env'))

# ... rest of your existing WSGI code below ...
```

This ensures environment variables are loaded before the Flask app initializes.

---

## Step 5: Scheduled Tasks (Cron Jobs) — No Changes Needed

All CLI scripts (e.g., `daily_mysql_backup.py`, `cleanup_unverified_users.py`)
do `from config import AppConfig`, which triggers `load_dotenv()` automatically.
The `.env` path is resolved from `config.py`'s location using an absolute path,
so it works regardless of the cron job's working directory.

**Your existing PythonAnywhere scheduled tasks will keep working as-is.**

---

## Step 6: Verify the Deployment

In a **Bash console**, run these checks:

```bash
cd ~/shift_rotation_organizer
workon YOUR_VENV_NAME

# 1. Check config loads
python -c "from config import AppConfig; print('SECRET_KEY:', AppConfig.SECRET_KEY[:8] + '...')"

# 2. Check database URI (should show mysql)
python -c "from config import get_database_uri; print(get_database_uri()[:50])"

# 3. Check app starts
python -c "from app import create_app; app = create_app(); print('OK')"

# 4. Check no old references remain
grep -r "AppConfig.CONFIG" app/
```

All checks should pass. The last command should return no results.

---

## Step 7: Reload the Web App

Go to the **Web** tab and click **Reload**.

Visit your site and verify it works normally.

---

## Step 8: Clean Up (Optional)

Once everything is confirmed working, you can remove the old `config.ini`:

```bash
rm ~/shift_rotation_organizer/config.ini
```

This is optional — the new code ignores `config.ini` entirely, so leaving it
in place does no harm.

---

## Troubleshooting

### App fails with "SECRET_KEY must be set"
The `.env` file is missing or not being loaded. Check:
- File exists: `ls -la ~/shift_rotation_organizer/.env`
- File has content: `head -5 ~/shift_rotation_organizer/.env`
- WSGI file has `load_dotenv()` call

### Scheduled task can't connect to database
The script may not be finding the `.env` file. Verify the script imports
`from config import AppConfig` — this triggers `load_dotenv()` automatically.
If the working directory is different, `load_dotenv()` uses an absolute path
based on `config.py`'s location, so it should still work.

### Email not sending
Check that `MAILGUN_API_KEY` is set correctly in `.env`:
```bash
python -c "from config import AppConfig; print(AppConfig.MAILGUN_API_KEY[:8])"
```
