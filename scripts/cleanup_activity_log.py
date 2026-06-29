"""
Retention cleanup for GDPR data minimisation. Run periodically via cron on Hetzner:
    python scripts/cleanup_activity_log.py

Deletes:
  - page_view activity events older than PAGE_VIEW_RETENTION_DAYS (30)
  - all other activity events (login, logout, favorite_add, favorite_remove)
    older than ACTIVITY_RETENTION_DAYS (180)
  - email verification / password reset tokens past their expiry

Retention logic lives in the service layer so it is unit-tested:
  app.services.activity_service.cleanup_old_activity
  app.services.auth_service.purge_expired_tokens
"""

import sys
import os

project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from app.services.activity_service import cleanup_old_activity
from app.services.auth_service import purge_expired_tokens


def main():
    try:
        page_views, other = cleanup_old_activity()
        print(f"Deleted {page_views} old page_view events and {other} other activity events.")
    except Exception as e:
        print(f"Error during activity cleanup: {e}")

    try:
        tokens = purge_expired_tokens()
        print(f"Deleted {tokens} expired tokens.")
    except Exception as e:
        print(f"Error during token cleanup: {e}")


if __name__ == "__main__":
    main()
