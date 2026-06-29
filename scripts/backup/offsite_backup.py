#!/usr/bin/env python3
"""
Off-site backup: MySQL dump → Backblaze B2 bucket.

Schedule via cron on Hetzner (10 min after daily_mysql_backup.py):
  10 2 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/offsite_backup.py

Required env vars (add to .env):
  B2_KEY_ID           Application key ID from Backblaze B2 console
  B2_APPLICATION_KEY  Application key from Backblaze B2 console
  B2_BUCKET_NAME      Name of the B2 bucket
  OFFSITE_KEEP_COUNT  How many remote backups to retain (default: 14)
"""

import sys
import os
import subprocess
import tempfile
import json
import urllib.request
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from config import AppConfig

import b2sdk.v2 as b2

LOG_FILE = os.path.join(project_root, 'app', 'logs', 'offsite_backup.log')

B2_KEY_ID = os.getenv('B2_KEY_ID', '')
B2_APPLICATION_KEY = os.getenv('B2_APPLICATION_KEY', '')
B2_BUCKET_NAME = os.getenv('B2_BUCKET_NAME', '')
KEEP_COUNT = int(os.getenv('OFFSITE_KEEP_COUNT', '14'))
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')


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
        text = f":white_check_mark: *Off-site backup succeeded* (turnushjelper)\n{message}"
    else:
        text = f":warning: *Off-site backup failed* (turnushjelper)\n```{message}```"
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
    return api, api.get_bucket_by_name(B2_BUCKET_NAME)


def b2_cleanup(api, bucket):
    file_versions = [
        fv for fv, _ in bucket.ls(latest_only=True)
        if fv is not None
        and fv.file_name.startswith('backup_')
        and fv.file_name.endswith('.sql')
    ]
    # Newest first (lexicographic order works for backup_YYYYMMDD_HHMMSS.sql)
    file_versions.sort(key=lambda fv: fv.file_name, reverse=True)
    for fv in file_versions[KEEP_COUNT:]:
        api.delete_file_version(fv.id_, fv.file_name)
        log(f"Deleted old backup: {fv.file_name}")


def create_dump(path):
    cmd = [
        'mysqldump',
        f'-h{AppConfig.MYSQL_HOST}',
        f'-u{AppConfig.MYSQL_USER}',
        f'-p{AppConfig.MYSQL_PASSWORD}',
        '--no-tablespaces',
        AppConfig.MYSQL_DATABASE,
    ]
    with open(path, 'w') as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"mysqldump failed: {result.stderr.strip()}")


def run():
    log('=' * 60)
    log('Starting off-site backup')

    if AppConfig.DB_TYPE != 'mysql':
        log(f"DB_TYPE={AppConfig.DB_TYPE}, not MySQL — skipping.")
        return False

    for var, val in [
        ('B2_KEY_ID', B2_KEY_ID),
        ('B2_APPLICATION_KEY', B2_APPLICATION_KEY),
        ('B2_BUCKET_NAME', B2_BUCKET_NAME),
    ]:
        if not val:
            log(f"ERROR: {var} is not set in .env")
            return False

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dump_name = f'backup_{timestamp}.sql'
    tmp_dump = os.path.join(tempfile.gettempdir(), dump_name)

    try:
        log("Creating mysqldump...")
        create_dump(tmp_dump)
        size_kb = os.path.getsize(tmp_dump) / 1024
        log(f"Dump size: {size_kb:.1f} KB")

        log(f"Connecting to B2 bucket: {B2_BUCKET_NAME}")
        api, bucket = get_b2_bucket()

        log(f"Uploading {dump_name}...")
        bucket.upload_local_file(local_file=tmp_dump, file_name=dump_name)
        log(f"Uploaded {dump_name}")

        b2_cleanup(api, bucket)
        log(f"Remote cleanup done (keeping last {KEEP_COUNT})")

        log("Off-site backup complete")
        log('=' * 60)
        return True

    except Exception as e:
        log(f"ERROR: {e}")
        log('=' * 60)
        notify_slack(False, str(e))
        return False

    finally:
        if os.path.exists(tmp_dump):
            os.remove(tmp_dump)


if __name__ == '__main__':
    sys.exit(0 if run() else 1)
