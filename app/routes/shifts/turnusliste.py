import uuid

from flask import redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.extensions import cache
from app.routes.shifts import shifts
from app.utils import db_utils, df_utils
from app.utils.kompdag_utils import count_kompdager, kompdager_max_label
from app.utils.turnus_helpers import get_user_turnus_set


def _turnusliste_cache_key():
    """Per-user, per-turnus-set cache key for the /turnusliste response."""
    ts = get_user_turnus_set()
    ts_id = ts["id"] if ts else "none"
    # Bypass cache when there are pending flash messages so they are never
    # baked into the stored HTML and re-shown on subsequent visits.
    if session.get("_flashes"):
        return f"view/turnusliste/{current_user.get_id()}/{ts_id}/flash/{uuid.uuid4()}"
    return f"view/turnusliste/{current_user.get_id()}/{ts_id}"


@shifts.route("/turnusliste")
@login_required
@cache.cached(timeout=120, key_prefix=_turnusliste_cache_key)
def turnusliste():
    # Get the turnus set for this user (their choice or system default)
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None
    active_set = db_utils.get_active_turnus_set()

    # Get favorites for current user and active turnus set
    favoritt = (
        db_utils.get_favorite_lst(current_user.get_id(), turnus_set_id)
        if current_user.is_authenticated
        else []
    )

    # Create a position lookup dictionary for robust favorite numbering
    favorite_positions = {name: idx + 1 for idx, name in enumerate(favoritt)}

    # Load data for user's selected year
    user_df_manager = df_utils.DataframeManager(turnus_set_id)

    # Get turnus parameter for highlighting specific turnus
    highlighted_turnus = request.args.get("turnus")

    df_records = (
        user_df_manager.df.to_dict(orient="records")
        if not user_df_manager.df.empty
        else []
    )
    komp = count_kompdager(turnus_set_id) or {}
    for row in df_records:
        row["kompdager_max"] = kompdager_max_label(komp.get(row["turnus"]))

    return render_template(
        "turnusliste.html",
        page_name="Turnusliste",
        table_data=user_df_manager.turnus_data,
        df=df_records,
        favoritt=favoritt,
        favorite_positions=favorite_positions,
        current_turnus_set=user_turnus_set,
        active_set=active_set,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
        highlighted_turnus=highlighted_turnus,
    )


@shifts.route("/switch-year/<int:turnus_set_id>")
@login_required
def switch_user_year(turnus_set_id):
    """Allow user to switch which year they're viewing (stored in session)"""
    # Invalidate cached page for the previous turnus set before switching
    from app.routes.shifts.oversikt import _oversikt_cache_key
    cache.delete(_turnusliste_cache_key())
    cache.delete(_oversikt_cache_key())
    # Store user's choice in their session
    session["user_selected_turnus_set"] = turnus_set_id

    # Get the referring page (where user came from)
    next_page = request.args.get("next") or request.referrer

    # If no referrer or if it's the same switch route, default to turnusliste
    if not next_page or "/switch-year/" in next_page:
        next_page = url_for("shifts.turnusliste")

    return redirect(next_page)
