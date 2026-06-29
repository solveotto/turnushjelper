#!/usr/bin/env python3
"""
Restore latest backup from Backblaze B2.

Can run unattended (cron) or interactively. Always picks the newest backup.

Usage:
  # Interactive (default) — choose a backup and confirm before restoring
  python scripts/backup/restore_from_offsite.py

  # Unattended — restores latest backup without prompts
  python scripts/backup/restore_from_offsite.py --yes

Schedule via cron on staging server:
  0 3 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/restore_from_offsite.py --yes

Requires B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME in .env.
"""

import sys
import os
import subprocess
import json
import urllib.request
from datetime import datetime
from dotenv import load_dotenv

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

load_dotenv(os.path.join(project_root, '.env'))

import b2sdk.v2 as b2

B2_KEY_ID = os.getenv('B2_KEY_ID', '')
B2_APPLICATION_KEY = os.getenv('B2_APPLICATION_KEY', '')
B2_BUCKET_NAME = os.getenv('B2_BUCKET_NAME', '')
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')

LOG_FILE = os.path.join(project_root, 'app', 'logs', 'offsite_restore.log')

UNATTENDED = '--yes' in sys.argv


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


def notify_slack(success, message):
    if not SLACK_WEBHOOK_URL:
        return
    if success:
        text = f":white_check_mark: *Offsite restore succeeded* (turnushjelper)\n{message}"
    else:
        text = f":warning: *Offsite restore failed* (turnushjelper)\n```{message}```"
    payload = json.dumps({"text": text}).encode()
    try:
        req = urllib.request.Request(SLACK_WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"Warning: could not send Slack notification: {e}")


def get_b2_bucket():
    info = b2.InMemoryAccountInfo()
    api = b2.B2Api(info)
    api.authorize_account("production", B2_KEY_ID, B2_APPLICATION_KEY)
    return api.get_bucket_by_name(B2_BUCKET_NAME)


def list_b2_dumps(bucket):
    file_versions = [
        fv for fv, _ in bucket.ls(latest_only=True)
        if fv is not None
        and fv.file_name.startswith('backup_')
        and fv.file_name.endswith('.sql')
    ]
    file_versions.sort(key=lambda fv: fv.file_name, reverse=True)
    return file_versions


def download_from_b2(bucket, file_name, local_path):
    downloaded = bucket.download_file_by_name(file_name)
    downloaded.save_to(local_path)


def restore_database(dump_file):
    db_type = os.getenv('DB_TYPE', '').lower()

    if db_type != 'mysql':
        log(f"ERROR: DB_TYPE={db_type!r} — only MySQL is supported")
        return False

    mysql_host = os.getenv('MYSQL_HOST', '')
    mysql_user = os.getenv('MYSQL_USER', '')
    mysql_password = os.getenv('MYSQL_PASSWORD', '')
    mysql_database = os.getenv('MYSQL_DATABASE', '')

    if not all([mysql_host, mysql_user, mysql_password, mysql_database]):
        log("ERROR: MySQL credentials not found in .env")
        return False

    log(f"Restoring to MySQL: {mysql_database} @ {mysql_host}")
    result = subprocess.run(
        f"mysql -h {mysql_host} -u {mysql_user} -p{mysql_password} {mysql_database} < {dump_file}",
        shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        log(f"ERROR: Restore failed: {result.stderr.strip()}")
        return False
    log("Database restored successfully")
    return True


def run_migrations():
    log("Running migrations...")
    venv_alembic = os.path.join(project_root, 'venv', 'bin', 'alembic')
    alembic_cmd = venv_alembic if os.path.exists(venv_alembic) else 'alembic'
    result = subprocess.run(
        [alembic_cmd, 'upgrade', 'head'],
        cwd=project_root, capture_output=True, text=True
    )
    if result.returncode != 0:
        log(f"WARNING: Migrations had issues: {result.stderr.strip()}")
        return False
    log("Migrations completed")
    return True


def run():
    log('=' * 60)
    log('Starting offsite restore')

    for var, val in [
        ('B2_KEY_ID', B2_KEY_ID),
        ('B2_APPLICATION_KEY', B2_APPLICATION_KEY),
        ('B2_BUCKET_NAME', B2_BUCKET_NAME),
    ]:
        if not val:
            log(f"ERROR: {var} is not set in .env")
            return False

    log(f"Connecting to B2 bucket: {B2_BUCKET_NAME}")
    try:
        bucket = get_b2_bucket()
    except Exception as e:
        log(f"ERROR: Could not connect to B2: {e}")
        return False

    dumps = list_b2_dumps(bucket)
    if not dumps:
        log("ERROR: No backups found in B2 bucket")
        return False

    if not UNATTENDED:
        print(f"\nFound {len(dumps)} backup(s):\n")
        for i, fv in enumerate(dumps):
            try:
                parts = fv.file_name.replace('.sql', '').split('_')
                dt = datetime.strptime(f"{parts[1]}_{parts[2]}", '%Y%m%d_%H%M%S')
                label = dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                label = fv.file_name
            size_kb = fv.size / 1024 if fv.size else 0
            print(f"  [{i + 1}] {label}  ({fv.file_name}, {size_kb:.1f} KB)")

        print()
        choice = input("Select backup number (or q to quit): ").strip()
        if choice.lower() == 'q':
            sys.exit(0)
        try:
            idx = int(choice) - 1
            assert 0 <= idx < len(dumps)
        except Exception:
            print("Invalid selection.")
            sys.exit(1)
        selected = dumps[idx]

        print(f"\nSelected: {selected.file_name}")
        confirm = input("Type RESTORE to confirm: ").strip()
        if confirm != 'RESTORE':
            print("Aborted.")
            sys.exit(0)
    else:
        selected = dumps[0]
        log(f"Latest backup: {selected.file_name}")

    local_sql = os.path.join(project_root, selected.file_name)

    try:
        log(f"Downloading {selected.file_name} from B2...")
        download_from_b2(bucket, selected.file_name, local_sql)
        size_kb = os.path.getsize(local_sql) / 1024
        log(f"Downloaded {size_kb:.1f} KB")

        if not restore_database(local_sql):
            return False

        run_migrations()

        log("Offsite restore complete")
        log('=' * 60)
        return True

    except Exception as e:
        log(f"ERROR: {e}")
        notify_slack(False, str(e))
        log('=' * 60)
        return False

    finally:
        if os.path.exists(local_sql):
            os.remove(local_sql)


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
