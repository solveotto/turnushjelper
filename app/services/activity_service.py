import logging
from datetime import datetime

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
                timestamp=datetime.utcnow(),
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
    """Return per-user activity aggregates."""
    db_session = get_db_session()
    try:
        rows = (
            db_session.query(UserActivity, DBUser.username)
            .outerjoin(DBUser, UserActivity.user_id == DBUser.id)
            .all()
        )
    finally:
        db_session.close()

    stats = {}
    for activity, username in rows:
        uid = activity.user_id
        if uid not in stats:
            stats[uid] = {
                "username": username or "(slettet)",
                "login_count": 0,
                "page_views": 0,
                "favorite_add": 0,
                "favorite_remove": 0,
            }
        s = stats[uid]
        if activity.event_type == "login":
            s["login_count"] += 1
        elif activity.event_type == "page_view":
            s["page_views"] += 1
        elif activity.event_type == "favorite_add":
            s["favorite_add"] += 1
        elif activity.event_type == "favorite_remove":
            s["favorite_remove"] += 1

    result = []
    for uid, s in stats.items():
        result.append({
            "username": s["username"],
            "login_count": s["login_count"],
            "page_views": s["page_views"],
            "favorite_add": s["favorite_add"],
            "favorite_remove": s["favorite_remove"],
        })

    result.sort(key=lambda x: x["login_count"], reverse=True)
    return result
