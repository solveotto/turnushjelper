import json
import logging

from app.database import get_db_session
from app.extensions import cache
from app.models import TurnusSet, Shifts, Favorites

logger = logging.getLogger(__name__)


def create_turnus_set(name, year_identifier, is_active=False, turnus_file_path=None, df_file_path=None):
    """Create a new turnus set with optional file paths"""
    db_session = get_db_session()
    try:
        existing = db_session.query(TurnusSet).filter_by(year_identifier=year_identifier).first()
        if existing:
            return False, f"Turnus set with identifier {year_identifier} already exists"

        if is_active:
            db_session.query(TurnusSet).update({'is_active': 0})

        new_set = TurnusSet(
            name=name,
            year_identifier=year_identifier,
            is_active=1 if is_active else 0,
            turnus_file_path=turnus_file_path,
            df_file_path=df_file_path
        )
        db_session.add(new_set)
        db_session.commit()
        if is_active:
            cache.delete_memoized(get_active_turnus_set)
        return True, f"Turnus set {year_identifier} created successfully"
    except Exception as e:
        db_session.rollback()
        return False, f"Error creating turnus set: {e}"
    finally:
        db_session.close()


def get_all_turnus_sets():
    """Get a list of all turnus sets"""
    db_session = get_db_session()
    try:
        sets = db_session.query(TurnusSet).order_by(TurnusSet.year_identifier.desc()).all()
        return [
            {
                'id': ts.id,
                'name': ts.name,
                'year_identifier': ts.year_identifier,
                'is_active': ts.is_active,
                'created_at': ts.created_at,
                'turnus_file_path': ts.turnus_file_path,
                'df_file_path': ts.df_file_path
            }
            for ts in sets
        ]
    finally:
        db_session.close()


def get_turnus_set_by_year(year_identifier):
    """Get turnus set by year identifier (e.g., 'R25', 'R26')"""
    db_session = get_db_session()
    try:
        turnus_set = db_session.query(TurnusSet).filter_by(year_identifier=year_identifier).first()
        if turnus_set:
            return {
                'id': turnus_set.id,
                'name': turnus_set.name,
                'year_identifier': turnus_set.year_identifier,
                'is_active': turnus_set.is_active,
                'created_at': turnus_set.created_at,
                'turnus_file_path': turnus_set.turnus_file_path,
                'df_file_path': turnus_set.df_file_path
            }
        return None
    finally:
        db_session.close()


def get_turnus_set_by_id(turnus_set_id):
    """Get turnus set by ID"""
    db_session = get_db_session()
    try:
        turnus_set = db_session.query(TurnusSet).filter_by(id=turnus_set_id).first()
        if turnus_set:
            return {
                'id': turnus_set.id,
                'name': turnus_set.name,
                'year_identifier': turnus_set.year_identifier,
                'is_active': turnus_set.is_active,
                'created_at': turnus_set.created_at,
                'turnus_file_path': turnus_set.turnus_file_path,
                'df_file_path': turnus_set.df_file_path
            }
        return None
    finally:
        db_session.close()


def set_active_turnus_set(turnus_set_id):
    """Switch which turnus set is currently active"""
    db_session = get_db_session()
    try:
        db_session.query(TurnusSet).update({'is_active': 0})

        turnus_set = db_session.query(TurnusSet).filter_by(id=turnus_set_id).first()
        if not turnus_set:
            return False, "Turnussett ikke funnet"

        turnus_set.is_active = 1
        db_session.commit()
        cache.delete_memoized(get_active_turnus_set)
        return True, f"Turnussett {turnus_set.year_identifier} er nå aktivt"
    except Exception as e:
        db_session.rollback()
        return False, f"Error setting active turnus set: {e}"
    finally:
        db_session.close()


@cache.memoize(timeout=60)
def get_active_turnus_set():
    """Get the currently active turnus set"""
    db_session = get_db_session()
    try:
        active_set = db_session.query(TurnusSet).filter_by(is_active=1).first()
        if active_set:
            return {
                'id': active_set.id,
                'name': active_set.name,
                'year_identifier': active_set.year_identifier,
                'is_active': active_set.is_active,
                'created_at': active_set.created_at,
                'turnus_file_path': active_set.turnus_file_path,
                'df_file_path': active_set.df_file_path
            }
        return None
    finally:
        db_session.close()


def add_shifts_to_turnus_set(file_path, turnus_set_id):
    """Load shifts from a JSON file into a specific turnus set"""
    db_session = get_db_session()
    try:
        with open(file_path, 'r') as f:
            turnus_data = json.load(f)

        existing_titles = {
            r.title
            for r in db_session.query(Shifts.title).filter_by(turnus_set_id=turnus_set_id).all()
        }
        for x in turnus_data:
            for name in x.keys():
                if name not in existing_titles:
                    db_session.add(Shifts(title=name, turnus_set_id=turnus_set_id))
                    existing_titles.add(name)

        db_session.commit()
        logger.info("Shifts added to turnus set %s successfully", turnus_set_id)
        return True, "Skift lagt til i turnussett"
    except Exception as e:
        db_session.rollback()
        logger.error("Error adding shifts to turnus set: %s", e)
        return False, f"Error adding shifts to turnus set: {e}"
    finally:
        db_session.close()


def get_shifts_by_turnus_set(turnus_set_id):
    """Get all shift names for a specific turnus set"""
    db_session = get_db_session()
    try:
        shifts = db_session.query(Shifts).filter_by(turnus_set_id=turnus_set_id).all()
        return [shift.title for shift in shifts]
    finally:
        db_session.close()


def delete_turnus_set(turnus_set_id):
    """Delete a turnus set and all its associated data"""
    db_session = get_db_session()
    try:
        from app.models import SoknadsskjemaChoice
        turnus_set = db_session.query(TurnusSet).filter_by(id=turnus_set_id).first()
        if not turnus_set:
            return False, "Turnussett ikke funnet"

        db_session.query(Shifts).filter_by(turnus_set_id=turnus_set_id).delete()
        db_session.query(Favorites).filter_by(turnus_set_id=turnus_set_id).delete()
        db_session.query(SoknadsskjemaChoice).filter_by(turnus_set_id=turnus_set_id).delete()
        db_session.delete(turnus_set)
        db_session.commit()
        cache.delete_memoized(get_active_turnus_set)
        return True, f"Turnussett {turnus_set.year_identifier} slettet"
    except Exception as e:
        db_session.rollback()
        return False, f"Error deleting turnus set: {e}"
    finally:
        db_session.close()


def update_turnus_set_paths(turnus_set_id, turnus_file_path, df_file_path):
    """Update file paths for an existing turnus set"""
    db_session = get_db_session()
    try:
        turnus_set = db_session.query(TurnusSet).filter_by(id=turnus_set_id).first()
        if not turnus_set:
            return False, "Turnussett ikke funnet"

        turnus_set.turnus_file_path = turnus_file_path
        turnus_set.df_file_path = df_file_path
        db_session.commit()
        return True, "Filstier oppdatert"
    except Exception as e:
        db_session.rollback()
        return False, f"Error updating file paths: {e}"
    finally:
        db_session.close()


def refresh_turnus_set_shifts(turnus_set_id, json_file_path):
    """Re-sync shift names from a new JSON file into the database.

    Matches old names to new names by prefix to preserve favorites.
    Returns a summary dict: {renamed: [...], added: [...], removed: [...], unchanged: [...]}
    """
    db_session = get_db_session()
    try:
        old_shifts = db_session.query(Shifts).filter_by(turnus_set_id=turnus_set_id).all()
        old_names = set(s.title for s in old_shifts)

        with open(json_file_path, 'r') as f:
            turnus_data = json.load(f)
        new_names = set()
        for entry in turnus_data:
            for name in entry.keys():
                new_names.add(name)

        unchanged = old_names & new_names
        unmatched_old = old_names - unchanged
        unmatched_new = new_names - unchanged

        rename_map = {}
        matched_new = set()
        for old_name in list(unmatched_old):
            candidates = [n for n in unmatched_new if n.startswith(old_name) or old_name.startswith(n)]
            if len(candidates) == 1:
                rename_map[old_name] = candidates[0]
                matched_new.add(candidates[0])
                # Claim the candidate so a second old name can't be renamed to
                # the same title (would violate the unique constraint).
                unmatched_new.discard(candidates[0])

        removed = unmatched_old - set(rename_map.keys())
        added = unmatched_new - matched_new

        # 1. Renames
        for old_name, new_name in rename_map.items():
            db_session.query(Shifts).filter_by(
                title=old_name, turnus_set_id=turnus_set_id
            ).update({'title': new_name})
            db_session.query(Favorites).filter_by(
                shift_title=old_name, turnus_set_id=turnus_set_id
            ).update({'shift_title': new_name})

        # 2. Delete orphaned shifts
        for name in removed:
            db_session.query(Shifts).filter_by(
                title=name, turnus_set_id=turnus_set_id
            ).delete()

        # 3. Add new shifts
        for name in added:
            db_session.add(Shifts(title=name, turnus_set_id=turnus_set_id))

        db_session.commit()

        return {
            'renamed': [{'old': k, 'new': v} for k, v in rename_map.items()],
            'added': sorted(added),
            'removed': sorted(removed),
            'unchanged': sorted(unchanged)
        }
    except Exception as e:
        db_session.rollback()
        raise e
    finally:
        db_session.close()
