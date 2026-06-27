"""
Validator for scraped turnus JSON data.

validate_turnus_json() is called:
- In admin routes before writing scraped data to disk (fast-fail on bad scrapes)
- In DataframeManager after loading from disk (runtime corruption check)
- In tests as a standalone assertion
"""

import re
from typing import Any, Optional

_WEEKDAYS = {
    1: "Mandag",
    2: "Tirsdag",
    3: "Onsdag",
    4: "Torsdag",
    5: "Fredag",
    6: "Lørdag",
    7: "Søndag",
}
_FREE_CODES = {"X", "O", "T"}
_TIME_PATTERN = re.compile(r"^\d{1,2}:\d{2}$")
_TOTAL_PATTERN = re.compile(r"^\d{1,3}:\d{2}$")

# Turnus names that signal a failed name extraction.
_BAD_NAMES = {"", "UNKNOWN"}

# Hours cross-check tolerances, calibrated against committed R25/R26 data.
# kl_timer is paid time after unpaid-break deductions, so the raw sum of shift
# spans is always >= kl_timer and exceeds it by at most ~10 h (observed worst 9.7 h).
# The band catches a dropped/misplaced shift, which pushes the sum out of range.
_HOURS_TOL_LOW = 0.5    # only rounding slack is allowed below kl_timer
_HOURS_TOL_HIGH = 12.0  # unpaid-break allowance above kl_timer (max observed ~9.7 h)


def _shift_duration_minutes(t0: str, t1: str) -> int:
    """Minutes from t0 to t1, wrapping past midnight when t1 <= t0."""
    h0, m0 = map(int, t0.split(":"))
    h1, m1 = map(int, t1.split(":"))
    start_min = h0 * 60 + m0
    end_min = h1 * 60 + m1
    return end_min - start_min if end_min >= start_min else end_min - start_min + 1440


def _compute_worked_hours(data: dict) -> float:
    """Sum of every 2-time-day shift span in a turnus, in hours.

    Free days and (in current data, nonexistent) single-time days contribute
    nothing. Exposed for the calibration script and the hours cross-check.
    """
    total_min = 0
    for week_nr in range(1, 7):
        week_data = _get(data, week_nr)
        if not isinstance(week_data, dict):
            continue
        for day_nr in range(1, 8):
            day_data = _get(week_data, day_nr)
            if not isinstance(day_data, dict):
                continue
            tid = day_data.get("tid")
            if not isinstance(tid, list):
                continue
            times = [t for t in tid if isinstance(t, str) and _TIME_PATTERN.match(t)]
            if len(times) == 2:
                total_min += _shift_duration_minutes(times[0], times[1])
    return total_min / 60


def validate_turnus_json(
    data: Any, expected_count: Optional[int] = None
) -> tuple[bool, list[str]]:
    """Validate scraped turnus JSON structure and values.

    Returns (is_valid, errors) where errors is a list of human-readable
    problem descriptions. Empty errors list means valid.

    If ``expected_count`` is given, the number of turnuser must match it
    exactly (catches silently dropped turnuser).
    """
    errors: list[str] = []

    if not isinstance(data, list):
        return False, ["Top-level value must be a list"]

    if len(data) == 0:
        return False, ["Turnus list is empty"]

    seen_names: list[str] = []
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict) or len(entry) != 1:
            errors.append(
                f"Entry {idx}: expected single-key dict, got {type(entry).__name__}"
            )
            continue

        turnus_name = next(iter(entry))
        turnus_data = entry[turnus_name]
        seen_names.append(turnus_name)

        if turnus_name in _BAD_NAMES:
            errors.append(f"Entry {idx}: turnus name is missing or UNKNOWN")

        if not isinstance(turnus_data, dict):
            errors.append(f"{turnus_name}: data must be a dict")
            continue

        _validate_totals(turnus_name, turnus_data, errors)
        _validate_weeks(turnus_name, turnus_data, errors)
        _validate_hours_crosscheck(turnus_name, turnus_data, errors)

    for dup in sorted({n for n in seen_names if seen_names.count(n) > 1}):
        errors.append(
            f"Duplicate turnus name '{dup}' ({seen_names.count(dup)} occurrences)"
        )

    if expected_count is not None and len(data) != expected_count:
        errors.append(
            f"Expected {expected_count} turnuser but found {len(data)}"
        )

    return len(errors) == 0, errors


def _validate_hours_crosscheck(name: str, data: dict, errors: list[str]) -> None:
    """Cross-check summed shift spans against the printed kl_timer.

    kl_timer is paid time after unpaid breaks, so the raw span sum must satisfy
    kl_timer - TOL_LOW <= sum <= kl_timer + TOL_HIGH. A dropped or misplaced
    shift moves the sum out of that band. Skipped when kl_timer is missing or
    malformed (already flagged by _validate_totals).
    """
    kl = data.get("kl_timer")
    if kl is None or not _TOTAL_PATTERN.match(str(kl)):
        return

    h, m = map(int, str(kl).split(":"))
    kl_h = h + m / 60
    computed_h = _compute_worked_hours(data)

    if not (kl_h - _HOURS_TOL_LOW <= computed_h <= kl_h + _HOURS_TOL_HIGH):
        errors.append(
            f"{name}: summed shift hours {computed_h:.2f} h outside plausible band "
            f"[{kl_h - _HOURS_TOL_LOW:.2f}, {kl_h + _HOURS_TOL_HIGH:.2f}] h for "
            f"kl_timer {kl} — likely a misplaced or dropped shift"
        )


def _validate_totals(name: str, data: dict, errors: list[str]) -> None:
    kl = data.get("kl_timer")
    tj = data.get("tj_timer")

    if kl is None:
        errors.append(f"{name}: missing kl_timer")
    elif not _TOTAL_PATTERN.match(str(kl)):
        errors.append(f"{name}: kl_timer '{kl}' does not match HH:MM / HHH:MM")
    else:
        h, m = map(int, kl.split(":"))
        total_h = h + m / 60
        if not (150 <= total_h <= 280):
            errors.append(f"{name}: kl_timer {kl} out of plausible range 150–280 h")

    if tj is None:
        errors.append(f"{name}: missing tj_timer")
    elif not _TOTAL_PATTERN.match(str(tj)):
        errors.append(f"{name}: tj_timer '{tj}' does not match HH:MM / HHH:MM")
    else:
        h, m = map(int, tj.split(":"))
        total_h = h + m / 60
        if not (200 <= total_h <= 250):
            errors.append(f"{name}: tj_timer {tj} out of plausible range 200–250 h")


def _get(d: dict, key: int):
    """Look up a week/day key that may be stored as int (scraper) or str (JSON file)."""
    return d.get(key, d.get(str(key)))


def _validate_weeks(name: str, data: dict, errors: list[str]) -> None:
    for week_nr in range(1, 7):
        week_data = _get(data, week_nr)
        if week_data is None:
            errors.append(f"{name}: missing week {week_nr}")
            continue

        if not isinstance(week_data, dict):
            errors.append(f"{name} week {week_nr}: expected dict")
            continue

        for day_nr in range(1, 8):
            day_data = _get(week_data, day_nr)
            if day_data is None:
                errors.append(f"{name} W{week_nr}D{day_nr}: missing day")
                continue

            if not isinstance(day_data, dict):
                errors.append(f"{name} W{week_nr}D{day_nr}: expected dict")
                continue

            _validate_day(name, week_nr, day_nr, day_data, errors)


def _validate_day(
    name: str, week_nr: int, day_nr: int, day_data: dict, errors: list[str]
) -> None:
    loc = f"{name} W{week_nr}D{day_nr}"

    for field in ("ukedag", "tid", "dagsverk"):
        if field not in day_data:
            errors.append(f"{loc}: missing field '{field}'")

    ukedag = day_data.get("ukedag")
    expected = _WEEKDAYS.get(day_nr)
    if ukedag != expected:
        errors.append(f"{loc}: ukedag '{ukedag}' expected '{expected}'")

    tid = day_data.get("tid")
    dagsverk = day_data.get("dagsverk", "")

    if tid is None:
        pass  # already flagged as missing above
    elif not isinstance(tid, list):
        errors.append(f"{loc}: 'tid' must be a list")
    else:
        for t in tid:
            if not isinstance(t, str):
                errors.append(f"{loc}: tid value {t!r} is not a string")
            elif t not in _FREE_CODES and not _TIME_PATTERN.match(t):
                errors.append(f"{loc}: invalid tid value '{t}'")

        times = [t for t in tid if isinstance(t, str) and _TIME_PATTERN.match(t)]

        # Work days must have both start and end time
        if dagsverk and len(times) != 2:
            errors.append(
                f"{loc}: dagsverk '{dagsverk}' present but tid has {len(times)} "
                f"time value(s) (expected 2)"
            )

        # Two times must have a dagsverk code
        if len(times) == 2 and not dagsverk:
            errors.append(f"{loc}: 2 time values but dagsverk is empty")

        # Shift duration must be ≤ 15 h (guards against misplaced times)
        if len(times) == 2:
            duration = _shift_duration_minutes(times[0], times[1])
            if duration > 900:  # 15 hours
                errors.append(
                    f"{loc}: shift duration {duration // 60}h{duration % 60:02d}m "
                    f"exceeds 15 h (start={times[0]}, end={times[1]})"
                )

        # start/slutt must mirror tid (catches the by-reference assembly bug
        # where start aliased the tid list and slutt was left empty).
        if "start" in day_data or "slutt" in day_data:
            start = day_data.get("start")
            slutt = day_data.get("slutt")
            if len(times) == 2:
                if start != times[0] or slutt != times[1]:
                    errors.append(
                        f"{loc}: start/slutt ({start!r}/{slutt!r}) do not mirror tid "
                        f"(expected start={times[0]!r}, slutt={times[1]!r})"
                    )
            elif slutt not in ("", None):
                errors.append(
                    f"{loc}: non-work day should have empty slutt, got {slutt!r}"
                )
