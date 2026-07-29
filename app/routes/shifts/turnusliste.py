from flask import redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.routes.shifts import shifts
from app.services import favorites_service, turnus_service
from app.utils import df_utils
from app.utils.kompdag_utils import count_kompdager, kompdager_max_label
from app.utils.turnus_helpers import get_user_turnus_set


# This page is rendered fresh on every request. It used to be cached per user
# for 120 s, which cost two stale-favorites bugs, a query-string key collision
# and four invalidation mechanisms, to save the ~33 ms this render takes while
# storing a ~3.7 MiB entry per user per worker. The shared turnus_data_* /
# kompdager_* caches (which do the expensive work) are untouched.
@shifts.route("/turnusliste")
@login_required
def turnusliste():
    # Get the turnus set for this user (their choice or system default)
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None
    active_set = turnus_service.get_active_turnus_set()

    # Get favorites for current user and active turnus set
    favoritt = (
        favorites_service.get_favorite_lst(current_user.get_id(), turnus_set_id)
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
        all_turnus_sets=turnus_service.get_all_turnus_sets(),
        highlighted_turnus=highlighted_turnus,
    )


@shifts.route("/switch-year/<int:turnus_set_id>")
@login_required
def switch_user_year(turnus_set_id):
    """Allow user to switch which year they're viewing (stored in session)"""
    # Store user's choice in their session
    session["user_selected_turnus_set"] = turnus_set_id

    # Get the referring page (where user came from)
    next_page = request.args.get("next") or request.referrer

    # Only follow same-host targets — prevents open redirect via ?next=
    if next_page:
        from urllib.parse import urljoin, urlparse

        target = urlparse(urljoin(request.host_url, next_page))
        if target.scheme not in ("http", "https") or target.netloc != urlparse(
            request.host_url
        ).netloc:
            next_page = None

    # If no referrer or if it's the same switch route, default to turnusliste
    if not next_page or "/switch-year/" in next_page:
        next_page = url_for("shifts.turnusliste")

    return redirect(next_page)
