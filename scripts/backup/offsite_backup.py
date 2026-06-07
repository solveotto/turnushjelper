#!/usr/bin/env python3
"""
Off-site backup: MySQL dump + .env → home Ubuntu server via rsync/SSH.

Schedule via cron on Hetzner (10 min after daily_mysql_backup.py):
  10 2 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/offsite_backup.py

Required env vars (add to .env):
  HOME_BACKUP_HOST      IP or hostname of home server
  HOME_BACKUP_USER      SSH username on home server
  HOME_BACKUP_PATH      Absolute path to backup dir on home server
  HOME_BACKUP_SSH_KEY   Path to SSH private key (~/.ssh/backup_key)
  HOME_BACKUP_PORT      SSH port (default: 3125)
  OFFSITE_KEEP_COUNT    How many remote backups to retain (default: 14)
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

LOG_FILE = os.path.join(project_root, 'app', 'logs', 'offsite_backup.log')
ENV_FILE = os.path.join(project_root, '.env')

SSH_HOST = os.getenv('HOME_BACKUP_HOST', '')
SSH_USER = os.getenv('HOME_BACKUP_USER', '')
SSH_REMOTE_PATH = os.getenv('HOME_BACKUP_PATH', '')
SSH_KEY = os.getenv('HOME_BACKUP_SSH_KEY', os.path.expanduser('~/.ssh/backup_key'))
SSH_PORT = os.getenv('HOME_BACKUP_PORT', '3125')
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


def _ssh_e_arg():
    return f"ssh -i {SSH_KEY} -p {SSH_PORT} -o StrictHostKeyChecking=no -o BatchMode=yes"


def rsync_up(local_path, remote_name):
    dest = f"{SSH_USER}@{SSH_HOST}:{SSH_REMOTE_PATH}/{remote_name}"
    result = subprocess.run(
        ['rsync', '-e', _ssh_e_arg(), '--timeout=60', local_path, dest],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"rsync failed: {result.stderr.strip()}")


def run_ssh(remote_cmd):
    return subprocess.run(
        ['ssh', '-i', SSH_KEY, '-p', SSH_PORT,
         '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes',
         f"{SSH_USER}@{SSH_HOST}", remote_cmd],
        capture_output=True, text=True
    )


def remote_cleanup():
    # Delete oldest sql and env files beyond KEEP_COUNT
    cmd = (
        f"ls -1t {SSH_REMOTE_PATH}/backup_*.sql 2>/dev/null | tail -n +{KEEP_COUNT + 1} | xargs -r rm -f; "
        f"ls -1t {SSH_REMOTE_PATH}/env_* 2>/dev/null | tail -n +{KEEP_COUNT + 1} | xargs -r rm -f"
    )
    result = run_ssh(cmd)
    if result.returncode != 0:
        log(f"Warning: remote cleanup issue: {result.stderr.strip()}")


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
        ('HOME_BACKUP_HOST', SSH_HOST),
        ('HOME_BACKUP_USER', SSH_USER),
        ('HOME_BACKUP_PATH', SSH_REMOTE_PATH),
    ]:
        if not val:
            log(f"ERROR: {var} is not set in .env")
            return False

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dump_name = f'backup_{timestamp}.sql'
    env_name = f'env_{timestamp}'
    tmp_dump = os.path.join(tempfile.gettempdir(), dump_name)

    try:
        log(f"Creating mysqldump...")
        create_dump(tmp_dump)
        size_kb = os.path.getsize(tmp_dump) / 1024
        log(f"Dump size: {size_kb:.1f} KB")

        log(f"Uploading {dump_name}...")
        rsync_up(tmp_dump, dump_name)
        log(f"Uploaded {dump_name}")

        if not os.path.exists(ENV_FILE):
            log(f"Warning: .env not found at {ENV_FILE} — skipping env backup")
        else:
            log(f"Uploading .env as {env_name}...")
            rsync_up(ENV_FILE, env_name)
            log(f"Uploaded {env_name}")

        remote_cleanup()
        log(f"Remote cleanup done (keeping last {KEEP_COUNT} of each)")

        log("Off-site backup complete")
        notify_slack(True, f"Dump: {dump_name} ({size_kb:.1f} KB)")
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
