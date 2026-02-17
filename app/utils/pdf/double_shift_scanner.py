"""
Double Shift Scanner

Scans a strekliste PDF for shift markers:
- "<<" markers indicate dobbelt tur (a shift that is a continuation of the shift above it)
- "**" markers indicate delt dagsverk (split work day)

Outputs a JSON file with both types of markers.
"""

import json
import os
import re
import sys
from typing import TypedDict

# from pandas.core.array_algos.transforms import shift

# Allow running as standalone script
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

import numpy as np
import pdfplumber
from PIL import Image

from config import AppConfig

# Shift numbers appear in the leftmost column (consistent with strekliste_generator.py)
SHIFT_NR_VISUAL_X_MAX = 50
SHIFT_NR_PATTERN = re.compile(r"^(\d{4,5})(?:-.*)?$")
Y_MIN_FOR_MARKERS = 85  # pixels from top - filter out legend area


class DoubleShiftResult(TypedDict):
    dobbelt_tur: list[dict[str, str]]
    delt_dagsverk: list[str]


def find_separator_lines_from_image(
    img: Image.Image, min_thickness: int = 2
) -> list[int]:
    """
    Detect horizontal black separator lines in the image.
    Same logic as strekliste_generator.py - uses image brightness analysis.

    Args:
        img: PIL Image object
        min_thickness: Minimum line thickness in pixels

    Returns:
        List of y-positions (in image pixels) where thick black lines are found.
    """
    gray = img.convert("L")
    arr = np.array(gray)
    row_brightness = np.mean(arr, axis=1)

    threshold = 180
    dark_rows = np.where(row_brightness < threshold)[0]

    if len(dark_rows) == 0:
        return []

    # Group consecutive dark rows and filter by thickness
    lines = []
    start = dark_rows[0]
    prev = dark_rows[0]

    for row in dark_rows[1:]:
        if row - prev > 3:  # Gap indicates a new line
            thickness = prev - start + 1
            if thickness >= min_thickness:  # Only keep thick lines
                lines.append((start + prev) // 2)
            start = row
        prev = row

    # Don't forget the last group
    thickness = prev - start + 1
    if thickness >= min_thickness:
        lines.append((start + prev) // 2)

    return lines


def get_separator_lines(page, resolution: int = 72) -> list[float]:
    """
    Extract horizontal separator lines from a PDF page using image analysis.
    Uses the same approach as strekliste_generator.py.

    Args:
        page: pdfplumber page object
        resolution: DPI for rendering the page to image

    Returns:
        List of y-positions (in PDF coordinates) where separator lines are found.
    """
    # Render page to image
    img = page.to_image(resolution=resolution).original

    # Find separator lines in image coordinates
    img_lines = find_separator_lines_from_image(img, min_thickness=2)

    # Convert image y-coordinates to PDF coordinates
    # PDF coordinates: origin at bottom-left, y increases upward
    # Image coordinates: origin at top-left, y increases downward
    scale = img.height / page.height
    pdf_lines = []
    for img_y in img_lines:
        # Convert: pdf_y = page.height - (img_y / scale)
        # But pdfplumber uses top-left origin too, so just scale
        pdf_y = img_y / scale
        pdf_lines.append(pdf_y)

    return sorted(pdf_lines)


def find_row_for_y(
    y: float, separator_lines: list[float]
) -> tuple[float, float] | None:
    """
    Find which row a y-position belongs to based on separator lines.

    Returns:
        Tuple of (top_y, bottom_y) for the row, or None if not found.
    """
    if not separator_lines:
        return None

    # Find the separator above and below this y position
    lines_above = [line_y for line_y in separator_lines if line_y < y]
    lines_below = [line_y for line_y in separator_lines if line_y > y]

    top = max(lines_above) if lines_above else 0
    bottom = min(lines_below) if lines_below else float("inf")

    return (top, bottom)


def scan_double_shifts(pdf_path: str) -> DoubleShiftResult:
    """
    Scan a strekliste PDF for "<<" markers and identify double shift pairs.

    The "<<" marker sits on its own row between two shift rows, indicating
    that the shift below it is a continuation of the shift above it.

    Args:
        pdf_path: Path to the strekliste PDF file.

    Returns:
        Dict with 'dobbelt_tur' pairs and 'delt_dagsverk' shift numbers.
    """
    double_shifts = []
    delt_dagsverk_shifts = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=2)

            # Get separator lines for row-based matching
            separator_lines = get_separator_lines(page)

            # Separate shift numbers, "**" and "<<" markers
            shift_numbers = []
            dobbelttur_markers = []
            delt_dagsverk_markers = []

            # First pass: collect single * characters for pairing
            single_stars = []

            for word in words:
                text = word["text"].strip()
                x = word["x0"]
                y_mid = (word["top"] + word["bottom"]) / 2

                # Check 1: Is it a << marker?
                if text == "<<":
                    dobbelttur_markers.append({"y": y_mid, "x": x})

                # Check 2: Is it a ** marker? (multiple detection methods)
                # Filter by y (skip header legend)
                elif y_mid > Y_MIN_FOR_MARKERS:
                    # Method A: Exact match
                    if text == "**":
                        delt_dagsverk_markers.append({"y": y_mid, "x": x})
                    # Method B: Text contains ** (might be merged with other text)
                    elif "**" in text:
                        delt_dagsverk_markers.append({"y": y_mid, "x": x})
                    # Method C: Single * (collect for pairing)
                    elif text == "*":
                        single_stars.append({"y": y_mid, "x": x})

                # Check 3: Shift number
                shift_match = SHIFT_NR_PATTERN.match(text)
                if x < SHIFT_NR_VISUAL_X_MAX and shift_match:
                    shift_numbers.append(
                        {
                            "nr": text,
                            "nr_base": shift_match.group(1),
                            "y": y_mid,
                        }
                    )

            # Pair single stars only if immediately adjacent (forming **)
            # A single * character is typically ~5-6 pixels wide
            single_stars.sort(key=lambda s: (s["y"], s["x"]))
            used = set()
            for i, star1 in enumerate(single_stars):
                if i in used:
                    continue
                for j, star2 in enumerate(single_stars[i + 1 :], i + 1):
                    if j in used:
                        continue
                    # Must be same row (very close y) and immediately adjacent (x within ~8 pixels)
                    if (
                        abs(star1["y"] - star2["y"]) < 3
                        and abs(star1["x"] - star2["x"]) < 8
                    ):
                        delt_dagsverk_markers.append({"y": star1["y"], "x": star1["x"]})
                        used.add(i)
                        used.add(j)
                        break

            # Sort shift numbers by y position (top to bottom)
            shift_numbers.sort(key=lambda s: s["y"])

            # For each "<<" marker, find the closest shift above and below it
            for marker in dobbelttur_markers:
                above_shift = None
                below_shift = None

                for s in shift_numbers:
                    if s["y"] < marker["y"]:
                        # Closest shift above the marker
                        if above_shift is None or s["y"] > above_shift["y"]:
                            above_shift = s
                    elif s["y"] > marker["y"]:
                        # Closest shift below the marker
                        if below_shift is None or s["y"] < below_shift["y"]:
                            below_shift = s

                if above_shift is None or below_shift is None:
                    continue

                pair = (above_shift["nr"], below_shift["nr"])
                double_shifts.append(pair)

            # For each "**" marker, find the CLOSEST shift in the same row
            for marker in delt_dagsverk_markers:
                marker_row = find_row_for_y(marker["y"], separator_lines)

                matching_shift = None
                closest_diff_in_row = float("inf")

                if marker_row:
                    # Find the CLOSEST shift within the same row
                    for s in shift_numbers:
                        shift_row = find_row_for_y(s["y"], separator_lines)
                        if shift_row and marker_row == shift_row:
                            diff = abs(s["y"] - marker["y"])
                            if diff < closest_diff_in_row:
                                closest_diff_in_row = diff
                                matching_shift = s

                if matching_shift:
                    delt_dagsverk_shifts.append(matching_shift["nr"])
                else:
                    # Fallback: find the closest shift (above or below)
                    closest_shift = None
                    closest_diff = float("inf")

                    for s in shift_numbers:
                        diff = abs(s["y"] - marker["y"])
                        if diff < closest_diff:
                            closest_diff = diff
                            closest_shift = s

                    # Use a moderate tolerance - the marker should be in the same row
                    if closest_shift and closest_diff < 35:
                        delt_dagsverk_shifts.append(closest_shift["nr"])

    # Deduplicate (same pair can appear on multiple pages)
    seen = set()
    unique = []
    for pair in double_shifts:
        if pair not in seen:
            seen.add(pair)
            unique.append({"first_shift": pair[0], "second_shift": pair[1]})

    return {"dobbelt_tur": unique, "delt_dagsverk": list(set(delt_dagsverk_shifts))}


def main():
    version = "r26"
    pdf_path = os.path.join(
        AppConfig.turnusfiler_dir, version, "streklister", f"{version}_streker.pdf"
    )
    output_path = os.path.join(
        AppConfig.turnusfiler_dir, version, f"double_shifts_{version}.json"
    )

    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}")
        sys.exit(1)

    print(f"Scanning {pdf_path}...")
    result = scan_double_shifts(pdf_path)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Found {len(result['dobbelt_tur'])} dobbelt tur pairs.")
    print(f"Found {len(result['delt_dagsverk'])} delt dagsverk shifts.")
    print(f"Output written to {output_path}")


if __name__ == "__main__":
    main()
