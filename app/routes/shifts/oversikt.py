import uuid

from flask import render_template, session
from flask_login import current_user, login_required

from app.extensions import cache
from app.routes.shifts import shifts
from app.services.innplassering_service import get_innplassering_for_user
from app.utils import db_utils, df_utils
from app.utils.turnus_helpers import get_user_turnus_set, iter_turnus_days


def _oversikt_cache_key():
    """Per-user, per-turnus-set cache key for the /oversikt response."""
    ts = get_user_turnus_set()
    ts_id = ts["id"] if ts else "none"
    if session.get("_flashes"):
        return f"view/oversikt/{current_user.get_id()}/{ts_id}/flash/{uuid.uuid4()}"
    return f"view/oversikt/{current_user.get_id()}/{ts_id}"


@shifts.route("/oversikt")
@login_required
@cache.cached(timeout=300, key_prefix=_oversikt_cache_key)
def oversikt():
    # Get user's selected turnus set
    user_turnus_set = get_user_turnus_set()
    turnus_set_id = user_turnus_set["id"] if user_turnus_set else None

    # Load data for user's selected year
    user_df_manager = df_utils.DataframeManager(turnus_set_id)

    # Prepare metrics for charts
    df = user_df_manager.df
    metrics = [
        "natt",
        "tidlig",
        "ettermiddag",
        "shift_cnt",
        "before_6",
        "helgetimer",
        "helgedager",
        "natt_helg",
        "helgetimer_dagtid",
        "helgetimer_ettermiddag",
        "tidlig_6_8",
        "tidlig_8_12",
        "longest_off_streak",
        "longest_work_streak",
        "avg_shift_hours",
        "afternoons_in_row",
    ]
    labels = df["turnus"].tolist() if not df.empty else []
    data = {m: df[m].tolist() if m in df.columns else [] for m in metrics}

    # Load current user's favorites for the star button in the modal
    fav_order_lst = db_utils.get_favorite_lst(current_user.get_id(), turnus_set_id)

    # Compute weekday free-day counts and compact schedule — single pass over turnus_data
    _day_names = [
        "Mandag",
        "Tirsdag",
        "Onsdag",
        "Torsdag",
        "Fredag",
        "Lørdag",
        "Søndag",
    ]
    weekday_free: dict = {}
    schedule_data: dict = {}  # {turnus_name: {linje_str: {dag_str: {tid, dg}}}}
    for turnus_name, week_nr, day_nr, day_data in iter_turnus_days(
        user_df_manager.turnus_data
    ):
        # weekday free counts
        weekday_free.setdefault(turnus_name, {d: 0 for d in _day_names})
        tid = day_data.get("tid", [])
        if len(tid) != 2:  # not a shift day → free
            ukedag = day_data.get("ukedag", "")
            if ukedag in weekday_free[turnus_name]:
                weekday_free[turnus_name][ukedag] += 1

        # compact schedule for modal (linje 1-6, dag 1-7)
        try:
            linje = int(week_nr)
            dag = int(day_nr)
        except (ValueError, TypeError):
            continue
        schedule_data.setdefault(turnus_name, {})
        linje_key = str(linje)
        schedule_data[turnus_name].setdefault(linje_key, {})
        schedule_data[turnus_name][linje_key][str(dag)] = {
            "tid": f"{tid[0]}–{tid[1]}" if len(tid) == 2 else "",
            "dg": day_data.get("dagsverk") or "",  # may be None in JSON
        }

    # Load user's innplassering and schedule data for each referenced turnus set
    innplassering = get_innplassering_for_user(current_user.id)
    innplassering_schedules: dict = {}  # {turnus_set_id: {shift_title: {linje: {dag: {tid, dg}}}}}
    for row in innplassering:
        ts_id = row["turnus_set_id"]
        if ts_id in innplassering_schedules:
            continue
        ts_dm = df_utils.DataframeManager(ts_id)
        ts_sched: dict = {}
        for turnus_name, week_nr, day_nr, day_data in iter_turnus_days(
            ts_dm.turnus_data
        ):
            try:
                linje = int(week_nr)
                dag = int(day_nr)
            except (ValueError, TypeError):
                continue
            tid = day_data.get("tid", [])
            ts_sched.setdefault(turnus_name, {}).setdefault(str(linje), {})[
                str(dag)
            ] = {
                "tid": f"{tid[0]}–{tid[1]}" if len(tid) == 2 else "",
                "dg": day_data.get("dagsverk") or "",
            }
        innplassering_schedules[ts_id] = ts_sched

    return render_template(
        "oversikt.html",
        page_name="Sammenlign Turnuser",
        labels=labels,
        data=data,
        weekday_free=weekday_free,
        schedule_data=schedule_data,
        favoritt=fav_order_lst,
        current_turnus_set=user_turnus_set,
        all_turnus_sets=db_utils.get_all_turnus_sets(),
        innplassering=innplassering,
        innplassering_schedules=innplassering_schedules,
    )
