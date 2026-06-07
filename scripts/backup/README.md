# Backup Scripts

Scripts for database backups on the Hetzner server.

## Files

| Script | Purpose |
|---|---|
| `daily_mysql_backup.py` | Nightly local SQL dump (run via cron) |
| `offsite_backup.py` | Push dump + .env to home server via rsync/SSH |
| `restore_backup.py` | Interactive restore from a local backup file |
| `restore_from_offsite.py` | Download and restore from home server |
| `test_backup_system.py` | Verify backup config before scheduling |

## Cron setup on Hetzner

```crontab
# Daily local backup at 02:00
0 2 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/daily_mysql_backup.py

# Off-site backup at 02:10 (after local backup completes)
10 2 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/offsite_backup.py
```

Add to crontab with `crontab -e` as the `deploy` user.

## Required .env vars

### Local backup
No extra vars needed — uses the standard `MYSQL_*` vars.

### Off-site backup (home server)
```
HOME_BACKUP_HOST=<ip or hostname>
HOME_BACKUP_USER=<ssh user>
HOME_BACKUP_PATH=<absolute path on home server>
HOME_BACKUP_SSH_KEY=~/.ssh/backup_key
HOME_BACKUP_PORT=3125
OFFSITE_KEEP_COUNT=14
```

## Testing

```bash
python scripts/backup/test_backup_system.py
```

## Manual backup

```bash
python scripts/backup/daily_mysql_backup.py
```

Backups are stored in `backups/backup_YYYYMMDD_HHMMSS.sql`. Last 7 days are kept.

## Restoring locally

```bash
python scripts/backup/restore_backup.py
```

## Restoring from home server

```bash
python scripts/backup/restore_from_offsite.py
```

## Logs

- `app/logs/backup.log` — local backup
- `app/logs/offsite_backup.log` — off-site backup
