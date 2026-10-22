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

from config import AppConfig

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Go through AppConfig so relocating the data store can't strand these again.
_JSON_PATH = os.path.join(
    AppConfig.turnusfiler_dir, "r26", "turnus_schedule_R26.json"
)
_R25_JSON_PATH = os.path.join(
    AppConfig.turnusfiler_dir, "r25", "turnus_schedule_R25.json"
)
# Golden-file source PDF: prefer the committed test fixture, fall back to the
# (gitignored) location an admin upload would write to.
_FIXTURE_PDF = os.path.join(_ROOT, "tests", "fixtures", "turnuser_R26.pdf")
_STATIC_PDF = os.path.join(
    AppConfig.turnusfiler_dir, "r26", "pdf", "turnuser_R26.pdf"
)
_PDF_PATH = _FIXTURE_PDF if os.path.exists(_FIXTURE_PDF) else _STATIC_PDF
# Primary source (committed): the Timeskjema export the JSON was built from.
_TIMESKJEMA_PATH = os.path.join(
    AppConfig.turnusfiler_dir, "r26", "turnuser_R26.xls"
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
        # Timeskjema values. The PDF edition printed 203:27 / 223:14; the
        # Timeskjema is the primary source (decided 2026-07-08).
        d = _get_turnus(turnus_data, "OSL_01")
        assert d["kl_timer"] == "203:26"
        assert d["tj_timer"] == "223:11"

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
# TestHardenedValidator — committed JSON must pass the production validator
# ---------------------------------------------------------------------------


class TestHardenedValidator:
    """The committed schedule files must pass validate_turnus_json (the same
    gate every ingestion path uses), including the hours cross-check and the
    start/slutt consistency check. Guards against accidental data corruption."""

    @pytest.mark.parametrize(
        "path",
        [
            pytest.param(_JSON_PATH, id="R26"),
            pytest.param(_R25_JSON_PATH, id="R25"),
        ],
    )
    def test_committed_schedule_is_valid(self, path):
        from app.utils.pdf.scraper_validator import validate_turnus_json

        if not os.path.exists(path):
            pytest.skip(f"Schedule file not found: {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ok, errors = validate_turnus_json(data, expected_count=len(data))
        assert ok, (
            f"{os.path.basename(path)}: {len(errors)} validation problem(s):\n"
            + "\n".join(errors[:20])
        )


# ---------------------------------------------------------------------------
# TestTimeskjemaRoundtrip — the committed JSON must be exactly what the
# ingestion pipeline produces from the committed sources
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def scraped():
    """ShiftScraper output for the fixture PDF (int week/day keys)."""
    if not os.path.exists(_PDF_PATH):
        pytest.skip(f"PDF not available at {_PDF_PATH}")
    from app.utils.pdf.shiftscraper import ShiftScraper

    scraper = ShiftScraper()
    scraper.scrape_pdf(_PDF_PATH)
    return scraper.turnuser


class TestTimeskjemaRoundtrip:
    """The Timeskjema is the primary source and the PDF only enriches
    dagsverk strings (``3006`` -> ``3006_SKNO``). Re-running that pipeline on
    the committed sources must reproduce the committed JSON byte for byte.
    A mismatch means the JSON was hand-edited, regenerated without the PDF in
    place (enrichment silently skipped), or the sources were swapped without
    a refresh."""

    def test_stored_json_equals_enriched_timeskjema_parse(
        self, turnus_data, scraped
    ):
        from app.utils.timeskjema_parser import parse_timeskjema
        from app.utils.turnus_diff import enrich_dagsverk

        if not os.path.exists(_TIMESKJEMA_PATH):
            pytest.skip(f"Timeskjema not available at {_TIMESKJEMA_PATH}")
        parsed = parse_timeskjema(_TIMESKJEMA_PATH).turnuser
        # JSON round-trip: the parser emits int keys, the stored file has str.
        expected = json.loads(json.dumps(enrich_dagsverk(parsed, scraped)))
        assert expected == turnus_data


# ---------------------------------------------------------------------------
# TestScraperRoundtrip — the PDF edition differs from the Timeskjema in a
# known, fixed set of revision cells and nothing else
# ---------------------------------------------------------------------------

# Every cell (turnus, uke, dag) and every turnus total where the fixture PDF
# ("Oslo R26 etter listemøte", printed 09.10.2025) disagrees with the later
# Timeskjema export. All 20 cells and 9 totals are genuine planning revisions
# (verified against the PDF's own printed text), not scrape errors. See
# CLAUDE.md "Cross-source verification must never hard-fail on inequality".
_KNOWN_PDF_REVISION_CELLS = {
    ("OSL_01", 3, 7),
    ("OSL_02", 1, 2),
    ("OSL_02", 1, 3),
    ("OSL_03", 1, 6),
    ("OSL_03", 1, 7),
    ("OSL_04", 1, 5),
    ("OSL_04", 1, 6),
    ("OSL_07", 1, 3),
    ("OSL_07", 1, 4),
    ("OSL_15_Østre_Linje", 3, 3),
    ("OSL_15_Østre_Linje", 3, 4),
    ("OSL_19_Gjøvik", 1, 3),
    ("OSL_19_Gjøvik", 3, 3),
    ("OSL_25", 5, 7),
    ("OSL_33", 5, 7),
    ("OSL_Ramme_10", 1, 6),
    ("OSL_Ramme_10", 1, 7),
    ("OSL_Ramme_10", 5, 3),
    ("OSL_Ramme_10", 5, 6),
    ("OSL_Ramme_10", 5, 7),
}
_KNOWN_PDF_REVISION_TOTALS = {
    "OSL_01", "OSL_03", "OSL_04", "OSL_07", "OSL_25", "OSL_28", "OSL_33",
    "OSL_38", "OSL_Ramme_10",
}


class TestScraperRoundtrip:
    def test_same_turnus_count(self, turnus_data, scraped):
        assert len(scraped) == len(turnus_data)

    def test_same_turnus_names(self, turnus_data, scraped):
        stored_names = {next(iter(e)) for e in turnus_data}
        scraped_names = {next(iter(e)) for e in scraped}
        assert scraped_names == stored_names

    def test_pdf_differs_only_in_known_revision_cells(self, turnus_data, scraped):
        # Exact set equality both ways: a new difference means the scraper or
        # the JSON drifted; a vanished one means the sources were swapped and
        # this list needs re-deriving.
        from app.utils.turnus_diff import diff_turnus_data

        diff = diff_turnus_data(turnus_data, scraped)
        cells = {(c["turnus"], c["uke"], c["dag"]) for c in diff["cells"]}
        totals = {t["turnus"] for t in diff["totals"]}
        assert cells == _KNOWN_PDF_REVISION_CELLS, (
            f"unexpected: {sorted(cells - _KNOWN_PDF_REVISION_CELLS)}, "
            f"missing: {sorted(_KNOWN_PDF_REVISION_CELLS - cells)}"
        )
        assert totals == _KNOWN_PDF_REVISION_TOTALS, (
            f"unexpected: {sorted(totals - _KNOWN_PDF_REVISION_TOTALS)}, "
            f"missing: {sorted(_KNOWN_PDF_REVISION_TOTALS - totals)}"
        )

    def test_scraped_start_slutt_consistent(self, scraped):
        # Locks the start/slutt assembly fix in the scraper itself: for every
        # working day the derived fields must be the two ends of ``tid``.
        for entry in scraped:
            name, s_data = next(iter(entry.items()))
            for week_nr in range(1, 7):
                for day_nr in range(1, 8):
                    day = s_data[week_nr][day_nr]
                    tid = day["tid"]
                    if len(tid) == 2:
                        assert day["start"] == tid[0], f"{name} W{week_nr}D{day_nr}"
                        assert day["slutt"] == tid[1], f"{name} W{week_nr}D{day_nr}"
