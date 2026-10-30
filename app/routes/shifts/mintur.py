from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.routes.shifts import _classify_shift_type, shifts
from app.services.innplassering_service import get_innplassering_for_user
from app.utils import df_utils, turnuskalender
from app.utils.kompdag_utils import count_kompdager, get_holidays_for_dates


def _pick_record(records: list[dict], turnus_set_id: int | None = None) -> dict | None:
    """The innplassering to show: the requested set if the driver is placed
    in it, else the newest set they are placed in.

    Mintur follows the driver's placements, not the active set. Around a
    rutetermin change that means the old set stays until the new
    innplassering is imported, after which the new set is the default and
    the old one is still viewable.
    """
    if not records:
        return None
    if turnus_set_id is not None:
        for record in records:
            if record["turnus_set_id"] == turnus_set_id:
                return record
    return max(records, key=lambda r: r["turnus_set_id"])


def _load_mintur_data(user_id: int, turnus_set_id: int | None = None) -> dict | None:
    """Load all data needed by both mintur() and export_ical().

    Returns a dict with keys: shift_title, linjenummer, year_identifier,
    turnus_set_id, turnus_set, available_sets, groups, template_found, raw, dm.
    Returns None if the user has no innplassering at all.

    Each cell dict in groups includes a 'tid' key (raw ["HH:MM","HH:MM"] list).
    Each date dict in groups includes a 'date_obj' key (Python date or None).
    """
    records = get_innplassering_for_user(user_id)
    user_record = _pick_record(records, turnus_set_id)
    if not user_record:
        return None

    shift_title = user_record["shift_title"]
    linjenummer = user_record["linjenummer"]
    turnus_set_id = user_record["turnus_set_id"]
    year_identifier = user_record["year_identifier"]
    turnus_set = {"id": turnus_set_id, "year_identifier": year_identifier}
    available_sets = [
        {"id": r["turnus_set_id"], "year_identifier": r["year_identifier"]}
        for r in sorted(records, key=lambda r: r["turnus_set_id"], reverse=True)
    ]

    dm = df_utils.DataframeManager(turnus_set_id)
    raw = next((t[shift_title] for t in dm.turnus_data if shift_title in t), None)
    if not raw:
        return None

    linje_shifts = {}
    for uke_nr, ukedata in sorted(
        [(k, v) for k, v in raw.items() if isinstance(v, dict)],
        key=lambda x: int(x[0]),
    ):
        linje = int(uke_nr)
        linje_shifts[linje] = {}
        for dag_nr, dag_data in ukedata.items():
            if not isinstance(dag_data, dict):
                continue
            tid = dag_data.get("tid", [])
            value = (
                f"{tid[0]} - {tid[1]}" if len(tid) >= 2 else (tid[0] if tid else "")
            )
            linje_shifts[linje][int(dag_nr)] = {
                "value": value,
                "dagsverk": dag_data.get("dagsverk", ""),
                "tid": tid,
            }

    dag_names = ["Man", "Tirs", "Ons", "Tors", "Fre", "Lør", "Søn"]
    all_rows = turnuskalender.load_nokkel_rows(year_identifier)
    template_found = all_rows is not None
    groups = []

    _empty_cell = {"value": "", "dagsverk": "", "tid": []}

    def _cells_for(g, d):
        """The six linje columns of one weekday row, in linje order."""
        return [
            linje_shifts.get(turnuskalender.rotation_week(g, j), {}).get(
                d + 1, _empty_cell
            )
            for j in range(1, 7)
        ]

    if template_found:
        # Holiday flag comes from the computed §5.13.1 set (multi-year, since
        # a turnus year spans two calendar years), not the manual red font.
        holiday_set = get_holidays_for_dates(
            list(turnuskalender.build_date_index(rows=all_rows))
        )
        columns = turnuskalender.grid_columns(all_rows)

        for g in range(turnuskalender.NOKKEL_GROUPS):
            day_rows = []
            for d in range(turnuskalender.DAYS_PER_WEEK):
                dates = []
                row = all_rows[g * turnuskalender.ROWS_PER_GROUP + 1 + d]
                for c in row[columns]:
                    cal_date = turnuskalender.cell_date(c)
                    if cal_date is None:
                        dates.append({"value": "", "holiday": False, "date_obj": None})
                    else:
                        dates.append(
                            {
                                "value": c.value.strftime("%d.%m.%y"),
                                "holiday": cal_date in holiday_set,
                                "date_obj": c.value,
                            }
                        )
                day_rows.append(
                    {"name": dag_names[d], "cells": _cells_for(g, d), "dates": dates}
                )
            groups.append(
                {
                    "uke_labels": turnuskalender.week_labels(all_rows, g),
                    "day_rows": day_rows,
                }
            )
    else:
        for g in range(turnuskalender.NOKKEL_GROUPS):
            day_rows = [
                {"name": dag_names[d], "cells": _cells_for(g, d), "dates": []}
                for d in range(turnuskalender.DAYS_PER_WEEK)
            ]
            groups.append(
                {
                    "uke_labels": [f"Linje {g + 1}"],
                    "day_rows": day_rows,
                }
            )

    return {
        "shift_title": shift_title,
        "linjenummer": linjenummer,
        "year_identifier": year_identifier,
        "turnus_set_id": turnus_set_id,
        "turnus_set": turnus_set,
        "available_sets": available_sets,
        "groups": groups,
        "template_found": template_found,
        "raw": raw,
        "dm": dm,
    }


@shifts.route("/mintur")
@login_required
def mintur():
    data = _load_mintur_data(
        int(current_user.get_id()), turnus_set_id=request.args.get("sett", type=int)
    )
    if not data:
        return redirect(url_for("shifts.turnusliste"))

    linje_labels = ["Linje 1", "Linje 2", "Linje 3", "Linje 4", "Linje 5", "Linje 6"]
    df_records = (
        data["dm"].df.to_dict(orient="records") if not data["dm"].df.empty else []
    )
    df_row = next(
        (r for r in df_records if r.get("turnus") == data["shift_title"]), None
    )

    komp = count_kompdager(data["turnus_set_id"])
    counts = komp.get(data["shift_title"]) if komp else None
    linjenummer = data["linjenummer"]  # nullable in the DB — guard the indexing
    kompdager = (
        counts[linjenummer - 1]
        if counts and linjenummer and 1 <= linjenummer <= len(counts)
        else None
    )

    return render_template(
        "mintur.html",
        page_name="Min Turnus",
        shift_title=data["shift_title"],
        linjenummer=data["linjenummer"],
        turnus_data={data["shift_title"]: data["raw"]},
        df_row=df_row,
        kompdager=kompdager,
        linje_labels=linje_labels,
        groups=data["groups"],
        template_found=data["template_found"],
        year_identifier=data["year_identifier"],
        turnus_set_id=data["turnus_set_id"],
        turnus_set=data["turnus_set"],
        available_sets=data["available_sets"],
        current_turnus_set=data["turnus_set"],
        all_turnus_sets=[],
    )


@shifts.route("/mintur/export_ical")
@login_required
def export_ical():
    from datetime import datetime, timedelta

    import pytz
    from icalendar import Calendar, Event

    mode = request.args.get("mode", "fixed")
    label = request.args.get("label", "Jobb")

    data = _load_mintur_data(
        int(current_user.get_id()), turnus_set_id=request.args.get("sett", type=int)
    )
    if not data:
        from flask import jsonify

        return jsonify({"error": "Ingen turnusdata funnet"}), 404
    if not data["template_found"]:
        from flask import jsonify

        return jsonify({"error": "Turnusnøkkel-mal ikke funnet for dette året"}), 404

    _COLORS = {
        "Tidlig": "#4986E7",
        "Dag": "#33B679",
        "Ettermiddag": "#F6BF26",
        "Natt": "#616161",
    }

    oslo = pytz.timezone("Europe/Oslo")
    cal = Calendar()
    cal.add("prodid", "-//Turnushjelper//NO")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "Turnus")
    cal.add("x-wr-timezone", "Europe/Oslo")

    linjenummer = data["linjenummer"]
    shift_title = data["shift_title"]

    # linjenummer is nullable in the DB and indexes a 6-element cells list
    if not linjenummer or not 1 <= linjenummer <= 6:
        from flask import jsonify

        return jsonify({"error": "Ugyldig linjenummer i innplasseringen"}), 404

    emitted_uids: set[str] = set()

    for group in data["groups"]:
        for day_row in group["day_rows"]:
            cell = day_row["cells"][linjenummer - 1]
            tid = cell.get("tid", [])
            if len(tid) < 2:
                continue

            start_str, end_str = tid[0], tid[1]
            sh, sm = (int(x) for x in start_str.split(":"))
            eh, em = (int(x) for x in end_str.split(":"))
            overnight = (eh * 60 + em) < (sh * 60 + sm)

            for date_entry in day_row["dates"]:
                date_obj = date_entry.get("date_obj")
                if not date_obj:
                    continue

                work_date = date_obj.date() if hasattr(date_obj, "date") else date_obj
                end_date = work_date + timedelta(days=1) if overnight else work_date

                uid = f"{shift_title}-{work_date.strftime('%Y%m%d')}@turnushjelper"
                if uid in emitted_uids:
                    continue
                emitted_uids.add(uid)

                start_dt = oslo.localize(
                    datetime(work_date.year, work_date.month, work_date.day, sh, sm),
                    is_dst=False,
                )
                end_dt = oslo.localize(
                    datetime(end_date.year, end_date.month, end_date.day, eh, em),
                    is_dst=False,
                )

                if mode == "auto":
                    shift_type = _classify_shift_type(start_str, end_str)
                    summary = f"{label}: {shift_type}"
                    color = _COLORS.get(shift_type)
                else:
                    summary = label
                    color = None

                event = Event()
                event.add("summary", summary)
                event.add("dtstart", start_dt)
                event.add("dtend", end_dt)
                event.add("uid", uid)
                if color:
                    event.add("color", color)
                cal.add_component(event)

    filename = f"turnusplan_{data['year_identifier'].lower()}.ics"
    from flask import current_app

    return current_app.response_class(
        cal.to_ical(),
        mimetype="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
