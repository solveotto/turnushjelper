"""Scrape employee seniority list from ansinitet.pdf.

Parses tables with columns:
  Nr | Etternavn | For- og mellomnavn | Ans. Asp | Født. Dato | [Rullenr.]

The ``Rullenr.`` column disappeared from the employer's export in October
2026, so it is optional: rows from a five-column list get ``rullenummer == ""``
and the sync matches them on name/dates instead.

The stasjoneringssted is read from each page header.
"""
import logging
import re

import pdfplumber

logger = logging.getLogger(__name__)


def scrape_pdf_date(pdf_path) -> str | None:
    """Extract the document date (DD.MM.YYYY) from the first page header.

    Returns the date string if found, otherwise None.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return None
            text = pdf.pages[0].extract_text() or ""
            match = re.search(r"\b(\d{2}\.\d{2}\.\d{4})\b", text)
            if match:
                return match.group(1)
    except Exception as e:
        logger.warning("employee_scraper: could not extract date from %s: %s", pdf_path, e)
    return None


def _cell(row: list, index: int) -> str:
    """Return the stripped cell text, or "" when the column is absent."""
    if index >= len(row):
        return ""
    return (row[index] or "").strip()


def _clean_date(cell: str | None) -> str:
    """Normalise a date cell to DD.MM.YYYY.

    In the real PDF long first names overflow into the Ans. Asp column, and
    pdfplumber returns the name letters interleaved with the date digits
    (``e2s0.11.2000``). The digits keep their order, so eight digits are
    enough to rebuild the date. Anything else is returned stripped.
    """
    text = (cell or "").strip()
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        return f"{digits[:2]}.{digits[2:4]}.{digits[4:]}"
    return text


def scrape_employees(pdf_path) -> list[dict]:
    """Return a list of employee dicts scraped from the PDF.

    Each dict has keys:
        seniority_nr, etternavn, fornavn, ans_dato, fodt_dato,
        rullenummer, stasjoneringssted

    ``rullenummer`` is "" when the PDF has no Rullenr. column.
    """
    employees = []
    with pdfplumber.open(pdf_path) as pdf:
        stasjoneringssted = "OSLO"  # sensible default
        for page in pdf.pages:
            # Try to extract stasjoneringssted from page header text
            text = page.extract_text() or ""
            match = re.search(
                r"Stasjoner(?:ings)?sted:\s*(\S+)", text, re.IGNORECASE
            )
            if match:
                stasjoneringssted = match.group(1).strip()

            table = page.extract_table()
            if not table:
                continue

            for row in table:
                if not row or not row[0]:
                    continue
                # Skip header rows — "Nr" is not a digit
                try:
                    nr = int(str(row[0]).strip())
                except (ValueError, TypeError):
                    continue

                employees.append({
                    "seniority_nr": nr,
                    "etternavn": _cell(row, 1),
                    "fornavn": _cell(row, 2),
                    "ans_dato": _clean_date(_cell(row, 3)),
                    "fodt_dato": _clean_date(_cell(row, 4)),
                    "rullenummer": _cell(row, 5),
                    "stasjoneringssted": stasjoneringssted,
                })

    logger.info("employee_scraper: scraped %d employees from %s", len(employees), pdf_path)
    return employees
