"""
Innplassering Scraper - Parse "Innplassering R26.pdf" into structured records.

The PDF has four sections:
  - Faste turer: Tur 1–40
  - Rammeturer: Ramme 1–13
  - Utland: Utland 1–4
  - 7.fører: links a driver (rullenummer) to a Tur they serve as 7th driver

Layout: multiple section headers per row (e.g. "Tur 1", "Tur 2", ... "Tur 5").
Each section has a mini-table with unlabeled columns:
  linjenummer | Ans | Fornavn | Etternavn | Rullenr
(for 7.fører also: Tur | L)

The section header "Tur N" appears above the right half of its mini-table.
The linjenr column and Ans column are to the LEFT of the header word.

"Ikke søkbar" rows: ans="x" or rullenr="0" — skip these.
"""

import json
import logging
import re

import pdfplumber

logger = logging.getLogger(__name__)

# Words that are column headers — skip rows containing these
_COL_HEADERS = {"Ans", "Fornavn", "Etternavn", "Rullenr", "Tur", "L"}


def _build_shift_lookup(json_path: str) -> dict[str, str]:
    """Build mapping from 'Type:N' key to canonical shift title."""
    with open(json_path, "r", encoding="utf-8") as f:
        turnus_data = json.load(f)

    lookup: dict[str, str] = {}
    for entry in turnus_data:
        for title in entry.keys():
            m = re.match(r"^OSL_(\d+)(?:_|$)", title)
            if m:
                lookup[f"Tur:{int(m.group(1))}"] = title
                continue
            m = re.match(r"^OSL_Ramme_(\d+)", title)
            if m:
                lookup[f"Ramme:{int(m.group(1))}"] = title
                continue
            m = re.match(r"^OSL_Utland_(\d+)", title)
            if m:
                lookup[f"Utland:{int(m.group(1))}"] = title
                continue
    return lookup


def _resolve_shift(section_type: str, number: int, lookup: dict[str, str]) -> str | None:
    return lookup.get(f"{section_type}:{number}")


def _group_words_into_rows(words: list[dict], y_tolerance: float = 3.0) -> list[list[dict]]:
    """Group words by approximate Y position (top coordinate)."""
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    current_row: list[dict] = [sorted_words[0]]
    current_top = sorted_words[0]["top"]

    for word in sorted_words[1:]:
        if abs(word["top"] - current_top) <= y_tolerance:
            current_row.append(word)
        else:
            rows.append(sorted(current_row, key=lambda w: w["x0"]))
            current_row = [word]
            current_top = word["top"]

    if current_row:
        rows.append(sorted(current_row, key=lambda w: w["x0"]))
    return rows


def _extract_ans_nr(token: str) -> int | None:
    """Extract leading integer from a token that may have ans+fornavn merged (e.g. '293Henrik')."""
    m = re.match(r"^(\d+)", token)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def _parse_data_row_normal(
    texts: list[str],
    shift_title: str,
) -> dict | None:
    """Parse one data row for a normal (non-7.fører) section.

    Column layout: linjenr | Ans | [names...] | Rullenr
    """
    # Skip column header rows
    if any(t in _COL_HEADERS for t in texts):
        return None
    if len(texts) < 3:
        return None

    linjenr_str = texts[0]
    ans_token = texts[1]
    rullenr_str = texts[-1]

    # Skip "Ikke søkbar": ans col starts with 'x' or rullenr is '0'
    if ans_token.lower().startswith("x"):
        return None
    if rullenr_str == "0":
        return None

    # Validate rullenr is numeric
    if not rullenr_str.isdigit():
        return None

    try:
        linjenr = int(linjenr_str)
    except (ValueError, TypeError):
        return None  # first token must be the linjenr digit

    ans_nr = _extract_ans_nr(ans_token)

    return {
        "rullenummer": rullenr_str,
        "shift_title": shift_title,
        "linjenummer": linjenr,
        "ans_nr": ans_nr,
        "is_7th_driver": 0,
    }


def _parse_data_row_7forer(
    texts: list[str],
    lookup: dict[str, str],
) -> dict | None:
    """Parse one data row from the 7.fører section.

    Column layout: linjenr | Ans | Fornavn | Etternavn | Rullenr | Tur | L
    We need Rullenr (index 4) and Tur (index 5 or a token that matches 'Tur N').
    """
    # Skip column header rows
    if any(t in _COL_HEADERS for t in texts):
        return None
    if len(texts) < 6:
        return None

    linjenr_str = texts[0]
    ans_token = texts[1]

    # Skip "Ikke søkbar"
    if ans_token.lower().startswith("x"):
        return None

    # Validate first token is a digit (linjenr)
    try:
        linjenr = int(linjenr_str)
    except (ValueError, TypeError):
        return None

    # Find the rullenr: it's a 5-digit number. Scan from right for it.
    rullenr_str = None
    tur_str = None
    for i in range(len(texts) - 1, 1, -1):
        t = texts[i]
        if re.match(r"^Tur\s+\d+$", t):
            tur_str = t
            continue
        if t.isdigit() and len(t) >= 4:
            rullenr_str = t
            # The Tur value should come after rullenr (to the right)
            # Check remaining tokens for Tur pattern
            for j in range(i + 1, len(texts)):
                if re.match(r"^Tur\s+\d+$", texts[j]):
                    tur_str = texts[j]
                    break
                if texts[j].isdigit() and int(texts[j]) <= 40:
                    # bare number, likely the tur number
                    tur_str = f"Tur {texts[j]}"
                    break
            break

    if not rullenr_str or not tur_str:
        return None
    if rullenr_str == "0":
        return None

    # Resolve tur shift
    m = re.match(r"^Tur\s+(\d+)$", tur_str)
    if not m:
        return None
    tur_number = int(m.group(1))
    tur_shift_title = _resolve_shift("Tur", tur_number, lookup)
    if tur_shift_title is None:
        tur_shift_title = f"Tur_{tur_number}"

    ans_nr = _extract_ans_nr(ans_token)

    return {
        "rullenummer": rullenr_str,
        "shift_title": tur_shift_title,
        "linjenummer": linjenr,
        "ans_nr": ans_nr,
        "is_7th_driver": 1,
    }


def scrape_innplassering(pdf_path: str, json_path: str) -> list[dict]:
    """Scrape Innplassering PDF and return a list of assignment dicts.

    Each dict: {rullenummer, shift_title, linjenummer, ans_nr, is_7th_driver}
    """
    lookup = _build_shift_lookup(json_path)

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(x_tolerance=3, y_tolerance=2)

    # Group all words into rows by Y position
    all_rows = _group_words_into_rows(words, y_tolerance=3.0)

    # --- Detect section headers ---
    # Headers are words "Tur"/"Ramme"/"Utland" followed immediately by a digit on the same Y row,
    # or the literal token "7.fører".
    sections: list[dict] = []
    for row_idx, row in enumerate(all_rows):
        row_texts = [w["text"] for w in row]
        i = 0
        while i < len(row_texts):
            text = row_texts[i]
            if text in ("Tur", "Ramme", "Utland") and i + 1 < len(row_texts) and row_texts[i + 1].isdigit():
                sections.append({
                    "type": text,
                    "number": int(row_texts[i + 1]),
                    "header_x0": row[i]["x0"],
                    "top": row[i]["top"],
                    "row_index": row_idx,
                })
                i += 2
                continue
            elif text == "7.fører":
                sections.append({
                    "type": "7.fører",
                    "number": 0,
                    "header_x0": row[i]["x0"],
                    "top": row[i]["top"],
                    "row_index": row_idx,
                })
            i += 1

    if not sections:
        logger.warning("No section headers found in %s", pdf_path)
        return []

    logger.info("Found %d section headers", len(sections))

    # --- Compute X boundaries for each section using midpoints ---
    # Sections on the same header row are grouped and sorted by x position.
    # Each section's left boundary = midpoint to its left neighbour (or 0).
    # Each section's right boundary = midpoint to its right neighbour (or page width).
    page_width = float(page.width)

    sections.sort(key=lambda s: (s["top"], s["header_x0"]))

    # Group by header row top
    from itertools import groupby
    for _, grp in groupby(sections, key=lambda s: s["top"]):
        row_secs = list(grp)
        row_secs.sort(key=lambda s: s["header_x0"])
        for j, sec in enumerate(row_secs):
            left = (row_secs[j - 1]["header_x0"] + sec["header_x0"]) / 2 if j > 0 else 0.0
            right = (sec["header_x0"] + row_secs[j + 1]["header_x0"]) / 2 if j + 1 < len(row_secs) else page_width
            sec["x_left"] = left
            sec["x_right"] = right

    # --- Determine data Y range for each section ---
    # Data is the rows between this header's Y and the next header row's Y.
    header_tops = sorted(set(s["top"] for s in sections))
    top_to_data_range: dict[float, tuple[float, float]] = {}
    for i, ht in enumerate(header_tops):
        data_start = ht + 5
        data_end = header_tops[i + 1] if i + 1 < len(header_tops) else page_width  # reuse as large number
        top_to_data_range[ht] = (data_start, data_end)

    # --- For each section, collect words and parse data rows ---
    results: list[dict] = []

    for sec in sections:
        data_y_start, data_y_end = top_to_data_range[sec["top"]]
        x_left = sec["x_left"]
        x_right = sec["x_right"]

        section_words = [
            w for w in words
            if (data_y_start <= w["top"] < data_y_end
                and x_left <= w["x0"] < x_right)
        ]

        data_rows = _group_words_into_rows(section_words, y_tolerance=3.0)
        is_7th = sec["type"] == "7.fører"

        if is_7th:
            shift_title = None
        else:
            shift_title = _resolve_shift(sec["type"], sec["number"], lookup)
            if shift_title is None:
                shift_title = f"{sec['type']}_{sec['number']}"

        for row in data_rows:
            texts = [w["text"] for w in row]
            if is_7th:
                rec = _parse_data_row_7forer(texts, lookup)
            else:
                rec = _parse_data_row_normal(texts, shift_title)

            if rec is not None:
                results.append(rec)

    logger.info("Scraped %d assignment records from %s", len(results), pdf_path)
    return results
