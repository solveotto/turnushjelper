"""Tests for app/utils/turnuskalender.py — the nøkkel date grid.

The grid tests build a synthetic sheet rather than reading turnusdata/, which
is gitignored: the shape of the nøkkel is what is under test, not one year's
contents. The real-file test at the bottom skips when R26 is not present.
"""

import datetime
import os

import pytest

from app.utils import turnuskalender as tk


class _Cell:
    """Minimal stand-in for an openpyxl cell."""

    def __init__(self, value=None):
        self.value = value


def _build_rows(start=datetime.date(2026, 1, 5), weeks_per_group=9, offset=0):
    """A synthetic nøkkel: 6 groups of 8 rows, dates in columns H–P.

    ``offset`` shifts every group that many columns to the right, the way the
    R27 draft has groups 1-4 starting in column I with H blank.

    Group g, week column w holds the Monday-first week starting
    ``start + (g + w * 6) weeks`` — the same interleaving the real sheet has,
    where consecutive calendar weeks land in consecutive groups.
    """
    rows = [[_Cell() for _ in range(20)] for _ in range(48)]
    for g in range(6):
        for w in range(weeks_per_group):
            rows[g * 8][7 + offset + w] = _Cell(f"Uke {g + w * 6 + 1}")
            monday = start + datetime.timedelta(weeks=g + w * 6)
            for d in range(7):
                rows[g * 8 + 1 + d][7 + offset + w] = _Cell(monday + datetime.timedelta(days=d))
    return rows


class TestBuildDateIndex:
    def test_maps_every_date_to_group_and_day(self):
        rows = _build_rows()
        index = tk.build_date_index(rows=rows)

        assert len(index) == 6 * 9 * 7
        # First Monday of group 0 -> (group 0, day 0)
        assert index[datetime.date(2026, 1, 5)] == (0, 0)
        # The Sunday of that same week is day 6, still group 0
        assert index[datetime.date(2026, 1, 11)] == (0, 6)
        # The next calendar week belongs to group 1
        assert index[datetime.date(2026, 1, 12)] == (1, 0)

    def test_ignores_empty_cells(self):
        rows = _build_rows(weeks_per_group=2)
        index = tk.build_date_index(rows=rows)
        assert len(index) == 6 * 2 * 7

    def test_covers_its_range_without_gaps(self):
        index = tk.build_date_index(rows=_build_rows())
        day = min(index)
        while day <= max(index):
            assert day in index, f"gap at {day}"
            day += datetime.timedelta(days=1)


class TestDateColumns:
    """The week columns are wherever the group's header says "Uke", not a
    fixed H-P. The R27 draft (2026-10-22) had groups 1-4 shifted one column
    right, which silently dropped weeks 48 and 49 from the page and mintur."""

    def test_standard_layout_is_h_to_p(self):
        header = _build_rows()[0]
        assert tk.date_columns(header) == slice(7, 16)

    def test_shifted_group_is_found_by_its_uke_label(self):
        header = _build_rows(offset=1)[0]
        assert tk.date_columns(header) == slice(8, 17)

    def test_label_match_is_case_insensitive_and_tolerates_padding(self):
        header = [_Cell() for _ in range(20)]
        header[9] = _Cell("  uke 53 ")
        assert tk.date_columns(header) == slice(9, 18)

    def test_falls_back_to_h_when_no_label(self):
        header = [_Cell() for _ in range(20)]
        assert tk.date_columns(header) == slice(7, 16)

    def test_index_reads_the_ninth_week_of_a_shifted_group(self):
        index = tk.build_date_index(rows=_build_rows(offset=1))
        assert len(index) == 6 * 9 * 7
        assert index[datetime.date(2026, 1, 5)] == (0, 0)

    def test_groups_may_differ_in_offset(self):
        rows = _build_rows()
        shifted = _build_rows(offset=1)
        for g in range(4):  # groups 1-4 shifted, 5-6 not — the R27 shape
            rows[g * 8:(g + 1) * 8] = shifted[g * 8:(g + 1) * 8]
        assert tk.build_date_index(rows=rows) == tk.build_date_index(rows=_build_rows())


class TestRotationWeek:
    def test_matches_the_mintur_formula(self):
        # ((group + linjenummer - 1) % 6) + 1, group 0-based, linje 1-6
        for group in range(6):
            for linje in range(1, 7):
                assert tk.rotation_week(group, linje) == (group + linje - 1) % 6 + 1

    def test_always_in_range(self):
        for group in range(6):
            for linje in range(1, 7):
                assert 1 <= tk.rotation_week(group, linje) <= 6

    def test_each_linje_visits_all_six_weeks_over_a_rotation(self):
        for linje in range(1, 7):
            assert {tk.rotation_week(g, linje) for g in range(6)} == {1, 2, 3, 4, 5, 6}


class TestLookupCell:
    WEEKS = {"4": {"3": {"dagsverk": "1413", "start": "6:05", "slutt": "15:00"}}}

    def test_finds_the_cell(self):
        # day is 0-based on the way in, matching build_date_index's output
        cell = tk.lookup_cell(self.WEEKS, 4, 2)
        assert cell["dagsverk"] == "1413"

    def test_missing_cell_is_none(self):
        assert tk.lookup_cell(self.WEEKS, 1, 0) is None

    def test_non_dict_cell_is_none(self):
        assert tk.lookup_cell({"1": {"1": "X"}}, 1, 0) is None


@pytest.mark.skipif(
    not os.path.exists(tk.nokkel_path("R26")),
    reason="turnusdata/r26 is gitignored and not present",
)
class TestAgainstRealR26:
    def test_covers_the_rutetermin_without_gaps(self):
        index = tk.build_date_index("R26")
        assert min(index) == datetime.date(2025, 12, 15)
        assert max(index) == datetime.date(2026, 12, 27)
        assert len(index) == 378

    def test_resolves_the_1413_anchor(self):
        """The 1413-ØV69 duty screenshot says 'Turnus 4 OSL 10 Østre Linje',
        06:05-15:00. That must be OSL_10_Østre_Linje rotation week 4, day 3."""
        import json

        from config import AppConfig

        path = os.path.join(
            AppConfig.turnusfiler_dir, "r26", "turnus_schedule_R26.json"
        )
        schedule = {}
        for entry in json.load(open(path, encoding="utf-8")):
            schedule.update(entry)

        cell = tk.lookup_cell(schedule["OSL_10_Østre_Linje"], 4, 2)
        assert cell["dagsverk"] == "1413"
        assert cell["start"] == "6:05"
        assert cell["slutt"] == "15:00"
