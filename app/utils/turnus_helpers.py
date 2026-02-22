from flask import session
from app.utils import db_utils


def get_user_turnus_set():
    """Get the turnus set for current user (their session choice or database active set)."""
    active_set = db_utils.get_active_turnus_set()

    user_choice = session.get('user_selected_turnus_set')
    if user_choice:
        all_sets = db_utils.get_all_turnus_sets()
        user_set = next((ts for ts in all_sets if ts['id'] == user_choice), None)
        if user_set:
            return user_set
        else:
            session.pop('user_selected_turnus_set', None)

    return active_set


def iter_turnus_weeks(turnus_data):
    """Yield (turnus_name, week_nr, week_data) for every valid week entry.

    Skips non-dict values at the week level (e.g. 'kl_timer', 'tj_timer'
    metadata strings that live at the same dict level as week numbers).
    """
    for entry in turnus_data:
        for turnus_name, weeks in entry.items():
            if not isinstance(weeks, dict):
                continue
            for week_nr, week_data in weeks.items():
                if not isinstance(week_data, dict):
                    continue
                yield turnus_name, week_nr, week_data


def iter_turnus_days(turnus_data):
    """Yield (turnus_name, week_nr, day_nr, day_data) for every valid day entry."""
    for turnus_name, week_nr, week_data in iter_turnus_weeks(turnus_data):
        for day_nr, day_data in week_data.items():
            if not isinstance(day_data, dict):
                continue
            yield turnus_name, week_nr, day_nr, day_data
