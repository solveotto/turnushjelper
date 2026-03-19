import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, case

from app.database import get_db_session
from app.models import UserActivity, DBUser

logger = logging.getLogger(__name__)


def log_event(user_id, event_type, details=None, session_duration_seconds=None):
    """Insert a user activity event. Swallows all exceptions to avoid breaking normal flow."""
    try:
        db_session = get_db_session()
        try:
            event = UserActivity(
                user_id=user_id,
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                details=details,
                session_duration_seconds=session_duration_seconds,
            )
            db_session.add(event)
            db_session.commit()
        finally:
            db_session.close()
    except Exception as e:
        logger.warning("activity_service.log_event failed silently: %s", e)


def get_recent_activity(limit=100):
    """Return recent activity events joined with username, ordered by timestamp DESC."""
    db_session = get_db_session()
    try:
        rows = (
            db_session.query(UserActivity, DBUser.username)
            .outerjoin(DBUser, UserActivity.user_id == DBUser.id)
            .order_by(UserActivity.timestamp.desc())
            .limit(limit)
            .all()
        )
        result = []
        for activity, username in rows:
            result.append({
                "id": activity.id,
                "user_id": activity.user_id,
                "username": username or "(slettet)",
                "event_type": activity.event_type,
                "timestamp": activity.timestamp,
                "details": activity.details,
                "session_duration_seconds": activity.session_duration_seconds,
            })
        return result
    finally:
        db_session.close()


def get_user_stats():
    """Return per-user activity aggregates using SQL GROUP BY."""
    db_session = get_db_session()
    try:
        cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)

        rows = (
            db_session.query(
                UserActivity.user_id,
                DBUser.username,
                func.count(case((UserActivity.event_type == "login", 1))).label("login_count"),
                func.count(case((UserActivity.event_type == "page_view", 1))).label("page_views"),
                func.count(case((UserActivity.event_type == "favorite_add", 1))).label("favorite_add"),
                func.count(case((UserActivity.event_type == "favorite_remove", 1))).label("favorite_remove"),
                func.max(UserActivity.timestamp).label("last_active"),
                func.count(case(((UserActivity.timestamp >= cutoff_30d), 1))).label("events_30d"),
            )
            .outerjoin(DBUser, UserActivity.user_id == DBUser.id)
            .group_by(UserActivity.user_id, DBUser.username)
            .all()
        )

        result = []
        for row in rows:
            result.append({
                "username": row.username or "(slettet)",
                "login_count": row.login_count,
                "page_views": row.page_views,
                "favorite_add": row.favorite_add,
                "favorite_remove": row.favorite_remove,
                "last_active": row.last_active,
                "events_30d": row.events_30d,
            })

        result.sort(key=lambda x: (x["last_active"] is None, x["last_active"]), reverse=True)
        return result
    finally:
        db_session.close()
