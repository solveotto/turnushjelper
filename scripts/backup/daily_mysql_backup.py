#!/usr/bin/env python3
"""
Daily MySQL Database Backup Script

Schedule via cron on Hetzner:
  0 2 * * * /home/deploy/turnushjelper/venv/bin/python /home/deploy/turnushjelper/scripts/backup/daily_mysql_backup.py

Features:
- Creates daily backups with timestamps
- Keeps last 7 days of backups (configurable)
- Logs all operations
"""

import sys
import os
import subprocess
from datetime import datetime, timedelta
import glob

# Add project root to path (go up 3 levels: backup -> scripts -> project_root)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from config import AppConfig

# Configuration
# Backups live alongside the project dir, not inside it, so they survive a fresh checkout
BACKUP_DIR = os.path.join(os.path.dirname(project_root), 'backups')
KEEP_DAYS = 7   # Delete backups older than this
MIN_BACKUPS = 3  # Always keep at least this many most-recent, regardless of age
LOG_FILE = os.path.join(project_root, 'app', 'logs', 'backup.log')

def log_message(message):
    """Log message with timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {message}\n"
    
    print(log_entry.strip())
    
    # Write to log file
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Warning: Could not write to log file: {e}")

def cleanup_old_backups():
    """Remove backups older than KEEP_DAYS, always keeping the MIN_BACKUPS most recent."""
    try:
        backup_pattern = os.path.join(BACKUP_DIR, 'backup_*.sql')
        # Sort newest-first — filenames are YYYYMMDD_HHMMSS so lexicographic order works
        all_backups = sorted(glob.glob(backup_pattern), reverse=True)

        if len(all_backups) <= MIN_BACKUPS:
            log_message(f"Skipping cleanup: only {len(all_backups)} backup(s) exist")
            return

        cutoff_date = datetime.now() - timedelta(days=KEEP_DAYS)
        deleted_count = 0

        # The MIN_BACKUPS newest are always kept; only consider the rest for deletion
        for backup_file in all_backups[MIN_BACKUPS:]:
            try:
                basename = os.path.basename(backup_file)
                date_str = basename.split('_')[1]  # YYYYMMDD
                file_date = datetime.strptime(date_str, '%Y%m%d')

                if file_date < cutoff_date:
                    os.remove(backup_file)
                    deleted_count += 1
                    log_message(f"Deleted old backup: {basename}")
            except (ValueError, IndexError) as e:
                log_message(f"Warning: Could not parse date from {basename}: {e}")

        if deleted_count > 0:
            log_message(f"Cleaned up {deleted_count} old backup(s)")
        else:
            log_message("No old backups to clean up")

    except Exception as e:
        log_message(f"Error during cleanup: {e}")

def create_backup():
    """Create MySQL database backup"""
    
    log_message("=" * 60)
    log_message("Starting daily MySQL backup")
    
    try:
        # Get database configuration
        db_type = AppConfig.DB_TYPE

        if db_type != 'mysql':
            log_message(f"Database type is {db_type}, not MySQL. Skipping backup.")
            return False

        # Get MySQL connection info
        host = AppConfig.MYSQL_HOST
        user = AppConfig.MYSQL_USER
        password = AppConfig.MYSQL_PASSWORD
        database = AppConfig.MYSQL_DATABASE
        
        # Create backup directory if it doesn't exist
        os.makedirs(BACKUP_DIR, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(BACKUP_DIR, f'backup_{timestamp}.sql')
        
        log_message(f"Database: {database}")
        log_message(f"Backup file: {backup_file}")
        
        # Build mysqldump command
        cmd = [
            'mysqldump',
            f'-h{host}',
            f'-u{user}',
            f'-p{password}',
            '--no-tablespaces',
            database
        ]
        
        # Run mysqldump and save to file
        with open(backup_file, 'w') as f:
            result = subprocess.run(
                cmd, 
                stdout=f, 
                stderr=subprocess.PIPE, 
                text=True
            )
        
        if result.returncode == 0:
            # Check file size
            file_size = os.path.getsize(backup_file)
            file_size_kb = file_size / 1024
            file_size_mb = file_size_kb / 1024
            
            if file_size_mb >= 1:
                size_str = f"{file_size_mb:.2f} MB"
            else:
                size_str = f"{file_size_kb:.1f} KB"
            
            log_message(f"✓ Backup created successfully!")
            log_message(f"  Size: {size_str}")
            
            # Cleanup old backups
            cleanup_old_backups()
            
            # Count remaining backups
            remaining_backups = len(glob.glob(os.path.join(BACKUP_DIR, 'backup_*.sql')))
            log_message(f"Total backups kept: {remaining_backups}")
            
            log_message("=" * 60)
            return True
        else:
            log_message(f"✗ Backup failed!")
            log_message(f"Error: {result.stderr}")
            
            # Remove incomplete backup file
            if os.path.exists(backup_file):
                os.remove(backup_file)
            
            log_message("=" * 60)
            return False
            
    except FileNotFoundError:
        log_message("✗ mysqldump command not found — install mysql-client")
        log_message("=" * 60)
        return False
        
    except Exception as e:
        log_message(f"✗ Unexpected error: {e}")
        log_message("=" * 60)
        return False

if __name__ == '__main__':
    success = create_backup()
    sys.exit(0 if success else 1)

