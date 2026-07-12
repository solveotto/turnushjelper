import logging
from sqlalchemy import func

from app.database import get_db_session
from app.models import Favorites

logger = logging.getLogger(__name__)


def get_favorite_lst(user_id, turnus_set_id=None):
    db_session = get_db_session()
    try:
        query = db_session.query(Favorites.shift_title).filter_by(user_id=user_id)

        if turnus_set_id:
            query = query.filter_by(turnus_set_id=turnus_set_id)
        else:
            from app.services.turnus_service import get_active_turnus_set
            active_set = get_active_turnus_set()
            if active_set:
                query = query.filter_by(turnus_set_id=active_set['id'])
            else:
                return []

        results = query.order_by(Favorites.order_index).all()

        seen = set()
        shift_titles = []
        for result in results:
            if result.shift_title not in seen:
                seen.add(result.shift_title)
                shift_titles.append(result.shift_title)

        return shift_titles
    finally:
        db_session.close()


def user_has_favorites_in_other_sets(user_id, exclude_turnus_set_id):
    """Check if user has favorites in any turnus set other than the specified one."""
    db_session = get_db_session()
    try:
        return db_session.query(
            db_session.query(Favorites)
            .filter(Favorites.user_id == user_id)
            .filter(Favorites.turnus_set_id != exclude_turnus_set_id)
            .exists()
        ).scalar()
    finally:
        db_session.close()


def update_favorite_order(user_id, turnus_set_id=None):
    db_session = get_db_session()
    try:
        if not turnus_set_id:
            from app.services.turnus_service import get_active_turnus_set
            active_set = get_active_turnus_set()
            if not active_set:
                return False
            turnus_set_id = active_set['id']

        current_favorites = db_session.query(Favorites).filter_by(
            user_id=user_id,
            turnus_set_id=turnus_set_id
        ).order_by(Favorites.order_index).all()

        for index, favorite in enumerate(current_favorites):
            favorite.order_index = index

        db_session.commit()
        logger.debug("Favorite order updated successfully")
        return True
    except Exception as e:
        db_session.rollback()
        logger.error("Failed to modify database. Changes only stored locally. Error = %s", e)
        return False
    finally:
        db_session.close()


def get_max_ordered_index(user_id, turnus_set_id=None):
    """Get the maximum order index for a user's favorites in a specific turnus set"""
    db_session = get_db_session()
    try:
        query = db_session.query(func.max(Favorites.order_index)).filter_by(user_id=user_id)

        if turnus_set_id:
            query = query.filter_by(turnus_set_id=turnus_set_id)
        else:
            from app.services.turnus_service import get_active_turnus_set
            active_set = get_active_turnus_set()
            if active_set:
                query = query.filter_by(turnus_set_id=active_set['id'])

        result = query.scalar()
        return result if result is not None else 0
    finally:
        db_session.close()


def cleanup_duplicate_favorites(session, user_id, shift_title, turnus_set_id):
    """Clean up duplicate favorites for a specific user/shift/turnus_set combination"""
    try:
        duplicates = session.query(Favorites).filter_by(
            user_id=user_id,
            shift_title=shift_title,
            turnus_set_id=turnus_set_id
        ).order_by(Favorites.order_index).all()

        if len(duplicates) > 1:
            keep_entry = duplicates[0]
            delete_entries = duplicates[1:]

            for entry in delete_entries:
                session.delete(entry)

            logger.info("Cleaned up %d duplicate favorites for user %s, shift '%s'", len(delete_entries), user_id, shift_title)

    except Exception as e:
        logger.error("Error cleaning up duplicates: %s", e)
        raise


def add_favorite(user_id, title, order_index, turnus_set_id=None):
    """Add a shift to user's favorites for a specific turnus set"""
    db_session = get_db_session()
    try:
        if not turnus_set_id:
            from app.services.turnus_service import get_active_turnus_set
            active_set = get_active_turnus_set()
            if not active_set:
                return False
            turnus_set_id = active_set['id']

        existing = db_session.query(Favorites).filter_by(
            user_id=user_id,
            shift_title=title,
            turnus_set_id=turnus_set_id
        ).first()

        if existing:
            cleanup_duplicate_favorites(db_session, user_id, title, turnus_set_id)
            return True

        new_favorite = Favorites(
            user_id=user_id,
            shift_title=title,
            order_index=order_index,
            turnus_set_id=turnus_set_id
        )
        db_session.add(new_favorite)
        db_session.commit()
        return True
    except Exception as e:
        db_session.rollback()
        logger.error("Error adding favorite: %s", e)
        return False
    finally:
        db_session.close()


def remove_favorite(user_id, title, turnus_set_id=None):
    """Remove a shift from user's favorites for a specific turnus set"""
    db_session = get_db_session()
    try:
        if not turnus_set_id:
            from app.services.turnus_service import get_active_turnus_set
            active_set = get_active_turnus_set()
            if not active_set:
                return False
            turnus_set_id = active_set['id']

        favorites = db_session.query(Favorites).filter_by(
            user_id=user_id,
            shift_title=title,
            turnus_set_id=turnus_set_id
        ).all()

        if favorites:
            deleted_count = 0
            for favorite in favorites:
                db_session.delete(favorite)
                deleted_count += 1

            db_session.commit()
            if deleted_count > 1:
                logger.info("Removed %d duplicate favorites for user %s, shift '%s'", deleted_count, user_id, title)
            return True
        return False
    except Exception as e:
        db_session.rollback()
        logger.error("Error removing favorite: %s", e)
        return False
    finally:
        db_session.close()
