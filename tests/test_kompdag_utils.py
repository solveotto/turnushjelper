"""Tests for kompdag computation (app/utils/kompdag_utils.py)."""

from datetime import date

from app.utils import kompdag_utils
from app.utils.kompdag_utils import (
    count_kompdager_for_turnus,
    get_holidays_for_dates,
    get_kompdag_holidays,
    get_official_holidays,
    kompdager_max_label,
)


class TestGetOfficialHolidays:
    def test_2025_holidays(self):
        holidays = get_official_holidays(2025)
        assert holidays == {
            date(2025, 1, 1),  # nyttårsdag
            date(2025, 4, 17),  # skjærtorsdag
            date(2025, 4, 18),  # langfredag
            date(2025, 4, 19),  # påskeaften
            date(2025, 4, 20),  # 1. påskedag
            date(2025, 4, 21),  # 2. påskedag
            date(2025, 5, 1),
            date(2025, 5, 17),
            date(2025, 5, 29),  # Kristi himmelfartsdag
            date(2025, 6, 8),  # 1. pinsedag
            date(2025, 6, 9),  # 2. pinsedag
            date(2025, 12, 25),
            date(2025, 12, 26),
        }

    def test_2026_holidays(self):
        holidays = get_official_holidays(2026)
        assert holidays == {
            date(2026, 1, 1),
            date(2026, 4, 2),  # skjærtorsdag
            date(2026, 4, 3),  # langfredag
            date(2026, 4, 4),  # påskeaften
            date(2026, 4, 5),  # 1. påskedag
            date(2026, 4, 6),  # 2. påskedag
            date(2026, 5, 1),
            date(2026, 5, 14),  # Kristi himmelfartsdag
            date(2026, 5, 17),
            date(2026, 5, 24),  # 1. pinsedag
            date(2026, 5, 25),  # 2. pinsedag
            date(2026, 12, 25),
            date(2026, 12, 26),
        }

    def test_12_or_13_distinct_days(self):
        # Normally 13 dates, but two §5.13.1 days can coincide (e.g. 2.
        # pinsedag lands on 17. mai when Easter falls on 28. mars, as in
        # 2027 and 2032), leaving 12 distinct dates.
        for year in range(2024, 2035):
            assert len(get_official_holidays(year)) in (12, 13)


class TestGetHolidaysForDates:
    def test_multi_year_union(self):
        # A turnus year spans two calendar years: jul 2025 AND jul 2026 must
        # both be found when the date range covers des 2025 – des 2026.
        dates = [
            date(2025, 12, 25),
            date(2026, 6, 1),  # not a holiday
            date(2026, 12, 25),
        ]
        assert get_holidays_for_dates(dates) == {
            date(2025, 12, 25),
            date(2026, 12, 25),
        }

    def test_non_holidays_excluded(self):
        assert get_holidays_for_dates([date(2026, 7, 3)]) == set()

    def test_empty_input(self):
        assert get_holidays_for_dates([]) == set()


class TestGetKompdagHolidays:
    def test_holidays_after_12_des_final_year_excluded(self):
        # Jul in the trailing December belongs to the next rutetermin.
        dates = [
            date(2025, 12, 25),  # leading December — counts for this termin
            date(2026, 1, 1),
            date(2026, 12, 25),  # after 12.12.2026 — next rutetermin
            date(2026, 12, 26),
        ]
        assert get_kompdag_holidays(dates) == {
            date(2025, 12, 25),
            date(2026, 1, 1),
        }

    def test_sunday_holidays_never_trigger(self):
        # 1. påskedag and 1. pinsedag always fall on Sundays; 17. mai 2026
        # happens to. None of them generate kompdager.
        dates = [
            date(2026, 4, 5),  # 1. påskedag (Sunday)
            date(2026, 4, 6),  # 2. påskedag (Monday) — counts
            date(2026, 5, 17),  # 17. mai 2026 (Sunday)
            date(2026, 5, 24),  # 1. pinsedag (Sunday)
            date(2026, 5, 25),  # 2. pinsedag (Monday) — counts
        ]
        assert get_kompdag_holidays(dates) == {
            date(2026, 4, 6),
            date(2026, 5, 25),
        }

    def test_17_mai_counts_when_not_sunday(self):
        # 17. mai 2027 is a Monday and triggers kompdager.
        assert get_kompdag_holidays([date(2027, 5, 17)]) == {date(2027, 5, 17)}

    def test_empty_input(self):
        assert get_kompdag_holidays([]) == set()


def _day(tid):
    return {"tid": tid, "dagsverk": "" if len(tid) < 2 else "1234"}


def _build_weeks(off_positions):
    """6x7 all-work schedule, with (week, day) in off_positions set to X."""
    weeks = {}
    for week in range(1, 7):
        weeks[str(week)] = {
            str(day): _day(["08:00", "16:00"]) for day in range(1, 8)
        }
    for week, day in off_positions:
        weeks[str(week)][str(day)] = _day(["X"])
    return weeks


class TestCountKompdagerForTurnus:
    def test_work_day_on_holiday_gives_no_kompdag(self):
        weeks = _build_weeks(off_positions=[])
        positions = [(0, 0, date(2026, 1, 1))]
        assert count_kompdager_for_turnus(weeks, positions) == [0] * 6

    def test_off_day_rotates_with_linje(self):
        # Holiday in group 0, Monday. Linje j follows week ((0+j-1)%6)+1 = j,
        # so only the linje matching the off-week gets the kompdag.
        weeks = _build_weeks(off_positions=[(3, 1)])  # week 3, Monday off
        positions = [(0, 0, date(2026, 1, 1))]
        assert count_kompdager_for_turnus(weeks, positions) == [0, 0, 1, 0, 0, 0]

    def test_group_offset_shifts_week(self):
        # Same off-day (week 3, Monday), holiday in group 2: linje j follows
        # week ((2+j-1)%6)+1, so linje 1 hits week 3.
        weeks = _build_weeks(off_positions=[(3, 1)])
        positions = [(2, 0, date(2026, 5, 1))]
        assert count_kompdager_for_turnus(weeks, positions) == [1, 0, 0, 0, 0, 0]

    def test_all_off_codes_count(self):
        for code in ["X", "O", "T"]:
            weeks = _build_weeks(off_positions=[])
            weeks["1"]["1"] = _day([code])
            positions = [(0, 0, date(2026, 1, 1))]
            counts = count_kompdager_for_turnus(weeks, positions)
            assert counts == [1, 0, 0, 0, 0, 0], f"code {code} should count"

    def test_missing_day_counts_as_off(self):
        weeks = _build_weeks(off_positions=[])
        del weeks["1"]["1"]
        positions = [(0, 0, date(2026, 1, 1))]
        assert count_kompdager_for_turnus(weeks, positions) == [1, 0, 0, 0, 0, 0]

    def test_empty_day_after_night_shift_does_not_count(self):
        weeks = _build_weeks(off_positions=[])
        weeks["1"]["1"] = _day(["23:30", "7:30"])  # night shift Monday
        weeks["1"]["2"] = _day([])  # blank Tuesday = sleep-off day
        positions = [(0, 1, date(2026, 1, 1))]  # holiday on Tuesday
        assert count_kompdager_for_turnus(weeks, positions) == [0] * 6

    def test_empty_day_before_night_shift_does_not_count(self):
        weeks = _build_weeks(off_positions=[])
        weeks["1"]["2"] = _day([])  # blank Tuesday
        weeks["1"]["3"] = _day(["23:30", "7:30"])  # night shift Wednesday
        positions = [(0, 1, date(2026, 1, 1))]
        assert count_kompdager_for_turnus(weeks, positions) == [0] * 6

    def test_empty_day_between_day_shifts_counts(self):
        weeks = _build_weeks(off_positions=[])
        weeks["1"]["2"] = _day([])  # blank Tuesday, ordinary shifts around it
        positions = [(0, 1, date(2026, 1, 1))]
        assert count_kompdager_for_turnus(weeks, positions) == [1, 0, 0, 0, 0, 0]

    def test_night_adjacency_wraps_rotation(self):
        # Blank Monday week 1 follows the night shift on Sunday week 6
        # (rotation wraps 6 -> 1), so it is not a fridag.
        weeks = _build_weeks(off_positions=[])
        weeks["6"]["7"] = _day(["22:00", "6:00"])
        weeks["1"]["1"] = _day([])
        positions = [(0, 0, date(2026, 1, 1))]
        assert count_kompdager_for_turnus(weeks, positions)[0] == 0

    def test_shift_ending_just_after_midnight_is_night(self):
        # e.g. 15:35-0:20 crosses midnight; the blank day after it is part
        # of the shift span, not a fridag (matches how R26 encodes these).
        weeks = _build_weeks(off_positions=[])
        weeks["1"]["1"] = _day(["15:35", "0:20"])
        weeks["1"]["2"] = _day([])
        positions = [(0, 1, date(2026, 1, 1))]
        assert count_kompdager_for_turnus(weeks, positions) == [0] * 6

    def test_excluded_code_does_not_count(self, monkeypatch):
        # A non-empty code outside KOMPDAG_OFF_CODES never generates a
        # kompdag (it does not fall back to the empty-day rule).
        monkeypatch.setattr(kompdag_utils, "KOMPDAG_OFF_CODES", {"X"})
        weeks = _build_weeks(off_positions=[])
        weeks["1"]["1"] = _day(["T"])
        positions = [(0, 0, date(2026, 1, 1))]
        assert count_kompdager_for_turnus(weeks, positions) == [0] * 6

    def test_multiple_holidays_accumulate(self):
        weeks = _build_weeks(off_positions=[(1, 1), (2, 5)])
        positions = [
            (0, 0, date(2026, 1, 1)),  # group 0 Monday -> week j
            (1, 4, date(2026, 5, 1)),  # group 1 Friday -> week ((1+j-1)%6)+1
        ]
        # Linje 1: week 1 Monday off (hit) + week 2 Friday off (hit) = 2
        counts = count_kompdager_for_turnus(weeks, positions)
        assert counts[0] == 2
        assert sum(counts) == 2


class TestKompdagerMaxLabel:
    def test_formats_max_and_linje(self):
        assert kompdager_max_label([10, 3, 9, 4, 8, 5]) == "10 (L1)"
        assert kompdager_max_label([1, 2, 3, 4, 5, 6]) == "6 (L6)"

    def test_first_linje_wins_ties(self):
        assert kompdager_max_label([5, 5, 1, 1, 1, 1]) == "5 (L1)"

    def test_none_and_empty(self):
        assert kompdager_max_label(None) == "–"
        assert kompdager_max_label([]) == "–"
