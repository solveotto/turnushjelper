#!/usr/bin/env python3
"""
PA DB sync: dump Hetzner MySQL → upload to PythonAnywhere → restore into PA MySQL.

Use this when rolling back from Hetzner to PythonAnywhere as the primary server.

Run manually on Hetzner, or schedule via cron while Hetzner is primary:
  python /home/deploy/turnushjelper/app/scripts/backup/pa_db_sync.py

Required env vars (add to Hetzner .env):
  PA_SSH_HOST         PythonAnywhere SSH host (ssh.pythonanywhere.com)
  PA_SSH_USER         PythonAnywhere username (e.g. solveottooren)
  PA_SSH_KEY          Path to SSH private key on Hetzner (e.g. /home/deploy/.ssh/pa_sync_key)
  PA_SSH_PORT         PythonAnywhere SSH port (default: 3022)
  PA_BACKUP_PATH      Absolute path for dump files on PA (e.g. /home/solveottooren/hetzner_dumps)
  PA_KEEP_COUNT       Number of dump files to retain on PA (default: 7)
"""

import sys
import os
import subprocess
import tempfile
import json
import urllib.request
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)

from config import AppConfig

LOG_FILE = os.path.join(project_root, 'app', 'logs', 'pa_db_sync.log')
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')

PA_SSH_HOST   = os.getenv('PA_SSH_HOST', 'ssh.pythonanywhere.com')
PA_SSH_USER   = os.getenv('PA_SSH_USER', '')
PA_SSH_KEY    = os.getenv('PA_SSH_KEY', os.path.expanduser('~/.ssh/pa_sync_key'))
PA_SSH_PORT   = os.getenv('PA_SSH_PORT', '3022')
PA_BACKUP_PATH = os.getenv('PA_BACKUP_PATH', '')
KEEP_COUNT    = int(os.getenv('PA_KEEP_COUNT', '7'))


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
        text = f":white_check_mark: *PA DB sync succeeded* (turnushjelper)\n{message}"
    else:
        text = f":warning: *PA DB sync failed* (turnushjelper)\n```{message}```"
    payload = json.dumps({"text": text}).encode()
    try:
        req = urllib.request.Request(SLACK_WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"Warning: could not send Slack notification: {e}")


def _ssh_args():
    return ['ssh', '-i', PA_SSH_KEY, '-p', PA_SSH_PORT,
            '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes',
            f"{PA_SSH_USER}@{PA_SSH_HOST}"]


def _ssh_e_arg():
    return f"ssh -i {PA_SSH_KEY} -p {PA_SSH_PORT} -o StrictHostKeyChecking=no -o BatchMode=yes"


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


def rsync_up(local_path, remote_name):
    dest = f"{PA_SSH_USER}@{PA_SSH_HOST}:{PA_BACKUP_PATH}/{remote_name}"
    result = subprocess.run(
        ['rsync', '-e', _ssh_e_arg(), '--timeout=60', local_path, dest],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"rsync to PA failed: {result.stderr.strip()}")


def remote_cleanup():
    cmd = (
        f"ls -1t {PA_BACKUP_PATH}/backup_*.sql 2>/dev/null "
        f"| tail -n +{KEEP_COUNT + 1} | xargs -r rm -f"
    )
    result = subprocess.run(_ssh_args() + [cmd], capture_output=True, text=True)
    if result.returncode != 0:
        log(f"Warning: PA cleanup issue: {result.stderr.strip()}")


def restore_on_pa(dump_name):
    cmd = f"bash ~/restore_from_hetzner.sh {PA_BACKUP_PATH}/{dump_name}"
    result = subprocess.run(_ssh_args() + [cmd], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"PA restore failed: {result.stderr.strip() or result.stdout.strip()}")
    log(f"PA restore output: {result.stdout.strip()}")


def run():
    log('=' * 60)
    log('Starting PA DB sync (Hetzner → PythonAnywhere)')

    if AppConfig.DB_TYPE != 'mysql':
        log(f"DB_TYPE={AppConfig.DB_TYPE}, not MySQL — skipping.")
        return False

    for var, val in [
        ('PA_SSH_USER', PA_SSH_USER),
        ('PA_BACKUP_PATH', PA_BACKUP_PATH),
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

        log(f"Uploading {dump_name} to PythonAnywhere...")
        rsync_up(tmp_dump, dump_name)
        log(f"Uploaded {dump_name}")

        remote_cleanup()
        log(f"Cleanup done (keeping last {KEEP_COUNT})")

        log("Restoring on PythonAnywhere...")
        restore_on_pa(dump_name)
        log("Restore complete")

        notify_slack(True, f"Dump: {dump_name} ({size_kb:.1f} KB)")
        log('PA DB sync complete')
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
