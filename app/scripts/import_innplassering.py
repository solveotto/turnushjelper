#!/usr/bin/env python3
"""Import shift assignment data from an Innplassering PDF into the database.

Usage:
    python app/scripts/import_innplassering.py --year R26
    python app/scripts/import_innplassering.py --year R26 --pdf-path custom/path.pdf
"""

import argparse
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

os.environ.setdefault("DB_TYPE", "sqlite")


def main():
    parser = argparse.ArgumentParser(description="Import Innplassering PDF into database")
    parser.add_argument("--year", required=True, help="Year identifier (e.g. R26)")
    parser.add_argument("--pdf-path", help="Custom path to Innplassering PDF (optional)")
    args = parser.parse_args()

    year_id = args.year.upper()

    from app.services.turnus_service import get_turnus_set_by_year
    from app.services.innplassering_service import import_innplassering
    from config import AppConfig

    turnus_set = get_turnus_set_by_year(year_id)
    if not turnus_set:
        print(f"Error: No turnus set found for year '{year_id}'")
        sys.exit(1)

    turnus_set_id = turnus_set["id"]
    json_path = turnus_set.get("turnus_file_path")
    if not json_path or not os.path.exists(json_path):
        print(f"Error: Turnus JSON not found: {json_path}")
        sys.exit(1)

    if args.pdf_path:
        pdf_path = args.pdf_path
    else:
        version = year_id.lower()
        pdf_path = os.path.join(AppConfig.static_dir, "turnusfiler", version, f"Innplassering {year_id}.pdf")

    if not os.path.exists(pdf_path):
        print(f"Error: Innplassering PDF not found: {pdf_path}")
        sys.exit(1)

    print(f"Importing innplassering for {year_id}...")
    print(f"  PDF:  {pdf_path}")
    print(f"  JSON: {json_path}")

    success, message = import_innplassering(pdf_path, turnus_set_id, json_path)
    print(f"{'OK' if success else 'FAIL'}: {message}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
