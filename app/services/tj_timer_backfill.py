"""Add the per-shift Tj.t to a stored turnus schedule, and nothing else.

Existing sets were imported before the parser kept this value. Admin "Oppdater"
would add it too, but it also rewrites the stats, can rename shifts, deletes
favorites and søknadsskjema choices on titles missing from the new file, and
strips the dagsverk suffixes if the PDF is missing. This does none of that.

It has no database connection, and the schedule file is the only existing file
it replaces. A dry run is the default. Any mismatch between the stored schedule
and the Timeskjema means nothing is written.
"""

import json
import os
import shutil
import stat
import tempfile
from datetime import datetime

from app.utils.timeskjema_parser import TimeskjemaParseError, parse_timeskjema
from app.utils.turnus_diff import duty_id
from config import AppConfig


def _as_map(turnuser):
    return {name: turnus for entry in turnuser for name, turnus in entry.items()}


def _with_tj_timer(cell, value):
    """A copy of the cell with the key right after dagsverk, so the stored file
    only gains lines."""
    updated = {}
    for key, existing in cell.items():
        updated[key] = existing
        if key == "dagsverk":
            updated["tj_timer"] = value
    return updated


def _fill(stored, parsed):
    """Returns (problems, cells filled, the schedule with the values added)."""
    problems = []
    filled = 0
    stored_map = _as_map(stored)
    parsed_map = _as_map(parsed)

    for name in sorted(set(stored_map) - set(parsed_map)):
        problems.append(f"{name}: finnes i lagret turnus, ikke i timeskjemaet")
    for name in sorted(set(parsed_map) - set(stored_map)):
        problems.append(f"{name}: finnes i timeskjemaet, ikke i lagret turnus")

    for name in sorted(set(stored_map) & set(parsed_map)):
        stored_tur = stored_map[name]
        parsed_tur = parsed_map[name]
        for total in ("kl_timer", "tj_timer"):
            if stored_tur.get(total) != parsed_tur.get(total):
                problems.append(
                    f"{name}: {total} er {stored_tur.get(total)} i lagret turnus, "
                    f"{parsed_tur.get(total)} i timeskjemaet"
                )
        for uke in map(str, range(1, 7)):
            for dag in map(str, range(1, 8)):
                where = f"{name} uke {uke} dag {dag}"
                cell = stored_tur.get(uke, {}).get(dag)
                source = parsed_tur[uke][dag]
                if not isinstance(cell, dict) or "dagsverk" not in cell:
                    problems.append(f"{where}: mangler i lagret turnus")
                elif cell.get("tid") != source["tid"]:
                    problems.append(
                        f"{where}: tid er {cell.get('tid')} i lagret turnus, "
                        f"{source['tid']} i timeskjemaet"
                    )
                elif duty_id(cell["dagsverk"]) != duty_id(source["dagsverk"]):
                    problems.append(
                        f"{where}: dagsverk er {cell['dagsverk']} i lagret turnus, "
                        f"{source['dagsverk']} i timeskjemaet"
                    )
                elif "tj_timer" not in cell:
                    stored_tur[uke][dag] = _with_tj_timer(cell, source["tj_timer"])
                    filled += 1
                elif cell["tj_timer"] != source["tj_timer"]:
                    problems.append(
                        f"{where}: tj_timer er {cell['tj_timer']} i lagret turnus, "
                        f"{source['tj_timer']} i timeskjemaet"
                    )
    return problems, filled, stored


def _without_tj_timer(turnuser):
    copied = json.loads(json.dumps(turnuser))
    for turnus in _as_map(copied).values():
        for week in turnus.values():
            if isinstance(week, dict):
                for cell in week.values():
                    cell.pop("tj_timer", None)
    return copied


def _replace_file(path, text):
    """Readers see the old file or the new one, never half of it. The new file
    keeps the group and permissions, or the app could lose its read access."""
    original = os.stat(path)
    handle, temp_path = tempfile.mkstemp(
        dir=os.path.dirname(path), prefix=".turnus_schedule_", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chown(temp_path, -1, original.st_gid)
        os.chmod(temp_path, stat.S_IMODE(original.st_mode))
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def backfill(year_id, write=False):
    """Returns a dict: problems (a list, empty when clean), cells_to_fill,
    written and backup. Nothing is written unless ``write`` is set and there are
    no problems."""
    year = year_id.upper()
    version = year.lower()
    directory = os.path.join(AppConfig.turnusfiler_dir, version)
    timeskjema_path = os.path.join(directory, f"turnuser_{year}.xls")
    schedule_path = os.path.join(directory, f"turnus_schedule_{year}.json")
    double_shifts_path = os.path.join(directory, f"double_shifts_{version}.json")
    result = {"problems": [], "cells_to_fill": 0, "written": False, "backup": None}

    for path in (timeskjema_path, schedule_path, double_shifts_path):
        if not os.path.exists(path):
            result["problems"].append(f"Mangler {os.path.basename(path)}")
    if result["problems"]:
        return result

    # Same user as the app, so a replaced file keeps its owner.
    if os.stat(schedule_path).st_uid != os.getuid():
        result["problems"].append(
            f"{os.path.basename(schedule_path)} eies av en annen bruker. "
            "Kjør som brukeren appen kjører som."
        )
        return result

    try:
        parsed = json.loads(json.dumps(parse_timeskjema(timeskjema_path).turnuser))
    except TimeskjemaParseError as e:
        result["problems"].extend(e.errors)
        return result

    try:
        with open(schedule_path, encoding="utf-8") as f:
            stored = json.load(f)
    except ValueError as e:
        result["problems"].append(f"Kan ikke lese {os.path.basename(schedule_path)}: {e}")
        return result

    problems, filled, updated = _fill(json.loads(json.dumps(stored)), parsed)
    result["problems"].extend(problems)
    if problems:
        return result
    result["cells_to_fill"] = filled
    if filled == 0 or not write:
        return result

    if _without_tj_timer(updated) != _without_tj_timer(stored):
        result["problems"].append("Kontrollen feilet: noe annet enn tj_timer ville endret seg")
        return result

    backup_path = f"{schedule_path}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    try:
        shutil.copy2(schedule_path, backup_path)
        _replace_file(schedule_path, json.dumps(updated, indent=4))
    except OSError as e:
        if os.path.exists(backup_path):
            os.unlink(backup_path)
        result["problems"].append(f"Kunne ikke skrive, filen er uendret: {e}")
        return result

    result["written"] = True
    result["backup"] = backup_path
    return result
