"""Tests for the ansiennitetsliste PDF scraper.

The employer's export dropped the ``Rullenr.`` column in October 2026, so the
scraper must accept both the five- and the six-column layout. Fixtures are
generated with reportlab so no real (PII) list is committed.
"""

import pytest
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from app.utils.pdf.employee_scraper import _clean_date, scrape_employees

HEADER_6 = ("Nr", "Etternavn", "For- og mellomnavn", "Ans. Asp", "Født. Dato", "Rullenr.")
HEADER_5 = HEADER_6[:5]


def make_pdf(path, header, rows):
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    table = Table([list(header)] + [list(r) for r in rows])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    doc.build([
        Paragraph("Ansiennitetsliste 20.10.2026 Stasjoneringssted: OSLO", styles["Normal"]),
        table,
    ])
    return str(path)


class TestColumnLayouts:
    def test_six_column_pdf_keeps_rullenummer(self, tmp_path):
        pdf = make_pdf(tmp_path / "six.pdf", HEADER_6, [
            ("1", "Nordmann", "Ola", "01.01.2020", "02.02.1990", "555"),
        ])
        rows = scrape_employees(pdf)
        assert len(rows) == 1
        assert rows[0]["seniority_nr"] == 1
        assert rows[0]["etternavn"] == "Nordmann"
        assert rows[0]["rullenummer"] == "555"
        assert rows[0]["stasjoneringssted"] == "OSLO"

    def test_five_column_pdf_gives_empty_rullenummer(self, tmp_path):
        pdf = make_pdf(tmp_path / "five.pdf", HEADER_5, [
            ("1", "Nordmann", "Ola", "01.01.2020", "02.02.1990"),
            ("2", "Hansen", "Kari", "03.03.2021", "04.04.1991"),
        ])
        rows = scrape_employees(pdf)
        assert [r["seniority_nr"] for r in rows] == [1, 2]
        assert all(r["rullenummer"] == "" for r in rows)
        assert rows[1]["ans_dato"] == "03.03.2021"
        assert rows[1]["fodt_dato"] == "04.04.1991"


class TestCleanDate:
    """Long first names overlap the Ans. Asp cell in the real PDF's text
    layer, so pdfplumber hands back name letters interleaved with the date."""

    @pytest.mark.parametrize("raw, expected", [
        ("05.03.2001", "05.03.2001"),
        (" 05.03.2001\n", "05.03.2001"),
        ("e2s0.11.2000", "20.11.2000"),
        ("G0.7 .03.2022", "07.03.2022"),
        ("G2.5.04.2024", "25.04.2024"),
    ])
    def test_recovers_date(self, raw, expected):
        assert _clean_date(raw) == expected

    @pytest.mark.parametrize("raw", ["", None, "ukjent", "1.2.3"])
    def test_non_dates_pass_through_stripped(self, raw):
        assert _clean_date(raw) == (raw or "").strip()
