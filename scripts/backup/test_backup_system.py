#!/usr/bin/env python3
"""
Test the backup system before scheduling
Runs a series of checks to verify everything is configured correctly

Usage:
    python scripts/backup/test_backup_system.py
"""

import sys
import os
import subprocess

# Add project root to path (go up 3 levels: backup -> scripts -> project_root)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from config import AppConfig

def print_header(text):
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)

def print_check(description, passed, details=""):
    status = "✓" if passed else "✗"
    color = "\033[92m" if passed else "\033[91m"
    reset = "\033[0m"
    
    print(f"{color}{status}{reset} {description}")
    if details:
        print(f"  → {details}")

def test_database_config():
    """Test 1: Check database configuration"""
    print_header("Test 1: Database Configuration")
    
    try:
        db_type = AppConfig.DB_TYPE

        if db_type != 'mysql':
            print_check("Database type", False, f"Expected MySQL, got {db_type}")
            return False

        print_check("Database type", True, "MySQL")

        # Check required fields
        fields = {
            'host': AppConfig.MYSQL_HOST,
            'user': AppConfig.MYSQL_USER,
            'password': AppConfig.MYSQL_PASSWORD,
            'database': AppConfig.MYSQL_DATABASE,
        }
        all_present = True

        for field, value in fields.items():
            if value:
                print_check(f"MySQL {field}", True, "Configured")
            else:
                print_check(f"MySQL {field}", False, "Missing")
                all_present = False

        return all_present
        
    except Exception as e:
        print_check("Database config", False, str(e))
        return False

def test_mysqldump_available():
    """Test 2: Check if mysqldump command is available"""
    print_header("Test 2: mysqldump Command")
    
    try:
        result = subprocess.run(
            ['mysqldump', '--version'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            version = result.stdout.strip()
            print_check("mysqldump available", True, version)
            return True
        else:
            print_check("mysqldump available", False, "Command failed")
            return False
            
    except FileNotFoundError:
        print_check("mysqldump available", False, "Command not found — install mysql-client")
        return False

def test_mysql_connection():
    """Test 3: Check MySQL connection"""
    print_header("Test 3: MySQL Connection")
    
    try:
        host = AppConfig.MYSQL_HOST
        user = AppConfig.MYSQL_USER
        password = AppConfig.MYSQL_PASSWORD
        database = AppConfig.MYSQL_DATABASE
        
        # Try to connect using mysql command
        cmd = [
            'mysql',
            f'-h{host}',
            f'-u{user}',
            f'-p{password}',
            database,
            '-e',
            'SELECT 1;'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print_check("MySQL connection", True, f"Connected to {database}")
            return True
        else:
            print_check("MySQL connection", False, result.stderr.strip())
            return False
            
    except FileNotFoundError:
        print_check("MySQL connection", False, "mysql command not found — install mysql-client")
        return False
    except Exception as e:
        print_check("MySQL connection", False, str(e))
        return False

def test_backup_directory():
    """Test 4: Check backup directory"""
    print_header("Test 4: Backup Directory")
    
    backup_dir = os.path.join(project_root, 'backups')
    
    if not os.path.exists(backup_dir):
        try:
            os.makedirs(backup_dir)
            print_check("Backup directory", True, f"Created: {backup_dir}")
            return True
        except Exception as e:
            print_check("Backup directory", False, f"Cannot create: {e}")
            return False
    else:
        print_check("Backup directory exists", True, backup_dir)
        
        # Check if writable
        test_file = os.path.join(backup_dir, '.test_write')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            print_check("Directory writable", True)
            return True
        except Exception as e:
            print_check("Directory writable", False, str(e))
            return False

def test_log_directory():
    """Test 5: Check log directory"""
    print_header("Test 5: Log Directory")
    
    log_dir = os.path.join(project_root, 'app', 'logs')
    
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir)
            print_check("Log directory", True, f"Created: {log_dir}")
            return True
        except Exception as e:
            print_check("Log directory", False, f"Cannot create: {e}")
            return False
    else:
        print_check("Log directory exists", True, log_dir)
        
        # Check if writable
        log_file = os.path.join(log_dir, 'backup.log')
        try:
            with open(log_file, 'a') as f:
                f.write(f'[TEST] Backup system test at {os.path.basename(__file__)}\n')
            print_check("Log file writable", True, log_file)
            return True
        except Exception as e:
            print_check("Log file writable", False, str(e))
            return False

def test_backup_script_exists():
    """Test 6: Check if backup script exists"""
    print_header("Test 6: Backup Script")
    
    backup_script = os.path.join(project_root, 'scripts', 'backup', 'daily_mysql_backup.py')
    
    if os.path.exists(backup_script):
        print_check("Backup script exists", True, backup_script)
        
        # Check if executable
        if os.access(backup_script, os.X_OK) or sys.platform == 'win32':
            print_check("Script permissions", True)
            return True
        else:
            print_check("Script permissions", False, "Not executable")
            print("  ℹ Run: chmod +x scripts/backup/daily_mysql_backup.py")
            return False
    else:
        print_check("Backup script exists", False, "File not found")
        return False

def run_test_backup():
    """Test 7: Try to create a test backup"""
    print_header("Test 7: Create Test Backup")
    
    try:
        # Import and run the backup script
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "daily_mysql_backup",
            os.path.join(project_root, 'scripts', 'backup', 'daily_mysql_backup.py')
        )
        backup_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backup_module)
        
        print("Running backup script...")
        success = backup_module.create_backup()
        
        if success:
            print_check("Test backup", True, "Backup created successfully!")
            
            # List backup files
            backup_dir = os.path.join(project_root, 'backups')
            import glob
            backups = glob.glob(os.path.join(backup_dir, 'backup_*.sql'))
            if backups:
                latest = max(backups, key=os.path.getctime)
                size = os.path.getsize(latest) / 1024
                print(f"  → Latest backup: {os.path.basename(latest)} ({size:.1f} KB)")
            return True
        else:
            print_check("Test backup", False, "Backup failed")
            return False
            
    except Exception as e:
        print_check("Test backup", False, str(e))
        return False

def main():
    print("\n" + "=" * 70)
    print(" MySQL BACKUP SYSTEM TEST")
    print("=" * 70)
    print("\nThis script tests your backup configuration before scheduling.")
    
    tests = [
        ("Database Configuration", test_database_config),
        ("mysqldump Command", test_mysqldump_available),
        ("MySQL Connection", test_mysql_connection),
        ("Backup Directory", test_backup_directory),
        ("Log Directory", test_log_directory),
        ("Backup Script", test_backup_script_exists),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        color = "\033[92m" if result else "\033[91m"
        reset = "\033[0m"
        print(f"{color}{status}{reset} - {test_name}")
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All tests passed! Ready to schedule daily backups.")
        print("\nNext steps:")
        print("1. Test the backup manually: python scripts/backup/daily_mysql_backup.py")
        print("2. Set up cron job on Hetzner (see README.md)")
        
        # Ask if user wants to run test backup
        if sys.platform != 'win32':  # Only on Unix-like systems
            response = input("\nRun a test backup now? (yes/no): ")
            if response.lower() == 'yes':
                run_test_backup()
    else:
        print(f"\n✗ {total - passed} test(s) failed. Please fix issues before scheduling.")
        print("\nSee README.md for troubleshooting help.")
    
    return passed == total

if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user.")
        sys.exit(1)

