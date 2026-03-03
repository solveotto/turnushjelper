"""
Data integrity tests for turnus JSON and the scraper pipeline.

No DB or Flask app fixtures needed — all tests operate on files and
the standalone validator / scraper.

Run with:
    pytest tests/test_data_integrity.py -v
"""

import json
import os
import re

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JSON_PATH = os.path.join(
    _ROOT, "app", "static", "turnusfiler", "r26", "turnus_schedule_R26.json"
)
_PDF_PATH = os.path.join(
    _ROOT, "app", "static", "turnusfiler", "r26", "turnuser_R26.pdf"
)

# ---------------------------------------------------------------------------
# Shared fixture: load the stored JSON once per session
# ---------------------------------------------------------------------------

_WEEKDAYS = {
    1: "Mandag",
    2: "Tirsdag",
    3: "Onsdag",
    4: "Torsdag",
    5: "Fredag",
    6: "Lørdag",
    7: "Søndag",
}

_EXPECTED_NAMES = [
    "OSL_01", "OSL_02", "OSL_03", "OSL_04", "OSL_05", "OSL_06", "OSL_07",
    "OSL_08", "OSL_09_Østre_Linje", "OSL_10_Østre_Linje", "OSL_11_Østre_Linje",
    "OSL_12_Østre_Linje", "OSL_13_Østre_Linje", "OSL_14_Østre_Linje",
    "OSL_15_Østre_Linje", "OSL_16_Gjøvik", "OSL_17_Gjøvik", "OSL_18_Gjøvik",
    "OSL_19_Gjøvik", "OSL_20", "OSL_21", "OSL_22", "OSL_23", "OSL_24",
    "OSL_25", "OSL_26", "OSL_27", "OSL_28", "OSL_29", "OSL_30", "OSL_31",
    "OSL_32", "OSL_33", "OSL_34", "OSL_35", "OSL_36", "OSL_37", "OSL_38",
    "OSL_39", "OSL_40", "OSL_Ramme_01", "OSL_Ramme_02", "OSL_Ramme_03",
    "OSL_Ramme_04", "OSL_Ramme_05", "OSL_Ramme_06", "OSL_Ramme_07",
    "OSL_Ramme_08", "OSL_Ramme_09", "OSL_Ramme_10", "OSL_Ramme_11",
    "OSL_Ramme_12", "OSL_Ramme_13", "OSL_Utland_1", "OSL_Utland_2",
    "OSL_Utland_3", "OSL_Utland_4",
]

_FREE_CODES = {"X", "O", "T"}
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
_TOTAL_RE = re.compile(r"^\d{1,3}:\d{2}$")


@pytest.fixture(scope="module")
def turnus_data():
    with open(_JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def _get_turnus(data: list, name: str) -> dict:
    """Return the inner dict for a named turnus entry."""
    for entry in data:
        if name in entry:
            return entry[name]
    raise KeyError(f"Turnus '{name}' not found in data")


# ---------------------------------------------------------------------------
# TestJsonStructure
# ---------------------------------------------------------------------------


class TestJsonStructure:
    def test_is_list_of_57(self, turnus_data):
        assert isinstance(turnus_data, list)
        assert len(turnus_data) == 57

    def test_all_expected_names_present(self, turnus_data):
        names = [next(iter(e)) for e in turnus_data]
        assert set(names) == set(_EXPECTED_NAMES)

    def test_all_entries_single_key_dicts(self, turnus_data):
        for entry in turnus_data:
            assert isinstance(entry, dict) and len(entry) == 1

    def test_all_weeks_and_days_present(self, turnus_data):
        for entry in turnus_data:
            name, d = next(iter(entry.items()))
            for week_nr in range(1, 7):
                week = d.get(str(week_nr))
                assert week is not None, f"{name}: missing week {week_nr}"
                for day_nr in range(1, 8):
                    assert str(day_nr) in week, f"{name} W{week_nr}: missing day {day_nr}"

    def test_all_days_have_required_fields(self, turnus_data):
        for entry in turnus_data:
            name, d = next(iter(entry.items()))
            for week_nr in range(1, 7):
                for day_nr in range(1, 8):
                    day = d[str(week_nr)][str(day_nr)]
                    for field in ("ukedag", "tid", "dagsverk"):
                        assert field in day, f"{name} W{week_nr}D{day_nr}: missing '{field}'"

    def test_weekday_names_match_day_number(self, turnus_data):
        for entry in turnus_data:
            name, d = next(iter(entry.items()))
            for week_nr in range(1, 7):
                for day_nr in range(1, 8):
                    ukedag = d[str(week_nr)][str(day_nr)]["ukedag"]
                    assert ukedag == _WEEKDAYS[day_nr], (
                        f"{name} W{week_nr}D{day_nr}: "
                        f"ukedag '{ukedag}' != '{_WEEKDAYS[day_nr]}'"
                    )


# ---------------------------------------------------------------------------
# TestTimeValues
# ---------------------------------------------------------------------------


class TestTimeValues:
    def test_all_tid_values_valid(self, turnus_data):
        for entry in turnus_data:
            name, d = next(iter(entry.items()))
            for week_nr in range(1, 7):
                for day_nr in range(1, 8):
                    for t in d[str(week_nr)][str(day_nr)]["tid"]:
                        assert isinstance(t, str), f"{name} W{week_nr}D{day_nr}: non-string tid"
                        assert t in _FREE_CODES or _TIME_RE.match(t), (
                            f"{name} W{week_nr}D{day_nr}: invalid tid '{t}'"
                        )

    def test_kl_timer_format_and_range(self, turnus_data):
        for entry in turnus_data:
            name, d = next(iter(entry.items()))
            kl = d.get("kl_timer")
            assert kl is not None, f"{name}: missing kl_timer"
            assert _TOTAL_RE.match(str(kl)), f"{name}: kl_timer '{kl}' bad format"
            h, m = map(int, kl.split(":"))
            assert 150 <= h + m / 60 <= 280, f"{name}: kl_timer {kl} out of range"

    def test_tj_timer_format_and_range(self, turnus_data):
        for entry in turnus_data:
            name, d = next(iter(entry.items()))
            tj = d.get("tj_timer")
            assert tj is not None, f"{name}: missing tj_timer"
            assert _TOTAL_RE.match(str(tj)), f"{name}: tj_timer '{tj}' bad format"
            h, m = map(int, tj.split(":"))
            assert 200 <= h + m / 60 <= 250, f"{name}: tj_timer {tj} out of range"


# ---------------------------------------------------------------------------
# TestKnownValues — spot-checks against authoritative data
# ---------------------------------------------------------------------------


class TestKnownValues:
    def test_osl01_totals(self, turnus_data):
        d = _get_turnus(turnus_data, "OSL_01")
        assert d["kl_timer"] == "203:27"
        assert d["tj_timer"] == "223:14"

    def test_osl01_w1d1(self, turnus_data):
        day = _get_turnus(turnus_data, "OSL_01")["1"]["1"]
        assert day["dagsverk"] == "3006_SKNO"
        assert day["tid"] == ["13:13", "19:01"]

    def test_osl01_w1d3_fridag(self, turnus_data):
        day = _get_turnus(turnus_data, "OSL_01")["1"]["3"]
        assert day["tid"] == ["X"]

    def test_osl01_w1d7_contains_night(self, turnus_data):
        day = _get_turnus(turnus_data, "OSL_01")["1"]["7"]
        assert "23:45" in day["tid"]

    def test_osl20_totals(self, turnus_data):
        d = _get_turnus(turnus_data, "OSL_20")
        assert d["kl_timer"] == "206:18"
        assert d["tj_timer"] == "224:24"

    def test_osl20_w3d4(self, turnus_data):
        day = _get_turnus(turnus_data, "OSL_20")["3"]["4"]
        assert day["dagsverk"] == "1413"
        assert "6:05" in day["tid"]

    def test_osl40_totals(self, turnus_data):
        d = _get_turnus(turnus_data, "OSL_40")
        assert d["kl_timer"] == "209:09"
        assert d["tj_timer"] == "223:29"

    def test_osl40_w3d4(self, turnus_data):
        day = _get_turnus(turnus_data, "OSL_40")["3"]["4"]
        assert day["dagsverk"] == "1411-N05"
        assert "6:01" in day["tid"]


# ---------------------------------------------------------------------------
# TestScraperRoundtrip — re-scrape the real PDF and compare to stored JSON
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.path.exists(_PDF_PATH),
    reason=f"PDF not available at {_PDF_PATH}",
)
class TestScraperRoundtrip:
    @pytest.fixture(scope="class")
    def scraped(self):
        from app.utils.pdf.shiftscraper import ShiftScraper

        scraper = ShiftScraper()
        scraper.scrape_pdf(_PDF_PATH)
        return scraper.turnuser

    def test_same_turnus_count(self, turnus_data, scraped):
        assert len(scraped) == len(turnus_data)

    def test_same_turnus_names(self, turnus_data, scraped):
        stored_names = {next(iter(e)) for e in turnus_data}
        scraped_names = {next(iter(e)) for e in scraped}
        assert scraped_names == stored_names

    def test_all_tid_values_match(self, turnus_data, scraped):
        # Stored JSON has string keys; scraper keeps integer keys in memory.
        stored_map = {next(iter(e)): next(iter(e.values())) for e in turnus_data}
        for entry in scraped:
            name, s_data = next(iter(entry.items()))
            t_data = stored_map[name]
            for week_nr in range(1, 7):
                for day_nr in range(1, 8):
                    s_tid = s_data[week_nr][day_nr]["tid"]
                    t_tid = t_data[str(week_nr)][str(day_nr)]["tid"]
                    assert s_tid == t_tid, (
                        f"{name} W{week_nr}D{day_nr}: "
                        f"scraped tid {s_tid} != stored {t_tid}"
                    )

    def test_all_dagsverk_match(self, turnus_data, scraped):
        stored_map = {next(iter(e)): next(iter(e.values())) for e in turnus_data}
        for entry in scraped:
            name, s_data = next(iter(entry.items()))
            t_data = stored_map[name]
            for week_nr in range(1, 7):
                for day_nr in range(1, 8):
                    s_dv = s_data[week_nr][day_nr]["dagsverk"]
                    t_dv = t_data[str(week_nr)][str(day_nr)]["dagsverk"]
                    assert s_dv == t_dv, (
                        f"{name} W{week_nr}D{day_nr}: "
                        f"scraped dagsverk '{s_dv}' != stored '{t_dv}'"
                    )

    def test_all_totals_match(self, turnus_data, scraped):
        stored_map = {next(iter(e)): next(iter(e.values())) for e in turnus_data}
        for entry in scraped:
            name, s_data = next(iter(entry.items()))
            t_data = stored_map[name]
            assert s_data.get("kl_timer") == t_data.get("kl_timer"), (
                f"{name}: kl_timer mismatch"
            )
            assert s_data.get("tj_timer") == t_data.get("tj_timer"), (
                f"{name}: tj_timer mismatch"
            )
