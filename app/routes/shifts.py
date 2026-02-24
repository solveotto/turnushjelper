from flask import Blueprint, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.extensions import cache
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set


def _turnusliste_cache_key():
    """Per-user, per-turnus-set cache key for the /turnusliste response."""
    ts = get_user_turnus_set()
    ts_id = ts['id'] if ts else 'none'
    return f"view/turnusliste/{current_user.get_id()}/{ts_id}"

shifts = Blueprint("shifts", __name__)


@shifts.route("/")
@login_required
def index():
    return redirect(url_for("shifts.turnusliste"))


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

    return render_template(
        "turnusliste.html",
        page_name="Turnusliste",
        table_data=user_df_manager.turnus_data,
        df=user_df_manager.df.to_dict(orient="records")
        if not user_df_manager.df.empty
        else [],
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
    cache.delete(_turnusliste_cache_key())
    # Store user's choice in their session
    session["user_selected_turnus_set"] = turnus_set_id

    # Get the referring page (where user came from)
    next_page = request.args.get("next") or request.referrer

    # If no referrer or if it's the same switch route, default to turnusliste
    if not next_page or "/switch-year/" in next_page:
        next_page = url_for("shifts.turnusliste")

    return redirect(next_page)


@shifts.route("/favorites")
@login_required
def favorites():
    # Get user's selected turnus set (same logic as turnusliste)
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None
    active_set = db_utils.get_active_turnus_set()

    # Get favorites for the user's selected turnus set
    fav_order_lst = db_utils.get_favorite_lst(current_user.get_id(), turnus_set_id)

    # Load data for the user's selected turnus set
    user_df_manager = df_utils.DataframeManager(turnus_set_id)

    fav_dict_lookup = {}

    # Use the user's selected turnus data, not global data
    for x in user_df_manager.turnus_data:
        for name, data in x.items():
            if name in fav_order_lst:
                fav_dict_lookup[name] = data
    fav_dict_sorted = [
        {name: fav_dict_lookup[name]}
        for name in fav_order_lst
        if name in fav_dict_lookup
    ]

    return render_template(
        "favorites.html",
        page_name="Favoritter",
        favorites=fav_dict_sorted,
        df=user_df_manager.df.to_dict(orient="records")
        if not user_df_manager.df.empty
        else [],
        current_turnus_set=user_turnus_set,
        active_set=active_set,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
    )


@shifts.route("/compare")
@login_required
def compare():
    # Get user's selected turnus set
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

    # Load data for user's selected year
    user_df_manager = df_utils.DataframeManager(turnus_set_id)

    # Prepare metrics for charts
    df = user_df_manager.df
    metrics = ["natt", "tidlig", "shift_cnt", "before_6", "helgetimer",
               "tidlig_6_8", "tidlig_8_12", "longest_off_streak", "longest_work_streak", "avg_shift_hours"]
    labels = df["turnus"].tolist() if not df.empty else []
    data = {m: df[m].tolist() if m in df else [] for m in metrics}

    return render_template(
        "compare.html",
        page_name="Sammenlign Turnuser",
        labels=labels,
        data=data,
        current_turnus_set=user_turnus_set,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
    )


@shifts.route("/import-favorites")
@login_required
def import_favorites():
    """Page for importing favorites from previous turnus years based on shift statistics."""
    from app.utils import shift_matcher

    # Get user's current turnus set
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

    # Get turnus sets where user has favorites
    user_id = current_user.get_id()
    sets_with_stats = shift_matcher.get_all_turnus_sets_with_stats()

    available_sources = []
    for ts in sets_with_stats:
        if ts["id"] == turnus_set_id:
            continue
        favorites = db_utils.get_favorite_lst(user_id, ts["id"])
        if favorites:
            ts["favorite_count"] = len(favorites)
            available_sources.append(ts)

    return render_template(
        "import_favorites.html",
        page_name="Importer Favoritter",
        current_turnus_set=user_turnus_set,
        available_sources=available_sources,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
    )
