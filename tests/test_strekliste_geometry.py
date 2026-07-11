"""
Tests for strekliste PNG geometry calibration.

The hour ruler and crop box must be derived from the hour labels printed
inside the strekliste PDF itself (all pages carry a "0".."23" header row),
not from hardcoded ratios. Golden values below are measured against the
real in-repo r26 PDF (hour 0 label at visual x=103.5, spacing 30.0 pt/hour).
"""

import io
import os

import numpy as np
import pytest

from app.utils.pdf import strekliste_generator as sg

fitz = pytest.importorskip("fitz")
PIL_Image = pytest.importorskip("PIL.Image")

PDF_PATH = sg.get_paths("r26")["pdf_path"]

requires_pdf = pytest.mark.skipif(
    not os.path.exists(PDF_PATH), reason="r26 strekliste PDF not present"
)


# ---------------------------------------------------------------------------
# Pure clustering logic: _pick_hour_row(spans) with spans = (text, x, y)
# ---------------------------------------------------------------------------


def _make_hour_row(y=95.0, x0=103.5, spacing=30.0):
    return [(str(h), x0 + h * spacing, y) for h in range(24)]


class TestPickHourRow:
    def test_finds_complete_row_among_decoys(self):
        spans = _make_hour_row()
        # Decoys: shift numbers, kjøredager digits, times at other y positions
        spans += [
            ("1201", 30.0, 150.0),
            ("1", 60.0, 150.0),  # kjøredager column
            ("12345", 60.0, 200.0),
            ("5", 300.0, 400.0),
            ("23", 500.0, 700.0),
        ]
        result = sg._pick_hour_row(spans)
        assert result is not None
        assert sorted(result.keys()) == list(range(24))
        assert result[0] == pytest.approx(103.5)
        assert result[23] == pytest.approx(103.5 + 23 * 30.0)

    def test_incomplete_row_returns_none(self):
        spans = _make_hour_row()[:-1]  # missing hour 23
        assert sg._pick_hour_row(spans) is None

    def test_topmost_complete_row_wins(self):
        top = _make_hour_row(y=95.0)
        bottom = _make_hour_row(y=600.0, x0=110.0)
        result = sg._pick_hour_row(bottom + top)
        assert result[0] == pytest.approx(103.5)

    def test_row_with_jittered_y_is_still_grouped(self):
        spans = [
            (str(h), 103.5 + h * 30.0, 95.0 + (0.9 if h % 2 else -0.9))
            for h in range(24)
        ]
        result = sg._pick_hour_row(spans)
        assert result is not None
        assert sorted(result.keys()) == list(range(24))

    def test_unevenly_spaced_fake_row_is_rejected(self):
        # 24 hour-like digits at one y but at random x spacing is not a ruler
        xs = [10, 11, 13, 700, 20, 300, 42, 55, 60, 61, 62, 90,
              95, 400, 410, 500, 120, 130, 200, 210, 220, 230, 600, 650]
        spans = [(str(h), float(xs[h]), 95.0) for h in range(24)]
        assert sg._pick_hour_row(spans) is None


class TestHourRulerDigits:
    def test_digits_scale_with_zoom(self):
        # Hour digits must render at a size proportional to the hour spacing,
        # not at the 10 px PIL default-font fallback size.
        zoom = 4
        hour_px = [326 + h * 119.8 for h in range(24)]
        ruler = sg.create_hour_ruler(3221, hour_px, zoom=zoom)
        arr = np.array(ruler.convert("L"))
        dark_rows = np.where((arr < 128).any(axis=1))[0]
        assert len(dark_rows) > 0
        glyph_height = dark_rows.max() - dark_rows.min() + 1
        assert glyph_height >= 18


# ---------------------------------------------------------------------------
# Golden tests against the real PDF
# ---------------------------------------------------------------------------


@requires_pdf
class TestHourLabelPositionsGolden:
    def test_page0_positions(self):
        doc = fitz.open(PDF_PATH)
        try:
            pos = sg.get_hour_label_positions(doc[0])
        finally:
            doc.close()
        assert pos is not None
        assert sorted(pos.keys()) == list(range(24))
        xs = [pos[h] for h in range(24)]
        assert xs == sorted(xs)
        assert pos[0] == pytest.approx(103.5, abs=1.0)
        assert pos[23] == pytest.approx(793.5, abs=1.0)

    def test_all_pages_have_same_hour_row(self):
        doc = fitz.open(PDF_PATH)
        try:
            first = sg.get_hour_label_positions(doc[0])
            last = sg.get_hour_label_positions(doc[len(doc) - 1])
        finally:
            doc.close()
        assert first is not None and last is not None
        assert first[0] == pytest.approx(last[0], abs=1.0)
        assert first[23] == pytest.approx(last[23], abs=1.0)


@requires_pdf
class TestPageGeometryGolden:
    def test_crop_covers_full_timeline(self):
        zoom = 4
        doc = fitz.open(PDF_PATH)
        try:
            page = doc[0]
            pos = sg.get_hour_label_positions(page)
            geo = sg.compute_page_geometry(page, zoom)
        finally:
            doc.close()
        assert geo["calibrated"] is True
        # Right crop edge must lie beyond the hour 23 label (no cut-off)
        assert geo["x_right"] > pos[23] * zoom
        assert geo["x_left"] == int(22 * zoom)
        # Ruler positions are relative to the cropped image
        assert geo["hour_px"][0] == pytest.approx(pos[0] * zoom - geo["x_left"], abs=2)
        assert geo["hour_px"][23] == pytest.approx(
            pos[23] * zoom - geo["x_left"], abs=2
        )

    def test_rendered_shift_includes_evening_hours(self):
        png = sg.render_shift_image("1426", "r26")
        assert png is not None
        img = PIL_Image.open(io.BytesIO(png))
        # Old broken crop produced 2196 px wide images (cut at ~15:40);
        # the full timeline at zoom 4 is > 3000 px wide.
        assert img.width > 3000
