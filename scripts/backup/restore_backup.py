#!/usr/bin/env python3
"""
Restore MySQL Database from Backup
Interactive script to restore database from backup files

Usage:
    python scripts/backup/restore_backup.py
"""

import sys
import os
import subprocess
import glob
from datetime import datetime

# Add project root to path (go up 4 levels: backup -> scripts -> app -> project_root)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from config import AppConfig

BACKUP_DIR = os.path.join(project_root, 'backups')

def list_backups():
    """List all available backup files"""
    backup_pattern = os.path.join(BACKUP_DIR, 'backup_*.sql')
    backups = sorted(glob.glob(backup_pattern), reverse=True)
    
    if not backups:
        print("\n✗ No backup files found!")
        print(f"Backup directory: {BACKUP_DIR}")
        return None
    
    print("\n" + "=" * 70)
    print("Available Backups")
    print("=" * 70)
    
    for i, backup in enumerate(backups, 1):
        basename = os.path.basename(backup)
        size = os.path.getsize(backup)
        
        # Format size
        if size >= 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.2f} MB"
        else:
            size_str = f"{size / 1024:.1f} KB"
        
        # Extract date from filename
        try:
            date_part = basename.split('_')[1]  # YYYYMMDD
            time_part = basename.split('_')[2].replace('.sql', '')  # HHMMSS
            backup_date = datetime.strptime(f"{date_part}_{time_part}", "%Y%m%d_%H%M%S")
            date_str = backup_date.strftime("%Y-%m-%d %H:%M:%S")
        except (IndexError, ValueError):
            date_str = "Unknown date"
        
        print(f"{i:2d}. {basename:30s} | {date_str} | {size_str:>10s}")
    
    print("=" * 70)
    return backups

def restore_backup(backup_file):
    """Restore database from backup file"""
    
    db_type = AppConfig.DB_TYPE

    if db_type != 'mysql':
        print(f"\n✗ Database type is {db_type}, not MySQL.")
        print("This restore script is for MySQL databases only.")
        return False

    host = AppConfig.MYSQL_HOST
    user = AppConfig.MYSQL_USER
    password = AppConfig.MYSQL_PASSWORD
    database = AppConfig.MYSQL_DATABASE
    
    basename = os.path.basename(backup_file)
    
    print("\n" + "=" * 70)
    print("⚠  WARNING: DATABASE RESTORE")
    print("=" * 70)
    print(f"\nBackup file: {basename}")
    print(f"Target database: {database}")
    print(f"\nThis will OVERWRITE the current database!")
    print("All current data will be replaced with the backup.")
    print("\nMake sure you have a backup of the current state if needed.")
    print("\n" + "=" * 70)
    
    response = input("\nType 'RESTORE' (in capitals) to confirm: ")
    
    if response != 'RESTORE':
        print("\n✗ Restore cancelled.")
        return False
    
    print("\nRestoring database...")
    print(f"Reading from: {backup_file}")
    
    # Build mysql restore command
    cmd = [
        'mysql',
        f'-h{host}',
        f'-u{user}',
        f'-p{password}',
        database
    ]
    
    try:
        with open(backup_file, 'r') as f:
            result = subprocess.run(
                cmd,
                stdin=f,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True
            )
        
        if result.returncode == 0:
            print("\n✓ Database restored successfully!")
            print(f"Database '{database}' has been restored from {basename}")
            return True
        else:
            print(f"\n✗ Restore failed!")
            print(f"Error: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print("\n✗ mysql command not found!")
        print("Make sure this script is run on the server where MySQL is installed.")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return False

def main():
    print("=" * 70)
    print("MySQL Database Restore Tool")
    print("=" * 70)
    
    # List available backups
    backups = list_backups()
    
    if not backups:
        return
    
    # Get user choice
    print("\nOptions:")
    print("  - Enter a number to restore that backup")
    print("  - Enter 'q' to quit")
    
    choice = input("\nYour choice: ").strip()
    
    if choice.lower() == 'q':
        print("\nExiting.")
        return
    
    # Validate choice
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(backups):
            backup_file = backups[idx]
            restore_backup(backup_file)
        else:
            print(f"\n✗ Invalid choice. Please enter a number between 1 and {len(backups)}")
    except ValueError:
        print("\n✗ Invalid input. Please enter a number or 'q'")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Restore cancelled by user.")
        sys.exit(1)

