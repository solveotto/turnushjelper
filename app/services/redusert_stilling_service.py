"""A driver's plan for a reduced position: a percentage and the shifts to give up.

The plan belongs to one user, turnus set and tur, and never changes the turnus
data other drivers see. ``fjernet`` maps each removed ``"uke-dag"`` to its duty
number, and a removal only counts while that day still has the same duty, so a
re-import can't move a removal onto a shift the driver never chose.
"""

from app.database import get_db_session
from app.models import RedusertStilling
from app.utils.timeskjema_parser import _to_minutes
from app.utils.turnus_diff import duty_id

# NLF, 2026-11-03: a full position is 225 Tj.t whatever a tur adds up to, since no
# tur is quite full. Targets and percentages start from this.
FULL_POSITION_MINUTES = 225 * 60
# 80 % of a full position, the official limit. The panel warns below it, whatever
# target the driver typed.
LOWEST_POSITION_MINUTES = 180 * 60
# NLF, 2026-11-03: a weekend runs from Friday 17:00 to Monday 06:00, so a Monday
# shift starting at 05:something counts.
WEEKEND_START_MINUTES = 17 * 60
WEEKEND_END_MINUTES = 6 * 60


def _empty_plan():
    return {"prosent": None, "fjernet": {}, "h_dag_jobb": False}


def _as_plan(row):
    return {
        "prosent": row.prosent,
        "fjernet": dict(row.fjernet or {}),
        "h_dag_jobb": bool(row.h_dag_jobb),
    }


def _days(raw):
    """The rotation's days in order, as ("uke-dag", cell)."""
    days = []
    for uke in range(1, 7):
        week = raw.get(str(uke))
        if not isinstance(week, dict):
            continue
        for dag in range(1, 8):
            cell = week.get(str(dag))
            if isinstance(cell, dict):
                days.append((f"{uke}-{dag}", cell))
    return days


def _is_work(cell):
    return len(cell.get("tid") or []) == 2


def _is_h_dag(cell):
    """The rule classifyCell in shift-classifier.js colours them by. An H-dag
    isn't worked unless the driver ticks it, so it's never chosen like a shift."""
    return _is_work(cell) and str(cell.get("dagsverk") or "").strip().endswith("H")


def _format(minutes):
    return f"{minutes // 60}:{minutes % 60:02d}"


def has_per_shift_data(raw):
    """False for a set without ``tj_timer`` on its shifts, such as R25 or one
    last refreshed from the PDF. The feature is hidden there."""
    work = [cell for _, cell in _days(raw) if _is_work(cell)]
    return (
        bool(work)
        and bool(_to_minutes(raw.get("tj_timer")))
        and all(_to_minutes(cell.get("tj_timer")) for cell in work)
    )


def active_removals(raw, plan):
    """The removals that count, in rotation order. Everything that reads a plan
    goes through this."""
    if not has_per_shift_data(raw):
        return []
    fjernet = plan["fjernet"]
    return [
        key
        for key, cell in _days(raw)
        if _is_work(cell)
        and not _is_h_dag(cell)
        and key in fjernet
        and duty_id(cell.get("dagsverk")) == fjernet[key]
    ]


def _status(remaining, target):
    if target is None:
        return ""
    difference = remaining - target
    if difference > 0:
        return f"{_format(difference)} over målet"
    if difference < 0:
        return f"{_format(-difference)} under målet"
    return "På målet"


def _utelatt(count):
    if count == 0:
        return ""
    return f"{count} vakt er utelatt" if count == 1 else f"{count} vakter er utelatt"


def _has_weekend_hours(cells, not_worked, uke):
    """Whether a worked shift falls in the weekend at the end of rotation week
    ``uke``. Its Monday is the first day of the next week, and week 6 wraps to 1."""

    def worked(key):
        cell = cells.get(key)
        return cell if cell and _is_work(cell) and key not in not_worked else None

    if worked(f"{uke}-6") or worked(f"{uke}-7"):
        return True
    friday = worked(f"{uke}-5")
    if friday:
        start, end = (_to_minutes(time) for time in friday["tid"])
        if end > WEEKEND_START_MINUTES or end < start:
            return True
    monday = worked(f"{uke % 6 + 1}-1")
    return bool(monday) and _to_minutes(monday["tid"][0]) < WEEKEND_END_MINUTES


def _works_every_second_weekend(cells, not_worked):
    weekends = [_has_weekend_hours(cells, not_worked, uke) for uke in range(1, 7)]
    return all(weekends[0::2]) or all(weekends[1::2])


def _beregnet_prosent(remaining):
    """What the remaining hours come to, written as the field shows it: "95,4"."""
    return f"{round(remaining / FULL_POSITION_MINUTES * 100, 1):g}".replace(".", ",")


def summary(raw, plan):
    """The numbers and wording for the panel, shared by the page and the JSON
    response. ``target`` is None when the driver hasn't set a percentage.
    ``beregnet_prosent`` is only for display and is never saved, so it keeps
    following the driver's clicks."""
    if not has_per_shift_data(raw):
        return {
            "available": False,
            "prosent": None,
            "beregnet_prosent": "",
            "total": None,
            "target": None,
            "remaining": None,
            "fjernet": [],
            "h_dager": [],
            "h_fri": [],
            "h_dag_jobb": False,
            "helg_varsel": False,
            "under_varsel": "",
            "status": "",
            "utelatt": "",
        }

    fjernet = active_removals(raw, plan)
    days = _days(raw)
    cells = dict(days)
    h_dager = [key for key, cell in days if _is_h_dag(cell)]
    # Without work hours every second weekend the driver has to work the H-dag, so
    # it's ticked for them. Worked out here rather than saved, so restoring the
    # weekend gives the driver's own choice back.
    helg_varsel = bool(h_dager) and not _works_every_second_weekend(cells, fjernet + h_dager)
    h_dag_jobb = bool(plan.get("h_dag_jobb")) or helg_varsel
    h_fri = [] if h_dag_jobb else h_dager
    # The H-dag stays in these hours whether it's worked or not: NLF counts it as
    # 9 hours towards the target even when it's taken free.
    remaining = _to_minutes(raw["tj_timer"]) - sum(
        _to_minutes(cells[key]["tj_timer"]) for key in fjernet
    )
    prosent = plan["prosent"]
    target = None if prosent is None else round(FULL_POSITION_MINUTES * prosent / 100)
    return {
        "available": True,
        "prosent": prosent,
        "beregnet_prosent": _beregnet_prosent(remaining) if fjernet else "",
        "total": _format(FULL_POSITION_MINUTES),
        "target": None if target is None else _format(target),
        "remaining": _format(remaining),
        "fjernet": fjernet,
        "h_dager": h_dager,
        "h_fri": h_fri,
        "h_dag_jobb": h_dag_jobb,
        "helg_varsel": helg_varsel,
        "under_varsel": (
            f"Du er under {_format(LOWEST_POSITION_MINUTES)} Tj.t (80 %)."
            if fjernet and remaining < LOWEST_POSITION_MINUTES
            else ""
        ),
        "status": _status(remaining, target),
        "utelatt": _utelatt(len(fjernet) + len(h_fri)),
    }


def _partner(days, vakt):
    """The other half of a double duty, or None. Flags alone don't decide it: a
    receiver's number can be the second half of a double duty elsewhere, so the
    first half has to be on the day before."""
    keys = [key for key, _ in days]
    index = keys.index(vakt)
    cell = days[index][1]
    after = days[(index + 1) % len(days)]
    before = days[index - 1]
    if cell.get("is_consecutive_shift") and after[1].get("is_consecutive_receiver"):
        return after[0]
    if cell.get("is_consecutive_receiver") and before[1].get("is_consecutive_shift"):
        return before[0]
    return None


def _find_row(db_session, user_id, turnus_set_id, shift_title):
    return (
        db_session.query(RedusertStilling)
        .filter_by(user_id=user_id, turnus_set_id=turnus_set_id, shift_title=shift_title)
        .first()
    )


def get_plan(user_id, turnus_set_id, shift_title):
    db_session = get_db_session()
    try:
        row = _find_row(db_session, user_id, turnus_set_id, shift_title)
        return _as_plan(row) if row else _empty_plan()
    finally:
        db_session.close()


def set_vakt(user_id, turnus_set_id, shift_title, raw, vakt, fjernet):
    """Mark a shift, and its double-duty partner, as removed or not.

    Takes the wanted state rather than flipping it, so a retry or a stale tab
    can't undo a choice. Raises ValueError for anything but a work day, and for
    the H-dag, which has its own choice.
    """
    days = _days(raw)
    cells = dict(days)
    cell = cells.get(vakt) if isinstance(vakt, str) else None
    if cell is None or not _is_work(cell) or _is_h_dag(cell):
        raise ValueError("Denne dagen kan ikke velges.")
    keys = [vakt]
    partner = _partner(days, vakt)
    if partner:
        keys.append(partner)

    db_session = get_db_session()
    try:
        row = _find_row(db_session, user_id, turnus_set_id, shift_title)
        if row is None:
            if not fjernet:
                return _empty_plan()
            row = RedusertStilling(
                user_id=user_id, turnus_set_id=turnus_set_id, shift_title=shift_title
            )
            db_session.add(row)
        # A new dict each time: SQLAlchemy doesn't detect in-place JSON changes.
        updated = dict(row.fjernet or {})
        for key in keys:
            if fjernet:
                updated[key] = duty_id(cells[key].get("dagsverk"))
            else:
                updated.pop(key, None)
        row.fjernet = updated
        db_session.commit()
        return _as_plan(row)
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


def set_prosent(user_id, turnus_set_id, shift_title, prosent):
    """Set the target percentage, 1-100 with decimals, or None for no target.
    Raises ValueError for anything else."""
    if prosent is not None and (
        isinstance(prosent, bool)
        or not isinstance(prosent, (int, float))
        or not 1 <= prosent <= 100
    ):
        raise ValueError("Prosent må være mellom 1 og 100.")

    db_session = get_db_session()
    try:
        row = _find_row(db_session, user_id, turnus_set_id, shift_title)
        if row is None:
            if prosent is None:
                return _empty_plan()
            row = RedusertStilling(
                user_id=user_id, turnus_set_id=turnus_set_id, shift_title=shift_title, fjernet={}
            )
            db_session.add(row)
        row.prosent = prosent
        db_session.commit()
        return _as_plan(row)
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


def set_h_dag_jobb(user_id, turnus_set_id, shift_title, jobb):
    """Whether the driver works the H-dag. Not worked is the default."""
    db_session = get_db_session()
    try:
        row = _find_row(db_session, user_id, turnus_set_id, shift_title)
        if row is None:
            if not jobb:
                return _empty_plan()
            row = RedusertStilling(
                user_id=user_id, turnus_set_id=turnus_set_id, shift_title=shift_title, fjernet={}
            )
            db_session.add(row)
        row.h_dag_jobb = 1 if jobb else 0
        db_session.commit()
        return _as_plan(row)
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


def nullstill(user_id, turnus_set_id, shift_title):
    db_session = get_db_session()
    try:
        row = _find_row(db_session, user_id, turnus_set_id, shift_title)
        if row:
            db_session.delete(row)
            db_session.commit()
        return _empty_plan()
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()
