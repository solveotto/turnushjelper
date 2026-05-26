#!/usr/bin/env python3
"""
DO warm-standby restore: restores the latest MySQL backup from /backups/ to local MySQL.

Schedule on DO droplet at 2:30 AM UTC (10 min after offsite_backup.py runs on PA):
  30 2 * * * /home/deploy/venv/bin/python /home/deploy/turnushjelper/app/scripts/backup/do_restore.py

Required .env vars: DB_TYPE=mysql, MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
"""

import sys
import os
import subprocess
import glob
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from config import AppConfig

LOG_FILE   = os.path.join(project_root, 'app', 'logs', 'do_restore.log')
BACKUP_DIR = os.path.join(project_root, 'backups')


def log(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry = f"[{timestamp}] {message}"
    print(entry)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(entry + '\n')
    except Exception as e:
        print(f"Warning: could not write to log: {e}")


def find_latest_backup(backup_dir):
    files = sorted(glob.glob(os.path.join(backup_dir, 'backup_*.sql')), reverse=True)
    return files[0] if files else None


def restore(backup_file):
    if AppConfig.DB_TYPE != 'mysql':
        log(f"DB_TYPE={AppConfig.DB_TYPE} — skipping (must be mysql)")
        return False
    cmd = [
        'mysql',
        f'-h{AppConfig.MYSQL_HOST}',
        f'-u{AppConfig.MYSQL_USER}',
        f'-p{AppConfig.MYSQL_PASSWORD}',
        AppConfig.MYSQL_DATABASE,
    ]
    try:
        with open(backup_file, 'r') as f:
            result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            log(f"ERROR: mysql restore failed: {result.stderr.strip()}")
            return False
        return True
    except FileNotFoundError:
        log("ERROR: mysql client not found — install mysql-client")
        return False


def run():
    log('=' * 60)
    log('Starting DO warm-standby restore')

    latest = find_latest_backup(BACKUP_DIR)
    if not latest:
        log(f"ERROR: no backup files found in {BACKUP_DIR}")
        return False

    size_kb = os.path.getsize(latest) / 1024
    log(f"Restoring {os.path.basename(latest)} ({size_kb:.1f} KB)")

    ok = restore(latest)
    log('Restore complete' if ok else 'Restore FAILED')
    log('=' * 60)
    return ok


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
