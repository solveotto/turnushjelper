from flask import abort, render_template
from flask_login import current_user, login_required

from app.database import get_db_session
from app.models import SoknadsskjemaChoice
from app.routes.shifts import shifts
from app.utils import db_utils, df_utils
from app.utils.kompdag_utils import count_kompdager, get_holidays_for_dates


@shifts.route("/turnusnokkel/<int:turnus_set_id>/<turnus_name>")
@login_required
def turnusnokkel_view(turnus_set_id, turnus_name):
    import os

    import openpyxl

    from config import AppConfig

    turnus_set = db_utils.get_turnus_set_by_id(turnus_set_id)
    if not turnus_set:
        abort(404)
    year_identifier = turnus_set["year_identifier"]
    df_manager = df_utils.DataframeManager(turnus_set_id)

    # Build linje_shifts[linje_nr (1-6)][dag_nr (1-7)] = time_string
    linje_shifts = {}
    for t in df_manager.turnus_data:
        if turnus_name not in t:
            continue
        target_data = t[turnus_name]
        week_items = [(k, v) for k, v in target_data.items() if isinstance(v, dict)]
        for uke_nr, ukedata in sorted(week_items, key=lambda x: int(x[0])):
            linje = int(uke_nr)
            linje_shifts[linje] = {}
            for dag_nr, dag_data in ukedata.items():
                if not isinstance(dag_data, dict):
                    continue
                tid = dag_data.get("tid", [])
                if len(tid) >= 2:
                    value = f"{tid[0]} - {tid[1]}"
                elif tid:
                    value = tid[0]
                else:
                    value = ""
                linje_shifts[linje][int(dag_nr)] = {
                    "value": value,
                    "dagsverk": dag_data.get("dagsverk", ""),
                }
        break

    dag_names = ["Man", "Tirs", "Ons", "Tors", "Fre", "Lør", "Søn"]
    linje_labels = ["Linje 1", "Linje 2", "Linje 3", "Linje 4", "Linje 5", "Linje 6"]

    # Read template to get calendar week labels for each of the 6 rotation groups.
    # The template has 6 groups of 8 rows (1 header + 7 day rows).
    # Each group header has Uke labels in columns H–P (0-indexed 7–15).
    # For group g (0-indexed), Linje column j (1-indexed):
    #   shift data comes from Linje ((g + j - 1) % 6 + 1).
    template_path = os.path.join(
        AppConfig.turnusfiler_dir,
        year_identifier.lower(),
        f"turnusnøkkel_{year_identifier}_org.xlsx",
    )
    groups = []
    template_found = os.path.exists(template_path)

    if template_found:
        wb = openpyxl.load_workbook(template_path, data_only=True)
        sheet = wb["Turnusnøkkel"]
        all_rows = [list(row) for row in sheet.iter_rows(min_row=1, max_row=48)]
        wb.close()

        # Holiday flag comes from the computed §5.13.1 set, not the manual
        # red font in the template (which misses e.g. påskeaften and Sunday
        # holidays). A turnus year spans two calendar years, so the set is
        # unioned across all years present in the template dates.
        all_dates = [
            cell.value.date() if hasattr(cell.value, "date") else cell.value
            for row in all_rows
            for cell in row[7:16]
            if cell.value is not None and hasattr(cell.value, "strftime")
        ]
        holiday_set = get_holidays_for_dates(all_dates)

        for g in range(6):
            header_cells = all_rows[g * 8]
            uke_labels = [
                str(c.value) for c in header_cells[7:16] if c.value is not None
            ]
            day_rows = []
            for d in range(7):
                _empty = {"value": "", "dagsverk": ""}
                cells = []
                for j in range(1, 7):
                    linje_idx = (g + j - 1) % 6 + 1
                    cells.append(linje_shifts.get(linje_idx, {}).get(d + 1, _empty))
                dates = []
                for cell in all_rows[g * 8 + 1 + d][7:16]:
                    if cell.value is not None and hasattr(cell.value, "strftime"):
                        cell_date = (
                            cell.value.date()
                            if hasattr(cell.value, "date")
                            else cell.value
                        )
                        dates.append(
                            {
                                "value": cell.value.strftime("%d.%m.%y"),
                                "holiday": cell_date in holiday_set,
                            }
                        )
                    else:
                        dates.append({"value": "", "holiday": False})
                day_rows.append({"name": dag_names[d], "cells": cells, "dates": dates})
            groups.append({"uke_labels": uke_labels, "day_rows": day_rows})
    else:
        # Fallback: simple 6×7 table without calendar mapping
        for g in range(6):
            day_rows = []
            for d in range(7):
                _empty = {"value": "", "dagsverk": ""}
                cells = [linje_shifts.get(g + 1, {}).get(d + 1, _empty)] + [_empty] * 5
                day_rows.append(
                    {
                        "name": dag_names[d],
                        "cells": cells,
                        "dates": [],
                        "is_saturday": d == 5,
                        "is_sunday": d == 6,
                    }
                )
            groups.append({"uke_labels": [f"Linje {g + 1}"], "day_rows": day_rows})

    komp = count_kompdager(turnus_set_id)
    kompdager = komp.get(turnus_name) if komp else None

    pref_db = get_db_session()
    try:
        pref_row = (
            pref_db.query(SoknadsskjemaChoice)
            .filter_by(
                user_id=int(current_user.get_id()),
                turnus_set_id=turnus_set_id,
                shift_title=turnus_name,
            )
            .first()
        )
        linjeprioritering_current = pref_row.linjeprioritering if pref_row else ""
    finally:
        pref_db.close()

    return render_template(
        "turnusnokkel_print.html",
        turnus_name=turnus_name,
        year_identifier=year_identifier,
        turnus_set_id=turnus_set_id,
        linje_labels=linje_labels,
        groups=groups,
        template_found=template_found,
        kompdager=kompdager,
        linjeprioritering_current=linjeprioritering_current or "",
    )
