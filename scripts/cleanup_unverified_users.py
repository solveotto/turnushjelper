"""
Cleanup script to delete unverified user accounts after X days
Schedule via cron on Hetzner.
"""

import sys
import os
from datetime import datetime, timedelta

# Add project root to path
project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from app.utils.db_utils import SessionLocal, DBUser, EmailVerificationToken, Favorites
from config import AppConfig

def cleanup_unverified_users():
    """Delete unverified users older than configured days"""
    session = SessionLocal()

    try:
        # Get cleanup threshold from config
        cleanup_days = AppConfig.UNVERIFIED_CLEANUP_DAYS
        cutoff_date = datetime.now() - timedelta(days=cleanup_days)

        print(f"Cleanup unverified users created before: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")

        # Find unverified users created before cutoff
        unverified_users = session.query(DBUser).filter(
            DBUser.email_verified == 0,
            DBUser.created_at < cutoff_date
        ).all()

        deleted_count = 0
        for user in unverified_users:
            # Delete associated verification tokens
            session.query(EmailVerificationToken).filter_by(user_id=user.id).delete()

            # Delete associated favorites
            session.query(Favorites).filter_by(user_id=user.id).delete()

            # Delete user
            username = user.username
            session.delete(user)
            deleted_count += 1
            print(f"Deleted unverified user: {username} (created {user.created_at})")

        session.commit()
        print(f"\nCleanup complete: {deleted_count} unverified accounts deleted")

        # Also cleanup expired tokens
        cleanup_expired_tokens(session)

        return deleted_count

    except Exception as e:
        session.rollback()
        print(f"Error during cleanup: {e}")
        return 0
    finally:
        session.close()

def cleanup_expired_tokens(session):
    """Remove expired verification tokens"""
    expired_tokens = session.query(EmailVerificationToken).filter(
        EmailVerificationToken.expires_at < datetime.now()
    ).delete()
    session.commit()
    print(f"Deleted {expired_tokens} expired tokens")

if __name__ == '__main__':
    cleanup_unverified_users()
