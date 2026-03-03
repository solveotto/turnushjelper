"""
Validator for scraped turnus JSON data.

validate_turnus_json() is called:
- In admin routes before writing scraped data to disk (fast-fail on bad scrapes)
- In DataframeManager after loading from disk (runtime corruption check)
- In tests as a standalone assertion
"""

import re
from typing import Any

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


def validate_turnus_json(data: Any) -> tuple[bool, list[str]]:
    """Validate scraped turnus JSON structure and values.

    Returns (is_valid, errors) where errors is a list of human-readable
    problem descriptions. Empty errors list means valid.
    """
    errors: list[str] = []

    if not isinstance(data, list):
        return False, ["Top-level value must be a list"]

    if len(data) == 0:
        return False, ["Turnus list is empty"]

    for idx, entry in enumerate(data):
        if not isinstance(entry, dict) or len(entry) != 1:
            errors.append(
                f"Entry {idx}: expected single-key dict, got {type(entry).__name__}"
            )
            continue

        turnus_name = next(iter(entry))
        turnus_data = entry[turnus_name]

        if not isinstance(turnus_data, dict):
            errors.append(f"{turnus_name}: data must be a dict")
            continue

        _validate_totals(turnus_name, turnus_data, errors)
        _validate_weeks(turnus_name, turnus_data, errors)

    return len(errors) == 0, errors


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
            h0, m0 = map(int, times[0].split(":"))
            h1, m1 = map(int, times[1].split(":"))
            start_min = h0 * 60 + m0
            end_min = h1 * 60 + m1
            duration = end_min - start_min if end_min >= start_min else end_min - start_min + 1440
            if duration > 900:  # 15 hours
                errors.append(
                    f"{loc}: shift duration {duration // 60}h{duration % 60:02d}m "
                    f"exceeds 15 h (start={times[0]}, end={times[1]})"
                )
