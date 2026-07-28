#!/usr/bin/env python3
"""Render one strekliste shift to a PNG so ruler alignment can be eyeballed.

A dev utility, not a test — the automated checks live in
`tests/test_strekliste_geometry.py`, which asserts the golden hour anchors and
the rendered width. Use this when those fail and you want to *look* at the
output, e.g. after swapping a streker PDF.

    venv/bin/python scripts/render_shift_preview.py                 # first shift, r26
    venv/bin/python scripts/render_shift_preview.py 1426            # a specific shift
    venv/bin/python scripts/render_shift_preview.py 1426 --version r25
    venv/bin/python scripts/render_shift_preview.py --out /tmp/x.png

Ruler and crop geometry are auto-calibrated from the hour labels printed in the
PDF (`compute_page_geometry`). If alignment is off, check
`get_hour_label_positions` against that PDF rather than re-tuning the fallback
constants.
"""

import argparse
import os
import sys

# Add project root to path (go up 2 levels: scripts -> project_root)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.utils.pdf.strekliste_generator import (  # noqa: E402
    compute_page_geometry,
    get_all_shifts,
    get_paths,
    render_shift_image,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "shift_nr", nargs="?", help="Shift number; defaults to the first in the PDF"
    )
    parser.add_argument("--version", default="r26", help="Turnus version (default: r26)")
    parser.add_argument(
        "--out",
        default="shift_preview.png",
        help="Output path (default: ./shift_preview.png)",
    )
    args = parser.parse_args()

    paths = get_paths(args.version)
    if not paths["pdf_exists"]:
        print(f"PDF not found at: {paths['pdf_path']}")
        return 1

    shift_nr = args.shift_nr
    if shift_nr is None:
        shifts = get_all_shifts(args.version)
        if not shifts:
            print("No shifts found in PDF")
            return 1
        shift_nr = shifts[0]["nr"]
        print(f"Using first shift found: {shift_nr}")

    # Report calibration up front — a False here explains a bad-looking render.
    import fitz

    doc = fitz.open(paths["pdf_path"])
    geo = compute_page_geometry(doc[0], 4)
    doc.close()
    print(f"Calibrated from PDF hour labels: {geo['calibrated']}")

    print(f"Rendering shift {shift_nr} ({args.version})...")
    img_bytes = render_shift_image(shift_nr, args.version)
    if img_bytes is None:
        print(f"Failed to render shift {shift_nr}")
        return 1

    with open(args.out, "wb") as f:
        f.write(img_bytes)
    print(f"Saved {len(img_bytes)} bytes to: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
