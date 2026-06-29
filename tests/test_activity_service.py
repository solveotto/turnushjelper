"""Tests for app.services.activity_service."""

from datetime import datetime, timedelta, timezone

from app.models import UserActivity
from app.services import activity_service


def _add_event(db_session, event_type, days_old):
    db_session.add(
        UserActivity(
            user_id=None,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc) - timedelta(days=days_old),
        )
    )


class TestCleanupOldActivity:
    def test_two_tier_retention(self, patch_db, db_session):
        # page_views: 30-day retention
        _add_event(db_session, "page_view", days_old=40)  # deleted
        _add_event(db_session, "page_view", days_old=10)  # kept
        # other events: 180-day retention
        _add_event(db_session, "login", days_old=200)  # deleted
        _add_event(db_session, "login", days_old=100)  # kept
        _add_event(db_session, "favorite_add", days_old=365)  # deleted
        _add_event(db_session, "logout", days_old=5)  # kept
        db_session.commit()

        page_views_deleted, other_deleted = activity_service.cleanup_old_activity()

        assert page_views_deleted == 1
        assert other_deleted == 2

        remaining = db_session.query(UserActivity).all()
        assert len(remaining) == 3
        remaining_types = sorted(e.event_type for e in remaining)
        assert remaining_types == ["login", "logout", "page_view"]
