"""
Migration script to add password reset feature
Adds token_type column to email_verification_tokens table to distinguish
between verification and password reset tokens.
"""

import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from app.utils.db_utils import engine, SessionLocal
from sqlalchemy import text
from config import AppConfig


def migrate_database():
    """Add token_type column to email_verification_tokens table"""
    session = SessionLocal()

    try:
        print("Starting password reset migration...")

        # Check database type
        db_type = AppConfig.DB_TYPE
        print(f"Database type: {db_type}")

        with engine.connect() as conn:
            # Add token_type column with default 'verification' for backward compatibility
            try:
                if db_type == 'sqlite':
                    conn.execute(text(
                        "ALTER TABLE email_verification_tokens "
                        "ADD COLUMN token_type VARCHAR(50) DEFAULT 'verification'"
                    ))
                else:  # mysql
                    conn.execute(text(
                        "ALTER TABLE email_verification_tokens "
                        "ADD COLUMN token_type VARCHAR(50) DEFAULT 'verification'"
                    ))
                print("Added token_type column to email_verification_tokens")
            except Exception as e:
                print(f"token_type column might already exist: {e}")

            conn.commit()

        print("\nMigration completed successfully!")
        print("\nThe forgot password feature is now enabled.")
        print("Password reset tokens will use token_type='password_reset'")

    except Exception as e:
        session.rollback()
        print(f"Error during migration: {e}")
        raise
    finally:
        session.close()


if __name__ == '__main__':
    migrate_database()
