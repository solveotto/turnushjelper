"""
Migration script to add email verification feature
Run this once to update database schema and mark existing users as verified
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, project_root)

from app.utils.db_utils import engine, SessionLocal, DBUser
from sqlalchemy import text
from config import AppConfig

def migrate_database():
    """Add new columns and tables for email verification"""
    session = SessionLocal()

    try:
        print("Starting migration...")

        # Check database type
        db_type = AppConfig.DB_TYPE
        print(f"Database type: {db_type}")

        # Add columns to users table
        with engine.connect() as conn:
            # Add email column
            try:
                if db_type == 'sqlite':
                    conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))
                else:  # mysql
                    conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))
                print("Added email column")
            except Exception as e:
                print(f"Email column might already exist: {e}")

            # Add email_verified column
            try:
                if db_type == 'sqlite':
                    conn.execute(text("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0"))
                else:
                    conn.execute(text("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0"))
                print("Added email_verified column")
            except Exception as e:
                print(f"email_verified column might already exist: {e}")

            # Add created_at column (SQLite doesn't support DEFAULT CURRENT_TIMESTAMP in ALTER TABLE)
            try:
                if db_type == 'sqlite':
                    conn.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME"))
                else:
                    conn.execute(text("ALTER TABLE users ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
                print("Added created_at column")
            except Exception as e:
                print(f"created_at column might already exist: {e}")

            # Add verification_sent_at column
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN verification_sent_at DATETIME"))
                print("Added verification_sent_at column")
            except Exception as e:
                print(f"verification_sent_at column might already exist: {e}")

            conn.commit()

        # Mark all existing users as verified
        existing_users = session.query(DBUser).all()
        for user in existing_users:
            user.email_verified = 1
            user.email = user.username  # Set email same as username
        session.commit()
        print(f"Marked {len(existing_users)} existing users as verified")

        # Tables are now managed by Alembic — run `alembic upgrade head`
        print("Note: Tables are managed by Alembic. Run 'alembic upgrade head' to create tables.")

        print("\nMigration completed successfully!")
        print("\nNext steps:")
        print("1. Add authorized emails via admin panel")
        print("2. Configure email settings in .env")
        print("3. Test registration flow")

    except Exception as e:
        session.rollback()
        print(f"Error during migration: {e}")
        raise
    finally:
        session.close()

if __name__ == '__main__':
    migrate_database()
