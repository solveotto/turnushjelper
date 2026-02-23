"""Scrape employee seniority list from ansinitet.pdf.

Parses tables with columns:
  Nr | Etternavn | For- og mellomnavn | Ans. Asp | Født. Dato | Rullenr.

and extracts the stasjoneringssted from each page header.
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


def scrape_employees(pdf_path) -> list[dict]:
    """Return a list of employee dicts scraped from the PDF.

    Each dict has keys:
        seniority_nr, etternavn, fornavn, ans_dato, fodt_dato,
        rullenummer, stasjoneringssted
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
                    "etternavn": (row[1] or "").strip(),
                    "fornavn": (row[2] or "").strip(),
                    "ans_dato": (row[3] or "").strip(),
                    "fodt_dato": (row[4] or "").strip(),
                    "rullenummer": (row[5] or "").strip(),
                    "stasjoneringssted": stasjoneringssted,
                })

    logger.info("employee_scraper: scraped %d employees from %s", len(employees), pdf_path)
    return employees
