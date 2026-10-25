"""
Tests for shift statistics correctness.

Covers:
  - Night shift classification rules (the 04:00 boundary)
  - Freshness: stored stats JSON must match what shift_stats.py produces now
  - Sanity: counts are internally consistent (no double-counting, no overflow)

Run with:
    pytest tests/test_shift_stats.py -v
"""

import json
import os
import sys
import types

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: shift_stats.py imports config and pandas but has no Flask dep.
# We mock config so it can be imported standalone.
# ---------------------------------------------------------------------------

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_mock_config = types.ModuleType("config")


class _AppConfig:
    static_dir = os.path.join(_ROOT, "app", "static")
    # The turnus data store lives outside app/static (see config.py).
    turnusfiler_dir = os.path.join(_ROOT, "turnusdata")


_mock_config.AppConfig = _AppConfig
sys.modules.setdefault("config", _mock_config)

from app.utils.shift_stats import Turnus  # noqa: E402  (must come after mock)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TURNUSDATA = _AppConfig.turnusfiler_dir

_YEARS = [
    (
        "R26",
        os.path.join(_TURNUSDATA, "r26", "turnus_schedule_R26.json"),
        os.path.join(_TURNUSDATA, "r26", "turnus_stats_R26.json"),
    ),
    (
        "R25",
        os.path.join(_TURNUSDATA, "r25", "turnus_schedule_R25.json"),
        os.path.join(_TURNUSDATA, "r25", "turnus_stats_R25.json"),
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fresh_stats_r26():
    _, schedule_path, _ = _YEARS[0]
    return Turnus(schedule_path).stats_df


@pytest.fixture(scope="module")
def stored_stats_r26():
    _, _, stats_path = _YEARS[0]
    with open(stats_path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# TestNightShiftClassification
#
# Unit-tests the Turnus classifier against hand-crafted minimal JSON.
# We build the smallest valid turnus JSON that exercises specific boundaries.
# ---------------------------------------------------------------------------

def _make_single_shift_json(turnus_name, start, end, day=1):
    """Return a minimal turnus_schedule JSON with one work shift and 41 off days."""
    from tests.conftest import single_shift_schedule

    return single_shift_schedule(turnus_name, start, end, day)


def _compute_natt(start, end):
    """Helper: run shift_stats on a single-shift turnus and return natt count."""
    import tempfile
    data = _make_single_shift_json("TEST", start, end)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f)
        path = f.name
    try:
        result = Turnus(path).stats_df
        return int(result[result["turnus"] == "TEST"]["natt"].iloc[0])
    finally:
        os.unlink(path)


def _compute_kveld(start, end):
    import tempfile
    data = _make_single_shift_json("TEST", start, end)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f)
        path = f.name
    try:
        result = Turnus(path).stats_df
        return int(result[result["turnus"] == "TEST"]["ettermiddag"].iloc[0])
    finally:
        os.unlink(path)


# Weekday numbers for single_shift_schedule(day=...).
MANDAG, ONSDAG, FREDAG, LORDAG, SONDAG = 1, 3, 5, 6, 7


def _compute_helg(start, end, day):
    """Helper: the (dagtid, ettermiddag, natt) weekend hours of one shift."""
    import tempfile
    data = _make_single_shift_json("TEST", start, end, day)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(data, f)
        path = f.name
    try:
        result = Turnus(path).stats_df
        row = result[result["turnus"] == "TEST"].iloc[0]
        return (
            float(row["helgetimer_dagtid"]),
            float(row["helgetimer_ettermiddag"]),
            float(row["helgetimer_natt"]),
        )
    finally:
        os.unlink(path)


class TestNightShiftClassification:
    """The 04:00 threshold: shifts ending < 04:00 after crossing midnight are kveld, not natt."""

    def test_ends_before_threshold_is_not_natt(self):
        # 17:50–02:00 crosses midnight, ends 02:00 < 04:00 → kveld
        assert _compute_natt("17:50", "2:00") == 0

    def test_ends_before_threshold_is_kveld(self):
        assert _compute_kveld("17:50", "2:00") == 1

    def test_ends_at_threshold_is_natt(self):
        # 22:00–04:00 ends exactly at 04:00 → natt
        assert _compute_natt("22:00", "4:00") == 1

    def test_ends_after_threshold_is_natt(self):
        # 23:00–06:00 → natt
        assert _compute_natt("23:00", "6:00") == 1

    def test_ends_just_before_threshold_not_natt(self):
        # 21:00–03:59 → kveld (one minute before threshold)
        assert _compute_natt("21:00", "3:59") == 0

    def test_ends_at_midnight_not_natt(self):
        # 16:00–00:00 → kveld
        assert _compute_natt("16:00", "0:00") == 0

    def test_same_day_shift_not_natt(self):
        # 22:00–23:30 (no midnight crossing) → not natt
        assert _compute_natt("22:00", "23:30") == 0

    def test_early_morning_start_not_natt(self):
        # 06:00–14:00 → tidligvakt, definitely not natt
        assert _compute_natt("06:00", "14:00") == 0

    def test_natt_is_not_also_tidlig(self):
        """A shift classified as natt must not also count as tidlig."""
        import tempfile
        data = _make_single_shift_json("TEST", "22:00", "6:00")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            path = f.name
        try:
            row = Turnus(path).stats_df[Turnus(path).stats_df["turnus"] == "TEST"].iloc[0]
            assert row["natt"] == 1
            assert row["tidlig"] == 0
        finally:
            os.unlink(path)


class TestWeekendHourBuckets:
    """The dagtid / ettermiddag / natt split of helgetimer.

    One decision in shift_stats.py routes every weekend hour:
      nattevakt (crosses midnight, ends 04:00+)  -> natt
      starts 14:00+ OR crosses midnight          -> ettermiddag
      otherwise                                  -> dagtid

    The `or crosses_midnight` clause is load-bearing: without it a Sunday
    shift running past midnight but ending before 04:00 lands in helgetimer
    and in no bucket at all.
    """

    def test_saturday_before_14_is_dagtid(self):
        assert _compute_helg("10:00", "18:00", LORDAG) == (8.0, 0.0, 0.0)

    def test_saturday_from_14_is_ettermiddag(self):
        assert _compute_helg("14:00", "22:00", LORDAG) == (0.0, 8.0, 0.0)

    def test_sunday_past_midnight_is_ettermiddag_not_dagtid(self):
        """The gap: starts before 14:00, crosses midnight, is not a nattevakt."""
        assert _compute_helg("12:00", "0:30", SONDAG) == (0.0, 12.5, 0.0)

    def test_friday_night_shift_is_natt(self):
        """Friday counts only from 17:00, and a nattevakt goes to natt."""
        assert _compute_helg("22:00", "6:00", FREDAG) == (0.0, 0.0, 8.0)

    def test_friday_before_14_running_past_17_is_ettermiddag(self):
        """Friday counts only the hours from 17:00, and those are evening hours
        whatever time the shift itself began — the bucket must be decided on the
        start of the counted window, not on the start of the shift."""
        assert _compute_helg("10:00", "19:00", FREDAG) == (0.0, 2.0, 0.0)

    def test_friday_hours_are_clipped_at_17(self):
        """15:00-20:00 contributes only the three hours after 17:00."""
        assert _compute_helg("15:00", "20:00", FREDAG) == (0.0, 3.0, 0.0)

    def test_friday_ending_before_17_has_no_weekend_hours(self):
        assert _compute_helg("12:00", "16:00", FREDAG) == (0.0, 0.0, 0.0)

    def test_sunday_night_is_capped_at_monday_06(self):
        """22:00-08:00 counts 8 h, not 10 — the weekend window closes at 06:00."""
        assert _compute_helg("22:00", "8:00", SONDAG) == (0.0, 0.0, 8.0)

    def test_midweek_shift_has_no_weekend_hours(self):
        assert _compute_helg("10:00", "18:00", ONSDAG) == (0.0, 0.0, 0.0)


ALL_DAYS = {(w, d) for w in range(1, 7) for d in range(1, 8)}


def _rotation_stats(off_days, night_days=()):
    """Helper: the stats row of a rotation that works every day except
    ``off_days``; days in ``night_days`` get a nattevakt instead of a day shift.
    Both are sets of (week, day)."""
    import tempfile
    from tests.conftest import WEEKDAYS_NB

    data = {}
    for w in range(1, 7):
        week = {}
        for d in range(1, 8):
            if (w, d) in off_days:
                tid = ["X"]
            elif (w, d) in night_days:
                tid = ["22:00", "6:00"]
            else:
                tid = ["7:00", "15:00"]
            week[str(d)] = {"ukedag": WEEKDAYS_NB[d - 1], "tid": tid, "dagsverk": "TEST"}
        data[str(w)] = week
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump([{"TEST": data}], f)
        path = f.name
    try:
        result = Turnus(path).stats_df
        return result[result["turnus"] == "TEST"].iloc[0]
    finally:
        os.unlink(path)


class TestStreaksWrap:
    """The rotation repeats: week 6 day 7 is followed by week 1 day 1."""

    def test_off_period_across_week_6_to_week_1_is_one_period(self):
        off = {(6, 5), (6, 6), (6, 7), (1, 1), (1, 2)}
        assert _rotation_stats(off)["longest_off_streak"] == 5

    def test_day_after_night_shift_in_week_6_is_not_a_day_off(self):
        """A nattevakt on week 6 Søndag makes week 1 Mandag its sleep-off day."""
        off = {(1, 1), (1, 2), (1, 3)}
        assert _rotation_stats(off, night_days={(6, 7)})["longest_off_streak"] == 2

    def test_off_period_within_rotation_is_unchanged(self):
        off = {(3, 2), (3, 3), (3, 4), (3, 5)}
        assert _rotation_stats(off)["longest_off_streak"] == 4

    def test_work_period_across_week_6_to_week_1_is_one_period(self):
        work = {(6, 4), (6, 5), (6, 6), (6, 7), (1, 1), (1, 2), (1, 3)}
        assert _rotation_stats(ALL_DAYS - work)["longest_work_streak"] == 7

    def test_work_period_within_rotation_is_unchanged(self):
        work = {(3, 2), (3, 3), (3, 4), (3, 5), (3, 6)}
        assert _rotation_stats(ALL_DAYS - work)["longest_work_streak"] == 5


# ---------------------------------------------------------------------------
# TestStatsFreshness
#
# The stored turnus_stats_*.json must exactly match what shift_stats.py
# produces from the schedule file today.  A mismatch means the JSON is stale.
# ---------------------------------------------------------------------------

_STAT_COLUMNS = ["shift_cnt", "tidlig", "ettermiddag", "natt", "before_6",
                 "tidlig_6_8", "tidlig_8_12", "helgetimer",
                 "helgetimer_dagtid", "helgetimer_ettermiddag", "helgetimer_natt",
                 "longest_off_streak", "longest_work_streak", "avg_shift_hours"]


def _load_stored_as_dict(stats_path):
    """Return {turnus_name: {col: value}} from the stored JSON."""
    with open(stats_path, encoding="utf-8") as f:
        raw = json.load(f)
    names = raw["turnus"]
    result = {}
    for k, name in names.items():
        result[name] = {col: raw[col][k] for col in _STAT_COLUMNS if col in raw}
    return result


@pytest.mark.parametrize("year,schedule_path,stats_path", _YEARS)
def test_stored_stats_match_fresh_computation(year, schedule_path, stats_path):
    """Stored JSON must match a fresh run of shift_stats.py — catches stale files."""
    if not os.path.exists(schedule_path):
        pytest.skip(f"Schedule file not found: {schedule_path}")
    if not os.path.exists(stats_path):
        pytest.skip(f"Stats file not found: {stats_path}")

    fresh_df = Turnus(schedule_path).stats_df
    stored = _load_stored_as_dict(stats_path)

    mismatches = []
    for _, row in fresh_df.iterrows():
        name = row["turnus"]
        if name not in stored:
            mismatches.append(f"{name}: not found in stored JSON")
            continue
        stored_row = stored[name]
        for col in _STAT_COLUMNS:
            if col not in stored_row:
                continue
            fresh_val = round(float(row[col]), 1)
            stored_val = round(float(stored_row[col]), 1)
            if fresh_val != stored_val:
                mismatches.append(
                    f"{name}.{col}: stored={stored_val}, fresh={fresh_val}"
                )

    assert not mismatches, (
        f"{year}: stored stats are stale — regenerate with "
        f"`python app/utils/shift_stats.py {year}`.\n"
        + "\n".join(mismatches)
    )


# ---------------------------------------------------------------------------
# TestStatsSanity
#
# Internal consistency checks on the freshly computed stats.
# ---------------------------------------------------------------------------


class TestStatsSanity:
    def test_natt_plus_tidlig_plus_kveld_leq_shift_cnt(self, fresh_stats_r26):
        for _, row in fresh_stats_r26.iterrows():
            total = row["natt"] + row["tidlig"] + row["ettermiddag"]
            assert total <= row["shift_cnt"], (
                f"{row['turnus']}: natt+tidlig+kveld={total} > shift_cnt={row['shift_cnt']}"
            )

    def test_tidlig_subtypes_sum_leq_tidlig(self, fresh_stats_r26):
        for _, row in fresh_stats_r26.iterrows():
            subtypes = row["before_6"] + row["tidlig_6_8"] + row["tidlig_8_12"]
            assert subtypes <= row["tidlig"], (
                f"{row['turnus']}: before_6+tidlig_6_8+tidlig_8_12={subtypes} > tidlig={row['tidlig']}"
            )

    def test_shift_cnt_positive(self, fresh_stats_r26):
        for _, row in fresh_stats_r26.iterrows():
            assert row["shift_cnt"] > 0, f"{row['turnus']}: shift_cnt is 0"

    def test_avg_shift_hours_plausible(self, fresh_stats_r26):
        for _, row in fresh_stats_r26.iterrows():
            assert 4.0 <= row["avg_shift_hours"] <= 16.0, (
                f"{row['turnus']}: avg_shift_hours={row['avg_shift_hours']} out of range"
            )
    def test_helg_buckets_partition_helgetimer(self, fresh_stats_r26):
        """dagtid + ettermiddag + natt must account for every weekend hour."""
        for _, row in fresh_stats_r26.iterrows():
            total = (row["helgetimer_dagtid"]
                        + row["helgetimer_ettermiddag"]
                        + row["helgetimer_natt"])
            # Three buckets and the total are each rounded to one decimal
            # independently, so the rounded sum can drift up to 4 x 0.05 from
            # the rounded total. Worst case observed across R25+R26 is 0.1.
            assert abs(total - row["helgetimer"]) <= 0.2, (
                f"{row['turnus']}: buckets sum to {total}, helgetimer is {row['helgetimer']}"
            )

    def test_helgetimer_non_negative(self, fresh_stats_r26):
        for _, row in fresh_stats_r26.iterrows():
            assert row["helgetimer"] >= 0, f"{row['turnus']}: helgetimer is negative"

    def test_known_natt_counts_r26(self, fresh_stats_r26):
        """Spot-check turnus that were affected by the stale-JSON bug."""
        affected = {"OSL_26": 0, "OSL_Ramme_04": 0}
        for _, row in fresh_stats_r26.iterrows():
            if row["turnus"] in affected:
                assert row["natt"] == affected[row["turnus"]], (
                    f"{row['turnus']}: expected natt={affected[row['turnus']]}, "
                    f"got {row['natt']}"
                )
