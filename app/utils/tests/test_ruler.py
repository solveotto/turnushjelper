"""
Test script to quickly iterate on hour ruler alignment.
Run this script and check the output PNG to adjust the ratios.
"""

import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.pdf.strekliste_generator import render_shift_image, get_all_shifts, get_paths

# Configuration - adjust these values
VERSION = "r26"  # Change to your turnus version
SHIFT_NR = None  # Set to a specific shift number, or None to use the first one found

def main():
    paths = get_paths(VERSION)

    if not paths['pdf_exists']:
        print(f"PDF not found at: {paths['pdf_path']}")
        return

    # Get a shift number to test with
    shift_nr = SHIFT_NR
    if shift_nr is None:
        shifts = get_all_shifts(VERSION)
        if not shifts:
            print("No shifts found in PDF")
            return
        shift_nr = shifts[0]['nr']
        print(f"Using first shift found: {shift_nr}")

    # Render the shift image
    print(f"Rendering shift {shift_nr}...")
    img_bytes = render_shift_image(shift_nr, VERSION)

    if img_bytes is None:
        print(f"Failed to render shift {shift_nr}")
        return

    # Save to test file
    output_path = os.path.join(os.path.dirname(__file__), "test_ruler_output.png")
    with open(output_path, 'wb') as f:
        f.write(img_bytes)

    print(f"Saved to: {output_path}")
    print("\nRuler/crop geometry is auto-calibrated from the hour labels")
    print("printed in the PDF (see compute_page_geometry in strekliste_generator.py).")
    print("If alignment is off, check get_hour_label_positions against this PDF.")

if __name__ == "__main__":
    main()
