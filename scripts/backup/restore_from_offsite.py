#!/usr/bin/env python3
"""
Interactive restore: download backups from home server back to this machine.

Run manually after a server wipe or to inspect available backups:
  python scripts/backup/restore_from_offsite.py

Requires the same HOME_BACKUP_* env vars as offsite_backup.py.
"""

import sys
import os
import subprocess
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

SSH_HOST = os.getenv('HOME_BACKUP_HOST', '')
SSH_USER = os.getenv('HOME_BACKUP_USER', '')
SSH_REMOTE_PATH = os.getenv('HOME_BACKUP_PATH', '')
SSH_KEY = os.getenv('HOME_BACKUP_SSH_KEY', os.path.expanduser('~/.ssh/backup_key'))
SSH_PORT = os.getenv('HOME_BACKUP_PORT', '3125')


def _ssh_e_arg():
    return f"ssh -i {SSH_KEY} -p {SSH_PORT} -o StrictHostKeyChecking=no -o BatchMode=yes"


def run_ssh(remote_cmd):
    return subprocess.run(
        ['ssh', '-i', SSH_KEY, '-p', SSH_PORT,
         '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes',
         f"{SSH_USER}@{SSH_HOST}", remote_cmd],
        capture_output=True, text=True
    )


def rsync_down(remote_name, local_path):
    src = f"{SSH_USER}@{SSH_HOST}:{SSH_REMOTE_PATH}/{remote_name}"
    result = subprocess.run(
        ['rsync', '-e', _ssh_e_arg(), '--timeout=60', src, local_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"rsync failed: {result.stderr.strip()}")


def list_remote_dumps():
    result = run_ssh(f"ls -1t {SSH_REMOTE_PATH}/backup_*.sql 2>/dev/null")
    if result.returncode != 0 or not result.stdout.strip():
        return []
    return [os.path.basename(f) for f in result.stdout.strip().splitlines()]


def main():
    for var, val in [
        ('HOME_BACKUP_HOST', SSH_HOST),
        ('HOME_BACKUP_USER', SSH_USER),
        ('HOME_BACKUP_PATH', SSH_REMOTE_PATH),
    ]:
        if not val:
            print(f"ERROR: {var} is not set. Add it to your .env file.")
            sys.exit(1)

    print("Connecting to home server and listing backups...")
    dumps = list_remote_dumps()
    if not dumps:
        print("No backups found on remote server.")
        sys.exit(1)

    print(f"\nFound {len(dumps)} backup(s):\n")
    for i, name in enumerate(dumps):
        try:
            parts = name.replace('.sql', '').split('_')
            dt = datetime.strptime(f"{parts[1]}_{parts[2]}", '%Y%m%d_%H%M%S')
            label = dt.strftime('%Y-%m-%d %H:%M')
        except Exception:
            label = name
        print(f"  [{i + 1}] {label}  ({name})")

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

    dump_name = dumps[idx]

    print(f"\nSelected:  {dump_name}")
    print()
    confirm = input("Type RESTORE to confirm download: ").strip()
    if confirm != 'RESTORE':
        print("Aborted.")
        sys.exit(0)

    local_sql = os.path.join(project_root, dump_name)

    print(f"\nDownloading {dump_name}...")
    rsync_down(dump_name, local_sql)
    print(f"  Saved: {local_sql}")

    print("\n--- Recovery steps ---")
    print(f"  1. Restore DB:   mysql -u USER -p DATABASE < {dump_name}")
    print(f"  2. Migrations:   alembic upgrade head")


if __name__ == '__main__':
    main()
