# Backup Setup Guide

This guide covers setting up automated backups on the **primary server** and automated restore sync on the **staging/backup server**. Both servers use a shared Backblaze B2 bucket as the transfer point.

## Overview

```
Primary server
  └── daily_mysql_backup.py   → ../backups/  (local, 7-day retention)
  └── offsite_backup.py       → B2 bucket    (14-backup retention)

Staging server
  └── restore_from_offsite.py ← B2 bucket    (pulls latest, restores DB)
```

---

## 1. Backblaze B2 — Create Bucket and Key

1. Log in to [backblaze.com](https://www.backblaze.com) and go to **B2 Cloud Storage**.
2. Create a bucket (e.g. `turnushjelper-backups`). Set **Files in Bucket** to **Private**.
3. Go to **App Keys** → **Add a New Application Key**.
   - Name: `turnushjelper-backup`
   - Allow access to: the bucket you just created
   - Type of access: **Read and Write**
   - Check **Allow Delete Files**
4. Copy the **keyID** and **applicationKey** — the key is only shown once.

---

## 2. Primary Server Setup

### 2.1 Add .env variables

Add the following to `.env` on the primary server:

```
DB_TYPE=mysql
MYSQL_HOST=...
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DATABASE=...

B2_KEY_ID=<keyID from step 1>
B2_APPLICATION_KEY=<applicationKey from step 1>
B2_BUCKET_NAME=turnushjelper-backups
OFFSITE_KEEP_COUNT=14
```

### 2.2 Install dependencies

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 2.3 Verify the setup

```bash
python scripts/backup/test_backup_system.py
```

All 7 tests should pass. When prompted, answer `yes` to test the B2 connection and optionally run a test backup.

### 2.4 Set up cron

Open the crontab for the `deploy` user:

```bash
crontab -e
```

Add these two lines:

```crontab
# Daily local backup at 02:00
0 2 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/daily_mysql_backup.py

# Off-site backup to B2 at 02:10 (after local backup)
10 2 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/offsite_backup.py
```

### 2.5 Verify cron is working

The next morning, check the logs:

```bash
tail -50 app/logs/backup.log
tail -50 app/logs/offsite_backup.log
```

You should also see a new file appear in your B2 bucket.

---

## 3. Staging/Backup Server Setup

The staging server pulls the latest backup from B2 and restores it to its local database once a day.

### 3.1 Add .env variables

Add the same B2 credentials to `.env` on the staging server. The MySQL credentials should point to the staging server's own database:

```
DB_TYPE=mysql
MYSQL_HOST=...
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DATABASE=...

B2_KEY_ID=<same keyID>
B2_APPLICATION_KEY=<same applicationKey>
B2_BUCKET_NAME=turnushjelper-backups
```

### 3.2 Install dependencies

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 3.3 Test a manual restore

Run the interactive restore to verify everything works before scheduling:

```bash
python scripts/backup/restore_from_offsite.py
```

This will list available backups in the B2 bucket, let you choose one, and ask for confirmation before restoring.

### 3.4 Set up cron

Open the crontab for the `deploy` user:

```bash
crontab -e
```

Add this line (scheduled after the primary server finishes uploading):

```crontab
# Pull and restore latest backup from B2 at 03:00
0 3 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/restore_from_offsite.py --yes
```

The `--yes` flag runs without prompts. Without it, the script runs interactively.

### 3.5 Verify cron is working

Check the restore log the next morning:

```bash
tail -50 app/logs/offsite_restore.log
```

---

## 4. Log Files

| Log | Location | Written by |
|---|---|---|
| Local backup | `app/logs/backup.log` | `daily_mysql_backup.py` |
| B2 upload | `app/logs/offsite_backup.log` | `offsite_backup.py` |
| B2 restore | `app/logs/offsite_restore.log` | `restore_from_offsite.py` |

---

## 5. Manual Operations

### Run a backup immediately (primary)

```bash
python scripts/backup/offsite_backup.py
```

### Restore a specific backup interactively (any server)

```bash
python scripts/backup/restore_from_offsite.py
```

### Restore from a local backup file

```bash
python scripts/backup/restore_backup.py
```

### List local backup files

```bash
ls -lh ../backups/
```
