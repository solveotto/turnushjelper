# Backup Scripts

Scripts for database backups on the Hetzner server.

## Files

| Script | Purpose |
|---|---|
| `daily_mysql_backup.py` | Nightly local SQL dump (run via cron) |
| `offsite_backup.py` | Push dump to Backblaze B2 bucket |
| `restore_backup.py` | Interactive restore from a local backup file |
| `restore_from_offsite.py` | Download and restore from Backblaze B2 |
| `test_backup_system.py` | Verify backup config before scheduling |

## Cron setup on Hetzner

**Active server** (writes backups):
```crontab
# Daily local backup at 02:00
0 2 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/daily_mysql_backup.py

# Off-site backup at 02:10 (after local backup completes)
10 2 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/offsite_backup.py
```

**Staging/backup server** (reads backups):
```crontab
# Pull and restore latest backup at 03:00
0 3 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/restore_from_offsite.py --yes
```

Add to crontab with `crontab -e` as the `deploy` user.

## Required .env vars

### Local backup
No extra vars needed — uses the standard `MYSQL_*` vars.

### Off-site backup (Backblaze B2)
```
B2_KEY_ID=<application key ID from B2 console>
B2_APPLICATION_KEY=<application key from B2 console>
B2_BUCKET_NAME=<bucket name>
OFFSITE_KEEP_COUNT=14   # optional, default 14
SLACK_WEBHOOK_URL=      # optional
```

Create a B2 application key with read/write/delete access to the bucket. The active server writes backups; any other server can restore from the same bucket.

## Testing

```bash
python scripts/backup/test_backup_system.py
```

## Manual backup

```bash
python scripts/backup/daily_mysql_backup.py
```

Backups are stored in `backups/backup_YYYYMMDD_HHMMSS.sql`. Last 7 days are kept locally.

## Restoring locally

```bash
python scripts/backup/restore_backup.py
```

## Restoring from B2

```bash
# Interactive (default) — choose a backup and confirm before restoring
python scripts/backup/restore_from_offsite.py

# Unattended (cron) — always picks the latest backup without prompts
python scripts/backup/restore_from_offsite.py --yes
```

## Logs

- `app/logs/backup.log` — local backup
- `app/logs/offsite_backup.log` — off-site backup
