from flask import render_template
from flask_login import current_user, login_required

from app.routes.shifts import shifts
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set


@shifts.route("/favorites")
@login_required
def favorites():
    # Get user's selected turnus set (same logic as turnusliste)
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None
    active_set = db_utils.get_active_turnus_set()

    # Get favorites for the user's selected turnus set
    fav_order_lst = db_utils.get_favorite_lst(current_user.get_id(), turnus_set_id)
    fav_set = set(fav_order_lst)

    # Load data for the user's selected turnus set
    user_df_manager = df_utils.DataframeManager(turnus_set_id)

    fav_dict_lookup = {}

    # Use the user's selected turnus data, not global data
    for x in user_df_manager.turnus_data:
        for name, data in x.items():
            if name in fav_set:
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


@shifts.route("/import-favorites")
@login_required
def import_favorites():
    """Page for importing favorites from previous turnus years based on shift statistics."""
    from app.services.innplassering_service import get_innplassering_for_user
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

    # When no previous-year favorites exist, fall back to innplassering data
    innplassering_sources = []
    if not available_sources:
        user_records = get_innplassering_for_user(user_id)
        seen_ts_ids = set()
        for rec in user_records:
            ts_id = rec["turnus_set_id"]
            if ts_id == turnus_set_id or ts_id in seen_ts_ids:
                continue
            ts_stats = shift_matcher.load_stats_for_turnus_set(ts_id)
            if ts_stats is not None:
                seen_ts_ids.add(ts_id)
                innplassering_sources.append(rec)

    return render_template(
        "import_favorites.html",
        page_name="Importer Favoritter",
        current_turnus_set=user_turnus_set,
        available_sources=available_sources,
        innplassering_sources=innplassering_sources,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
    )
