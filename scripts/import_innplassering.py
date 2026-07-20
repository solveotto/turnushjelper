#!/usr/bin/env python3
"""Import shift assignment data from an Innplassering PDF into the database.

Usage:
    python scripts/import_innplassering.py --year R26
    python scripts/import_innplassering.py --year R26 --pdf-path custom/path.pdf
"""

import argparse
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Deliberately no os.environ.setdefault("DB_TYPE", ...) here: config.py's
# load_dotenv() does not override an already-set env var, so forcing a
# default here BEFORE .env loads would silently shadow a real DB_TYPE=mysql
# in production and redirect every write to an empty local SQLite file
# instead (found 2026-07-20 via scripts/check_7th_drivers.py — see
# TODO_forensic_audit.md Task 0.1). Let config.py's own load_dotenv() +
# its own internal default handle it.


def main():
    parser = argparse.ArgumentParser(description="Import Innplassering PDF into database")
    parser.add_argument("--year", required=True, help="Year identifier (e.g. R26)")
    parser.add_argument("--pdf-path", help="Custom path to Innplassering PDF (optional)")
    args = parser.parse_args()

    year_id = args.year.upper()

    from config import AppConfig
    from app.services.turnus_service import get_turnus_set_by_year
    from app.services.innplassering_service import import_innplassering
    from app.utils import protected_paths

    # Print which DB this is actually about to write to — a wrong DB_TYPE
    # here fails loudly instead of silently writing to an unrelated
    # (and possibly empty) database.
    print(f"DB_TYPE={AppConfig.DB_TYPE}")

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
        # PII file — lives in instance/protected/, never under app/static/.
        pdf_path = protected_paths.innplassering_pdf_path(year_id)

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
