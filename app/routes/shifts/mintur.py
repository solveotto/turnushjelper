from flask import redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.routes.shifts import _classify_shift_type, shifts
from app.services.innplassering_service import get_innplassering_for_user
from app.utils import db_utils, df_utils
from app.utils.kompdag_utils import count_kompdager, get_holidays_for_dates


def _load_mintur_data(user_id: int) -> dict | None:
    """Load all data needed by both mintur() and export_ical().

    Returns a dict with keys: shift_title, linjenummer, year_identifier,
    turnus_set_id, active_set, groups, template_found, raw, dm.
    Returns None if the user has no innplassering or no active turnus set.

    Each cell dict in groups includes a 'tid' key (raw ["HH:MM","HH:MM"] list).
    Each date dict in groups includes a 'date_obj' key (Python date or None).
    """
    import os

    import openpyxl

    from config import AppConfig

    active_set = db_utils.get_active_turnus_set()
    records = get_innplassering_for_user(user_id)
    if not records or not active_set:
        return None

    user_record = next(
        (r for r in records if r["turnus_set_id"] == active_set["id"]), None
    )
    if not user_record:
        return None

    shift_title = user_record["shift_title"]
    linjenummer = user_record["linjenummer"]
    turnus_set_id = active_set["id"]
    year_identifier = active_set["year_identifier"]

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
    template_path = os.path.join(
        AppConfig.turnusfiler_dir,
        year_identifier.lower(),
        f"turnusnøkkel_{year_identifier}_org.xlsx",
    )
    template_found = os.path.exists(template_path)
    groups = []

    _empty_cell = {"value": "", "dagsverk": "", "tid": []}

    if template_found:
        wb = openpyxl.load_workbook(template_path, data_only=True)
        sheet = wb["Turnusnøkkel"]
        all_rows = [list(row) for row in sheet.iter_rows(min_row=1, max_row=48)]
        wb.close()

        # Holiday flag comes from the computed §5.13.1 set (multi-year, since
        # a turnus year spans two calendar years), not the manual red font.
        all_dates = [
            c.value.date() if hasattr(c.value, "date") else c.value
            for row in all_rows
            for c in row[7:16]
            if c.value is not None and hasattr(c.value, "strftime")
        ]
        holiday_set = get_holidays_for_dates(all_dates)

        for g in range(6):
            uke_labels = [
                str(c.value) for c in all_rows[g * 8][7:16] if c.value is not None
            ]
            day_rows = []
            for d in range(7):
                cells = [
                    linje_shifts.get((g + j - 1) % 6 + 1, {}).get(d + 1, _empty_cell)
                    for j in range(1, 7)
                ]
                dates = []
                for c in all_rows[g * 8 + 1 + d][7:16]:
                    if c.value is not None and hasattr(c.value, "strftime"):
                        cal_date = (
                            c.value.date() if hasattr(c.value, "date") else c.value
                        )
                        dates.append(
                            {
                                "value": c.value.strftime("%d.%m.%y"),
                                "holiday": cal_date in holiday_set,
                                "date_obj": c.value,
                            }
                        )
                    else:
                        dates.append({"value": "", "holiday": False, "date_obj": None})
                day_rows.append({"name": dag_names[d], "cells": cells, "dates": dates})
            groups.append({"uke_labels": uke_labels, "day_rows": day_rows})
    else:
        for g in range(6):
            day_rows = [
                {
                    "name": dag_names[d],
                    "cells": [
                        linje_shifts.get((g + j - 1) % 6 + 1, {}).get(
                            d + 1, _empty_cell
                        )
                        for j in range(1, 7)
                    ],
                    "dates": [],
                }
                for d in range(7)
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
        "active_set": active_set,
        "groups": groups,
        "template_found": template_found,
        "raw": raw,
        "dm": dm,
    }


@shifts.route("/mintur")
@login_required
def mintur():
    data = _load_mintur_data(int(current_user.get_id()))
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
    kompdager = counts[data["linjenummer"] - 1] if counts else None

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
        active_set=data["active_set"],
        current_turnus_set=data["active_set"],
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

    data = _load_mintur_data(int(current_user.get_id()))
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
