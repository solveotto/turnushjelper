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


_mock_config.AppConfig = _AppConfig
sys.modules.setdefault("config", _mock_config)

from app.utils.shift_stats import Turnus  # noqa: E402  (must come after mock)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_YEARS = [
    (
        "R26",
        os.path.join(_ROOT, "app", "static", "turnusfiler", "r26", "turnus_schedule_R26.json"),
        os.path.join(_ROOT, "app", "static", "turnusfiler", "r26", "turnus_stats_R26.json"),
    ),
    (
        "R25",
        os.path.join(_ROOT, "app", "static", "turnusfiler", "r25", "turnus_schedule_R25.json"),
        os.path.join(_ROOT, "app", "static", "turnusfiler", "r25", "turnus_stats_R25.json"),
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

def _make_single_shift_json(turnus_name, start, end):
    """Return a minimal turnus_schedule JSON with one work shift and 41 off days."""
    days = {}
    weekdays = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
    for week in range(1, 7):
        days[str(week)] = {}
        for day in range(1, 8):
            if week == 1 and day == 1:
                days["1"]["1"] = {
                    "ukedag": "Mandag",
                    "tid": [start, end],
                    "dagsverk": "TEST",
                }
            else:
                days[str(week)][str(day)] = {
                    "ukedag": weekdays[day - 1],
                    "tid": ["X"],
                    "dagsverk": "X",
                }
    return [{turnus_name: days}]


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


# ---------------------------------------------------------------------------
# TestStatsFreshness
#
# The stored turnus_stats_*.json must exactly match what shift_stats.py
# produces from the schedule file today.  A mismatch means the JSON is stale.
# ---------------------------------------------------------------------------

_STAT_COLUMNS = ["shift_cnt", "tidlig", "ettermiddag", "natt", "before_6",
                 "tidlig_6_8", "tidlig_8_12", "helgetimer", "longest_off_streak",
                 "longest_work_streak", "avg_shift_hours"]


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
