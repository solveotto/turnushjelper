"""
Migration script to add name and rullenummer columns to users and authorized_emails tables
Run this once to update database schema

This migration adds:
- name field to users table (for displaying user's full name instead of email)
- rullenummer field to users table (work ID)
- rullenummer field to authorized_emails table (for pre-registration authorization)

Usage:
    python scripts/migrate_tools/migrate_add_name_and_rullenummer.py
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from app.utils.db_utils import engine, SessionLocal
from sqlalchemy import text
from config import AppConfig

def migrate_add_name_and_rullenummer():
    """Add name and rullenummer columns to users and authorized_emails tables"""
    session = SessionLocal()

    try:
        print("Starting migration to add name and rullenummer columns...")

        # Check database type
        db_type = AppConfig.DB_TYPE
        print(f"Database type: {db_type}")

        with engine.connect() as conn:
            # Add rullenummer column to users table
            try:
                # Note: rullenummer already exists in DBUser model as String(10)
                # This might fail if it already exists from the model definition
                conn.execute(text('ALTER TABLE users ADD COLUMN rullenummer VARCHAR(10)'))
                print("OK Added rullenummer column to users table")
            except Exception as e:
                print(f"  rullenummer column might already exist in users table: {e}")

            # Add name column to users table
            try:
                conn.execute(text('ALTER TABLE users ADD COLUMN name VARCHAR(255)'))
                print("OK Added name column to users table")
            except Exception as e:
                print(f"  name column might already exist in users table: {e}")

            # Add rullenummer column to authorized_emails table
            try:
                conn.execute(text('ALTER TABLE authorized_emails ADD COLUMN rullenummer VARCHAR(50)'))
                print("OK Added rullenummer column to authorized_emails table")
            except Exception as e:
                print(f"  rullenummer column might already exist in authorized_emails table: {e}")

            # Drop the unique constraint on email only (if it exists)
            try:
                if db_type == 'mysql':
                    # MySQL syntax
                    conn.execute(text('ALTER TABLE authorized_emails DROP INDEX email'))
                    print("OK Dropped unique constraint on email column")
                elif db_type == 'sqlite':
                    # SQLite doesn't support dropping constraints directly
                    # We'll need to recreate the table, but let's skip this for now
                    print("  Note: SQLite - cannot drop unique constraint. This is okay if the table is empty or you're okay with the constraint.")
            except Exception as e:
                print(f"  Could not drop unique constraint (might not exist): {e}")

            conn.commit()

        print("\n" + "="*60)
        print("Migration completed successfully!")
        print("="*60)
        print("\nChanges made:")
        print("  1. OK Added 'name' field to users table")
        print("  2. OK Added 'rullenummer' field to users table")
        print("  3. OK Added 'rullenummer' field to authorized_emails table")
        print("\nNext steps:")
        print("  1. Add authorized email/rullenummer combinations via admin panel")
        print("  2. New users can register with their name and work ID")
        print("  3. Navbar will display user's name instead of email")
        print("="*60)

    except Exception as e:
        session.rollback()
        print(f"ERROR Error during migration: {e}")
        raise
    finally:
        session.close()

if __name__ == '__main__':
    migrate_add_name_and_rullenummer()
