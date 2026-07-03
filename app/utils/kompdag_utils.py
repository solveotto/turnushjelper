"""Kompdag (compensation day) computation.

Per overenskomsten §5.13.1, the following days are fridager: 1. og 17. mai,
nyttårsdag, skjærtorsdag, langfredag, påskeaften, 1. og 2. påskedag, Kristi
himmelfartsdag, 1. og 2. pinsedag og 1. og 2. juledag. When a rostered day
off in the turnus falls on one of these dates, a kompdag is generated.

Holiday dates are computed from calendar rules (fixed dates plus
Easter-derived offsets) instead of being read from the red font in the
turnusnøkkel Excel template, which is manually colored and incomplete.
The Excel template is still the only source mapping rotation weeks to
calendar dates.
"""

import logging
import os
from datetime import date, timedelta

from config import AppConfig

logger = logging.getLogger(__name__)

# Off-day codes that always generate a kompdag when landing on an official
# holiday. Empty days are handled separately: they only count when not
# adjacent to a night shift (an empty day before/after a night shift is part
# of the night-shift span, not a real fridag).
KOMPDAG_OFF_CODES = {"X", "O", "T"}


def _easter(year):
    """Easter Sunday for a Gregorian year (Anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def get_official_holidays(year):
    """The 13 fridager listed in overenskomsten §5.13.1 for one calendar year."""
    easter = _easter(year)
    return {
        date(year, 1, 1),  # nyttårsdag
        easter - timedelta(days=3),  # skjærtorsdag
        easter - timedelta(days=2),  # langfredag
        easter - timedelta(days=1),  # påskeaften
        easter,  # 1. påskedag
        easter + timedelta(days=1),  # 2. påskedag
        date(year, 5, 1),  # 1. mai
        date(year, 5, 17),  # 17. mai
        easter + timedelta(days=39),  # Kristi himmelfartsdag
        easter + timedelta(days=49),  # 1. pinsedag
        easter + timedelta(days=50),  # 2. pinsedag
        date(year, 12, 25),  # 1. juledag
        date(year, 12, 26),  # 2. juledag
    }


def get_holidays_for_dates(dates):
    """Official holidays among the given dates.

    A turnus year spans two calendar years (e.g. R26 runs des 2025 – des
    2026), so holidays are unioned across every calendar year present in
    the input before intersecting.
    """
    dates = {d for d in dates}
    holidays = set()
    for year in {d.year for d in dates}:
        holidays |= get_official_holidays(year)
    return holidays & dates


def get_kompdag_holidays(dates):
    """Holidays among the given dates that generate kompdager for this
    rutetermin. Two exclusions apply:

    - Holidays falling on a Sunday never trigger a kompdag (which means
      1. påskedag and 1. pinsedag never do, and e.g. 17. mai 2026 does not).
    - Holidays after 12. desember of the final calendar year in the range
      (e.g. jul 2026 in the R26 nøkkel) belong to the next rutetermin, which
      starts mid-December. Holidays in the leading December still count.
    """
    dates = {d for d in dates}
    holidays = {d for d in get_holidays_for_dates(dates) if d.weekday() != 6}
    if not dates:
        return holidays
    cutoff = date(max(d.year for d in dates), 12, 12)
    return {d for d in holidays if d <= cutoff}


def _cell_date(cell):
    """Normalize an openpyxl cell value to a date, or None if not a date."""
    value = cell.value
    if value is None or not hasattr(value, "strftime"):
        return None
    return value.date() if hasattr(value, "date") else value


def get_holiday_positions(year_identifier):
    """Map official holidays onto the rotation grid of a year's turnusnøkkel.

    Returns a list of (group, day, date) tuples (group 0-5, day 0-6, Monday
    first) for each holiday date in the template, deduped by date keeping the
    first occurrence in group-scan order. Returns None when the template file
    is missing, so callers can distinguish "no data" from "zero kompdager".
    """
    import openpyxl

    template_path = os.path.join(
        AppConfig.turnusfiler_dir,
        year_identifier.lower(),
        f"turnusnøkkel_{year_identifier}_org.xlsx",
    )
    if not os.path.exists(template_path):
        logger.warning("Turnusnøkkel template not found: %s", template_path)
        return None

    wb = openpyxl.load_workbook(template_path, data_only=True)
    sheet = wb["Turnusnøkkel"]
    all_rows = [list(row) for row in sheet.iter_rows(min_row=1, max_row=48)]
    wb.close()

    cell_dates = []
    for g in range(6):
        for d in range(7):
            for cell in all_rows[g * 8 + 1 + d][7:16]:
                cal_date = _cell_date(cell)
                if cal_date is not None:
                    cell_dates.append((g, d, cal_date))

    holidays = get_kompdag_holidays(dt for (_, _, dt) in cell_dates)
    positions = []
    seen = set()
    for g, d, dt in cell_dates:
        if dt in holidays and dt not in seen:
            seen.add(dt)
            positions.append((g, d, dt))
    return positions


def _parse_minutes(time_str):
    hours, minutes = time_str.split(":")
    return int(hours) * 60 + int(minutes)


def _is_night_shift(day_data):
    """Whether a schedule day entry is a work shift crossing midnight."""
    if not isinstance(day_data, dict):
        return False
    tid = day_data.get("tid", [])
    if len(tid) < 2:
        return False
    try:
        return _parse_minutes(tid[1]) < _parse_minutes(tid[0])
    except (AttributeError, ValueError):
        return False


def _neighbor_day(weeks, week, day, step):
    """The schedule entry one day before/after, wrapping across the 6-week
    rotation (week 1 day 1 is preceded by week 6 day 7)."""
    day += step
    if day < 1:
        day = 7
        week = week - 1 if week > 1 else 6
    elif day > 7:
        day = 1
        week = week + 1 if week < 6 else 1
    return weeks.get(week, {}).get(str(day))


def _generates_kompdag(weeks, week, day):
    """Whether the given rotation day is a fridag that generates a kompdag.

    X/O/T days always do. Empty days (blank cell after/before a night shift
    span) only do when neither neighboring day is a night shift.
    """
    day_data = weeks.get(week, {}).get(str(day))
    tid = day_data.get("tid", []) if isinstance(day_data, dict) else []
    if len(tid) >= 2:
        return False
    code = tid[0] if tid else ""
    if code in KOMPDAG_OFF_CODES:
        return True
    if code != "":
        return False
    return not (
        _is_night_shift(_neighbor_day(weeks, week, day, -1))
        or _is_night_shift(_neighbor_day(weeks, week, day, 1))
    )


def count_kompdager_for_turnus(turnus_weeks, positions):
    """Per-linje kompdag counts for one turnus (index 0 = linje 1).

    turnus_weeks is one turnus' schedule dict ({"1".."6": {"1".."7": day}});
    positions come from get_holiday_positions(). A worker on linje j follows
    rotation week ((g + j - 1) % 6) + 1 during nøkkel group g.
    """
    weeks = {int(k): v for k, v in turnus_weeks.items() if isinstance(v, dict)}
    counts = []
    for linje in range(1, 7):
        n = 0
        for g, d, _dt in positions:
            week = (g + linje - 1) % 6 + 1
            if _generates_kompdag(weeks, week, d + 1):
                n += 1
        counts.append(n)
    return counts


def kompdager_max_label(counts):
    """Compact "max (linje)" label for stats grids, e.g. "10 (L1)"."""
    if not counts:
        return "–"
    best = max(counts)
    return f"{best} (L{counts.index(best) + 1})"


def count_kompdager(turnus_set_id):
    """Per-linje kompdag counts for every turnus in a set.

    Returns {turnus_name: [linje1..linje6]} or None when the nøkkel template
    (the only calendar-date source) is unavailable.
    """
    from app.extensions import cache
    from app.utils import df_utils

    cache_key = f"kompdager_{turnus_set_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    dm = df_utils.DataframeManager(turnus_set_id)
    turnus_set = dm.get_current_turnus_info()
    if not turnus_set:
        return None

    positions = get_holiday_positions(turnus_set["year_identifier"])
    if positions is None:
        return None

    result = {}
    for entry in dm.turnus_data:
        for name, data in entry.items():
            if isinstance(data, dict):
                result[name] = count_kompdager_for_turnus(data, positions)

    cache.set(cache_key, result, timeout=3600)
    return result
