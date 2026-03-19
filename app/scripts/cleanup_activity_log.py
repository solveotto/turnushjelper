"""
Cleanup script to delete page_view activity events older than RETENTION_DAYS.
Other event types (login, logout, favorite_add, favorite_remove) are kept forever.

Run via scheduled task (PythonAnywhere scheduled tasks or cron):
    python app/scripts/cleanup_activity_log.py

PythonAnywhere: set up a daily scheduled task pointing to this file.
"""

import sys
import os
from datetime import datetime, timedelta, timezone

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from app.database import get_db_session
from app.models import UserActivity

RETENTION_DAYS = 30


def cleanup_activity_log():
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    print(f"Deleting page_view events older than {RETENTION_DAYS} days (before {cutoff.strftime('%Y-%m-%d %H:%M:%S')} UTC)")

    db_session = get_db_session()
    try:
        deleted = (
            db_session.query(UserActivity)
            .filter(
                UserActivity.event_type == "page_view",
                UserActivity.timestamp < cutoff,
            )
            .delete(synchronize_session=False)
        )
        db_session.commit()
        print(f"Deleted {deleted} page_view rows.")
        return deleted
    except Exception as e:
        db_session.rollback()
        print(f"Error during cleanup: {e}")
        return 0
    finally:
        db_session.close()


if __name__ == "__main__":
    cleanup_activity_log()
