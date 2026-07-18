"""Tests for the timeskjema (.xls TSV export) parser.

The fixture ``tests/fixtures/timeskjema_sample.xls`` is a byte-exact excerpt of
the real "R26 endelig.xls": the OSL 01 block (accounting-week offset, X/O/T
fridager, blank sleep-off rows) and the OSL Utland 4 block (0:00 midnight end,
`&` artifacts) followed by the trailing station-summary section that a parser
must not consume. Expected values below are hand-verified against the raw file.
"""

import datetime
import os

import pytest

from app.utils.pdf.scraper_validator import validate_turnus_json
from app.utils.timeskjema_parser import (
    TimeskjemaParseError,
    parse_timeskjema,
    sniff_format,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "timeskjema_sample.xls")


def fixture_bytes():
    with open(FIXTURE, "rb") as f:
        return f.read()


class TestSniffFormat:
    def test_pdf_magic(self):
        assert sniff_format(b"%PDF-1.7 rest of file") == "pdf"

    def test_timeskjema_fixture(self):
        assert sniff_format(fixture_bytes()) == "timeskjema"

    def test_ole2_real_excel_is_unknown(self):
        assert sniff_format(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64) == "unknown"

    def test_html_is_unknown(self):
        assert sniff_format(b"<html><table><tr><td>Turnus:</td></tr></table>") == "unknown"

    def test_empty_is_unknown(self):
        assert sniff_format(b"") == "unknown"

    def test_random_text_is_unknown(self):
        assert sniff_format("bare litt tekst uten struktur".encode("iso-8859-1")) == "unknown"

    def test_timeskjema_header_without_turnus_lines_is_unknown(self):
        assert sniff_format("Timeskjema for Lokfører\ningen blokker".encode("iso-8859-1")) == "unknown"


class TestParseFixture:
    @pytest.fixture(scope="class")
    def result(self):
        return parse_timeskjema(FIXTURE)

    @pytest.fixture(scope="class")
    def osl01(self, result):
        return dict((k, v) for entry in result.turnuser for k, v in entry.items())["OSL_01"]

    @pytest.fixture(scope="class")
    def utland4(self, result):
        return dict((k, v) for entry in result.turnuser for k, v in entry.items())["OSL_Utland_4"]

    def test_turnus_names(self, result):
        names = [next(iter(e)) for e in result.turnuser]
        assert names == ["OSL_01", "OSL_Utland_4"]

    def test_passes_the_shared_validator(self, result):
        valid, errors = validate_turnus_json(result.turnuser)
        assert valid, errors

    def test_normal_shift_day(self, osl01):
        day = osl01[1][1]
        assert day["ukedag"] == "Mandag"
        assert day["tid"] == ["13:13", "19:01"]
        assert day["start"] == "13:13"
        assert day["slutt"] == "19:01"
        assert day["dagsverk"] == "3006"
        assert day["is_consecutive_shift"] is False
        assert day["is_consecutive_receiver"] is False

    def test_fridag_days_match_scraper_schema(self, osl01):
        x_day = osl01[1][3]
        assert x_day["tid"] == ["X"]
        assert x_day["start"] == ["X"]  # list, mirroring ShiftScraper output
        assert x_day["slutt"] == ""
        assert x_day["dagsverk"] == ""
        assert osl01[1][4]["tid"] == ["O"]
        assert osl01[4][5]["tid"] == ["T"]

    def test_accounting_week_offset_sunday(self, osl01):
        # Shift 9348 (Sun 23:45) is listed in the "Sum uke 2" block in the file
        # but belongs to calendar week 1 day 7.
        day = osl01[1][7]
        assert day["tid"] == ["23:45", "7:45"]
        assert day["dagsverk"] == "9348"

    def test_blank_sleep_off_day(self, osl01):
        day = osl01[2][2]
        assert day["tid"] == []
        assert day["start"] == []
        assert day["slutt"] == ""
        assert day["dagsverk"] == ""

    def test_long_numeric_dagsverk(self, osl01):
        assert osl01[6][5]["dagsverk"] == "9908001700"

    def test_totals(self, osl01, utland4):
        assert osl01["kl_timer"] == "203:26"
        assert osl01["tj_timer"] == "223:11"
        # Utland 4 totals come from its own "Totalsummer for turnus" row, not
        # the trailing station-summary "Totalsummer" row.
        assert utland4["kl_timer"] == "209:42"
        assert utland4["tj_timer"] == "223:06"

    def test_midnight_end(self, utland4):
        day = utland4[1][3]
        assert day["tid"] == ["14:00", "0:00"]
        assert day["dagsverk"] == "914002400"

    def test_all_42_days_present_with_correct_ukedag(self, osl01):
        ukedager = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
        for uke in range(1, 7):
            for dag in range(1, 8):
                assert osl01[uke][dag]["ukedag"] == ukedager[dag - 1]

    def test_rutetermin_dates(self, result):
        assert result.rutetermin_start == datetime.date(2025, 12, 14)
        assert result.rutetermin_end == datetime.date(2026, 12, 12)

    def test_year_id_warning(self, result):
        assert result.year_id_warning("R26") is None
        warning = result.year_id_warning("R27")
        assert warning is not None and "2026" in warning

    def test_accepts_bytes_input(self):
        result = parse_timeskjema(fixture_bytes())
        assert len(result.turnuser) == 2


class TestArtifacts:
    def test_ampersand_suffix_is_stripped(self):
        # Append '&' to a week-sum KL.TID value; parsing must still succeed
        # with identical arithmetic.
        mutated = fixture_bytes().replace(b"45:14", b"45:14&")
        result = parse_timeskjema(mutated)
        assert len(result.turnuser) == 2


class TestFailureModes:
    def test_shuffled_weekday_label(self):
        mutated = fixture_bytes().replace(b"Tirsdag\t3007", b"Mandag\t3007", 1)
        with pytest.raises(TimeskjemaParseError) as exc:
            parse_timeskjema(mutated)
        assert any("Tirsdag" in e for e in exc.value.errors)

    def test_missing_day_row(self):
        lines = fixture_bytes().split(b"\n")
        removed = [l for l in lines if not l.startswith(b"Tirsdag\t3007")]
        assert len(removed) == len(lines) - 1
        with pytest.raises(TimeskjemaParseError) as exc:
            parse_timeskjema(b"\n".join(removed))
        assert any("42" in e for e in exc.value.errors)

    def test_corrupted_week_sum_arithmetic(self):
        mutated = fixture_bytes().replace(b"30:58", b"30:59", 1)
        with pytest.raises(TimeskjemaParseError) as exc:
            parse_timeskjema(mutated)
        assert any("KL.TID" in e and "uke 1" in e for e in exc.value.errors)

    def test_ole2_bytes(self):
        with pytest.raises(TimeskjemaParseError):
            parse_timeskjema(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64)

    def test_empty_file(self):
        with pytest.raises(TimeskjemaParseError):
            parse_timeskjema(b"")

    def test_missing_kltid_column(self):
        mutated = fixture_bytes().replace(b"KL.TID", b"KLTID")
        with pytest.raises(TimeskjemaParseError) as exc:
            parse_timeskjema(mutated)
        assert any("KL.TID" in e for e in exc.value.errors)

    def test_times_without_dagsverk_number(self):
        # A day row with start/end times but empty Dv.Nr. is a structural
        # surprise, not a shift.
        mutated = fixture_bytes().replace(b"Mandag\t3006\t", b"Mandag\t\t", 1)
        with pytest.raises(TimeskjemaParseError):
            parse_timeskjema(mutated)

    def test_duplicate_turnus_name_caught_by_validator(self):
        # The parser itself accepts duplicates; the shared validator gate
        # rejects them.
        data = fixture_bytes()
        mutated = data.replace(b"Turnus: OSL Utland 4", b"Turnus: OSL 01")
        result = parse_timeskjema(mutated)
        valid, errors = validate_turnus_json(result.turnuser)
        assert not valid
        assert any("Duplicate" in e for e in errors)


_REAL_XLS = os.path.join(
    os.path.dirname(__file__), "..", "app", "static", "turnusfiler", "r26",
    "R26 endelig.xls",
)


@pytest.mark.skipif(
    not os.path.exists(_REAL_XLS),
    reason=f"Real timeskjema not available at {_REAL_XLS}",
)
class TestGoldenRealFile:
    """Parse the full real R26 export. Spot values are hand-verified against
    the raw file (2026-07-08); see docs/plans/import-turnusset-plan.md."""

    @pytest.fixture(scope="class")
    def result(self):
        return parse_timeskjema(_REAL_XLS)

    @pytest.fixture(scope="class")
    def by_name(self, result):
        return {name: data for entry in result.turnuser for name, data in entry.items()}

    def test_57_turnuser(self, result):
        assert len(result.turnuser) == 57

    def test_validator_passes(self, result):
        valid, errors = validate_turnus_json(result.turnuser)
        assert valid, errors

    def test_hand_verified_spot_values(self, by_name):
        osl01 = by_name["OSL_01"]
        assert osl01[3][7]["tid"] == ["7:02", "14:33"]  # revised vs PDF's 7:01
        assert osl01["kl_timer"] == "203:26"
        assert osl01["tj_timer"] == "223:11"
        assert by_name["OSL_19_Gjøvik"][1][3]["dagsverk"] == "7401"
        assert by_name["OSL_Ramme_10"][1][6]["dagsverk"] == "915000030"
        assert by_name["OSL_25"][5][7]["dagsverk"] == "1720"
        assert by_name["OSL_Utland_4"][1][3]["tid"] == ["14:00", "0:00"]

    def test_rutetermin(self, result):
        assert result.rutetermin_start == datetime.date(2025, 12, 14)
        assert result.rutetermin_end == datetime.date(2026, 12, 12)
        assert result.year_id_warning("R26") is None
