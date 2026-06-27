"""
Unit tests for the turnus validation gate (app/utils/pdf/scraper_validator.py)
and the scraper's pure helper methods.

The validator is the single chokepoint every ingestion path passes through, so
each failure mode gets its own test. Tests start from a fully valid turnus
(make_valid_turnus_data) and mutate one field to trigger exactly one problem.
"""

from app.utils.pdf.scraper_validator import (
    _compute_worked_hours,
    _shift_duration_minutes,
    validate_turnus_json,
)
from app.utils.pdf.shiftscraper import ShiftScraper
from tests.conftest import (
    make_free_day,
    make_valid_turnus_data,
    make_work_day,
    turnus_list,
)


def _errs(*data_by_name, **kw):
    """Validate one or more named turnuser and return (ok, errors)."""
    return validate_turnus_json(turnus_list(*data_by_name), **kw)


def _one(data, name="OSL_01", **kw):
    return validate_turnus_json(turnus_list((name, data)), **kw)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_turnus_passes():
    ok, errors = _one(make_valid_turnus_data())
    assert ok, errors
    assert errors == []


def test_valid_turnus_passes_with_expected_count():
    ok, errors = _one(make_valid_turnus_data(), expected_count=1)
    assert ok, errors


# ---------------------------------------------------------------------------
# Top-level structure
# ---------------------------------------------------------------------------

def test_not_a_list():
    ok, errors = validate_turnus_json({"OSL_01": {}})
    assert not ok
    assert any("must be a list" in e for e in errors)


def test_empty_list():
    ok, errors = validate_turnus_json([])
    assert not ok
    assert any("empty" in e for e in errors)


def test_entry_not_single_key_dict():
    ok, errors = validate_turnus_json([{"A": {}, "B": {}}])
    assert not ok
    assert any("single-key dict" in e for e in errors)


def test_data_not_dict():
    ok, errors = validate_turnus_json([{"OSL_01": "nope"}])
    assert not ok
    assert any("must be a dict" in e for e in errors)


# ---------------------------------------------------------------------------
# Week / day structure
# ---------------------------------------------------------------------------

def test_missing_week():
    data = make_valid_turnus_data()
    del data["6"]
    ok, errors = _one(data)
    assert not ok
    assert any("missing week 6" in e for e in errors)


def test_missing_day():
    data = make_valid_turnus_data()
    del data["1"]["1"]
    ok, errors = _one(data)
    assert not ok
    assert any("W1D1: missing day" in e for e in errors)


def test_wrong_ukedag():
    data = make_valid_turnus_data()
    data["1"]["1"]["ukedag"] = "Tirsdag"
    ok, errors = _one(data)
    assert not ok
    assert any("ukedag 'Tirsdag' expected 'Mandag'" in e for e in errors)


# ---------------------------------------------------------------------------
# tid / dagsverk consistency
# ---------------------------------------------------------------------------

def test_invalid_time_format():
    data = make_valid_turnus_data()
    data["1"]["1"]["tid"] = ["8:00", "abc"]
    ok, errors = _one(data)
    assert not ok
    assert any("invalid tid value 'abc'" in e for e in errors)


def test_two_times_without_dagsverk():
    data = make_valid_turnus_data()
    data["1"]["1"]["dagsverk"] = ""
    ok, errors = _one(data)
    assert not ok
    assert any("2 time values but dagsverk is empty" in e for e in errors)


def test_dagsverk_with_single_time():
    data = make_valid_turnus_data()
    # single time but keep dagsverk; replace cleanly so start/slutt stay consistent
    day = make_free_day(1)
    day["dagsverk"] = "D11"
    data["1"]["1"] = day
    ok, errors = _one(data)
    assert not ok
    assert any("expected 2" in e for e in errors)


def test_shift_longer_than_15h():
    data = make_valid_turnus_data()
    data["1"]["1"] = make_work_day(1, "6:00", "23:30", "D11")  # 17.5h
    ok, errors = _one(data)
    assert not ok
    assert any("exceeds 15 h" in e for e in errors)


# ---------------------------------------------------------------------------
# Totals
# ---------------------------------------------------------------------------

def test_kl_timer_out_of_range():
    data = make_valid_turnus_data(kl_timer="999:00")
    ok, errors = _one(data)
    assert not ok
    assert any("kl_timer" in e and "range" in e for e in errors)


def test_tj_timer_out_of_range():
    data = make_valid_turnus_data(tj_timer="999:00")
    ok, errors = _one(data)
    assert not ok
    assert any("tj_timer" in e and "range" in e for e in errors)


def test_missing_totals():
    data = make_valid_turnus_data()
    del data["kl_timer"]
    del data["tj_timer"]
    ok, errors = _one(data)
    assert not ok
    assert any("missing kl_timer" in e for e in errors)
    assert any("missing tj_timer" in e for e in errors)


# ---------------------------------------------------------------------------
# New hardened checks
# ---------------------------------------------------------------------------

def test_hours_crosscheck_below_band():
    # computed 210h, but kl_timer claims 240h -> sum far below band
    data = make_valid_turnus_data(kl_timer="240:00")
    ok, errors = _one(data)
    assert not ok
    assert any("summed shift hours" in e and "outside plausible band" in e for e in errors)


def test_hours_crosscheck_above_band():
    # computed 210h, but kl_timer claims 190h -> sum above kl+12h band
    data = make_valid_turnus_data(kl_timer="190:00")
    ok, errors = _one(data)
    assert not ok
    assert any("summed shift hours" in e for e in errors)


def test_duplicate_turnus_name():
    ok, errors = _errs(
        ("OSL_01", make_valid_turnus_data()),
        ("OSL_01", make_valid_turnus_data()),
    )
    assert not ok
    assert any("Duplicate turnus name 'OSL_01'" in e for e in errors)


def test_unknown_name_rejected():
    ok, errors = _one(make_valid_turnus_data(), name="UNKNOWN")
    assert not ok
    assert any("missing or UNKNOWN" in e for e in errors)


def test_expected_count_mismatch():
    ok, errors = _one(make_valid_turnus_data(), expected_count=2)
    assert not ok
    assert any("Expected 2 turnuser but found 1" in e for e in errors)


def test_start_slutt_list_mismatch():
    # The real bug: start aliases the tid list and slutt is empty.
    data = make_valid_turnus_data()
    data["1"]["1"]["start"] = ["8:00", "15:00"]
    data["1"]["1"]["slutt"] = ""
    ok, errors = _one(data)
    assert not ok
    assert any("do not mirror tid" in e for e in errors)


def test_free_day_with_nonempty_slutt():
    data = make_valid_turnus_data()
    data["1"]["6"]["slutt"] = "12:00"  # Saturday is a free day
    ok, errors = _one(data)
    assert not ok
    assert any("non-work day should have empty slutt" in e for e in errors)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_shift_duration_minutes_wraps_midnight():
    assert _shift_duration_minutes("8:00", "15:00") == 420
    assert _shift_duration_minutes("22:00", "6:00") == 480  # wraps past midnight


def test_compute_worked_hours():
    # 30 work days x 7h = 210h
    assert _compute_worked_hours(make_valid_turnus_data()) == 210.0


# ---------------------------------------------------------------------------
# Scraper pure-helper methods
# ---------------------------------------------------------------------------

def test_split_concatenated_times():
    s = ShiftScraper()
    assert s.split_concatenated_times("19:014:24") == ["19:01", "4:24"]
    assert s.split_concatenated_times("8:0016:00") == ["8:00", "16:00"]
    assert s.split_concatenated_times("8:00") == ["8:00"]
    assert s.split_concatenated_times("X") == ["X"]


def test_extract_turnus_name_multiword_until_separator():
    s = ShiftScraper()
    words = [
        {"text": "Turnus:", "top": 100},
        {"text": "OSL", "top": 100},
        {"text": "Ramme", "top": 100},
        {"text": "01", "top": 100},
        {"text": "Stasjoneringssted:", "top": 100},
    ]
    assert s.extract_turnus_name(words, 0) == "OSL_Ramme_01"


def test_extract_turnus_name_stops_on_vertical_jump():
    s = ShiftScraper()
    words = [
        {"text": "Turnus:", "top": 100},
        {"text": "OSL", "top": 100},
        {"text": "99", "top": 130},  # >10px below -> different line, excluded
    ]
    assert s.extract_turnus_name(words, 0) == "OSL"


def test_fridag_normalize_map():
    s = ShiftScraper()
    assert s.FRIDAG_NORMALIZE == {"XX": "X", "OO": "O", "TT": "T"}
