"""Unit tests for the 7.fører row parser (pure function, no PDF needed).

Row shapes below are real rows from innplassering_R26.pdf (verified with
pdfplumber 2026-07-18). The table columns are
    rownum | Ans | Fornavn | Etternavn | Rullenr | Tur | L | (TVP)
where texts[0] is just the table's sequential row counter — the driver's
actual linje within the target Tur is the L column after the Tur number.
"""

from app.utils.pdf.innplassering_scraper import _parse_data_row_7forer


class TestParse7ForerRow:
    def test_linje_comes_from_L_column_not_row_counter(self):
        # Row 1 of R26: counter=1, but L (real linje) = 3
        rec = _parse_data_row_7forer(
            ["1", "3", "Steinar", "Nordermoen", "64895", "13", "3"], {}
        )
        assert rec is not None
        assert rec["rullenummer"] == "64895"
        assert rec["shift_title"] == "Tur_13"
        assert rec["linjenummer"] == 3
        assert rec["is_7th_driver"] == 1

    def test_row_counter_larger_than_six_is_not_the_linje(self):
        # Row 9 of R26: counter=9 (impossible linje), L = 3
        rec = _parse_data_row_7forer(
            ["9", "185", "Fredrik", "Gudim", "93235", "38", "3"], {}
        )
        assert rec is not None
        assert rec["linjenummer"] == 3

    def test_double_surname_row(self):
        # Row 6 of R26: extra name token shifts everything right
        rec = _parse_data_row_7forer(
            ["6", "140", "Kim", "Wangen", "Bakkebråten", "36022", "23", "1"], {}
        )
        assert rec is not None
        assert rec["rullenummer"] == "36022"
        assert rec["shift_title"] == "Tur_23"
        assert rec["linjenummer"] == 1

    def test_header_row_skipped(self):
        rec = _parse_data_row_7forer(
            ["Ans", "Fornavn", "Etternavn", "Rullenr", "Tur", "L", "TVP"], {}
        )
        assert rec is None

    def test_row_without_L_column_is_rejected(self):
        # No trustworthy linje available — better no record than a wrong one.
        rec = _parse_data_row_7forer(
            ["1", "3", "Steinar", "Nordermoen", "64895", "13"], {}
        )
        assert rec is None

    def test_ikke_sokbar_row_skipped(self):
        rec = _parse_data_row_7forer(
            ["1", "x", "Steinar", "Nordermoen", "64895", "13", "3"], {}
        )
        assert rec is None
