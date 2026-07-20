#!/usr/bin/env python3
"""Verify 7.fører linjenummer data after an innplassering import.

7.fører (7th driver) rows in the Innplassering PDF have their own column
layout; a past parser bug stored a sequential row counter (1..10, 1..N) as
the linjenummer instead of the real "L" column value. That bug pattern is
NOT reliably caught by a bare "is linjenummer in 1-6" check: found
2026-07-20, when a stale (non-restarted) server process wrote row-counter
values for ALL 10 rows, but 6 of them coincidentally had row-counter values
that were themselves also in 1-6, so a range check alone missed 6 of the 10
bad rows and only flagged the 4 where row-counter > 6.

The reliable check is to re-parse the PDF fresh, right now, with whatever
code is actually running this script, and compare row-for-row against what's
stored in the DB — a coincidental range match can't fool that. This script
does the fresh-parse comparison as the primary check, and falls back to the
weaker 1-6 range check only if the PDF file isn't available to re-parse.

Usage:
    venv/bin/python scripts/check_7th_drivers.py --year R26
"""

import argparse
import glob
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Deliberately no os.environ.setdefault("DB_TYPE", ...) here: config.py's
# load_dotenv() does not override an already-set env var, so forcing a
# default here BEFORE .env loads would silently shadow a real DB_TYPE=mysql
# in production and redirect every query to an empty local SQLite file
# instead (this bit us once — see TODO_forensic_audit.md Task 0.1). Let
# config.py's own load_dotenv() + its own internal default handle it.

VALID_LINJER = {1, 2, 3, 4, 5, 6}


def main():
    parser = argparse.ArgumentParser(
        description="Check 7.fører linjenummer values for a turnus set"
    )
    parser.add_argument("--year", required=True, help="Year identifier (e.g. R26)")
    args = parser.parse_args()
    year_id = args.year.upper()

    from config import AppConfig
    from app.database import get_db_session
    from app.models import Innplassering, TurnusSet
    from app.utils import protected_paths

    # Print which DB this is actually about to hit — a wrong DB_TYPE here
    # (e.g. accidentally defaulting to sqlite in production) fails loudly
    # instead of silently querying an unrelated empty database.
    print(f"DB_TYPE={AppConfig.DB_TYPE}")

    db = get_db_session()
    try:
        turnus_set = db.query(TurnusSet).filter_by(year_identifier=year_id).first()
        if not turnus_set:
            available = [t.year_identifier for t in db.query(TurnusSet).all()]
            print(f"Error: No turnus set found for year '{year_id}'")
            print(f"Available year_identifier values: {available}")
            sys.exit(1)

        rows = (
            db.query(Innplassering)
            .filter_by(turnus_set_id=turnus_set.id, is_7th_driver=1)
            .order_by(Innplassering.rullenummer)
            .all()
        )

        print(f"{len(rows)} 7.fører row(s) for {year_id} in the DB")
        print("=" * 60)

        if not rows:
            print("No 7.fører rows found — nothing to check.")
            sys.exit(0)

        # --- Primary check: fresh dry-run parse vs DB, row for row ---
        pdf_path = protected_paths.innplassering_pdf_path(year_id)
        fresh_by_rullenr = None
        if os.path.exists(pdf_path):
            json_path = turnus_set.turnus_file_path
            if not json_path or not os.path.exists(json_path):
                matches = glob.glob(f"**/turnus_schedule_{year_id}.json", recursive=True)
                json_path = matches[0] if matches else None
            if json_path:
                from app.utils.pdf.innplassering_scraper import scrape_innplassering
                fresh_records = scrape_innplassering(pdf_path, json_path)
                fresh_by_rullenr = {
                    r["rullenummer"]: r["linjenummer"]
                    for r in fresh_records if r["is_7th_driver"] == 1
                }

        if fresh_by_rullenr is None:
            print(
                "(Could not re-parse the PDF for comparison — falling back to the "
                "weaker 1-6 range check only. This CANNOT catch a wrong value that "
                "happens to also be in 1-6.)\n"
            )

        bad_rows = []
        for r in rows:
            in_range = r.linjenummer in VALID_LINJER
            if fresh_by_rullenr is not None:
                fresh_val = fresh_by_rullenr.get(r.rullenummer)
                matches_fresh = fresh_val == r.linjenummer
                flag = "" if matches_fresh else f"  <-- MISMATCH (fresh parse says {fresh_val})"
                if not matches_fresh:
                    bad_rows.append(r)
            else:
                flag = "" if in_range else "  <-- INVALID (outside 1-6)"
                if not in_range:
                    bad_rows.append(r)
            print(f"rullenummer={r.rullenummer:>6}  linje={r.linjenummer}  tur={r.shift_title}{flag}")

        print("=" * 60)
        if bad_rows:
            print(
                f"\n⚠ {len(bad_rows)} row(s) are wrong. This is the row-counter bug "
                "pattern (sequential 1..N instead of the real 'L' column) — re-run "
                "the import. If it was just re-run and this still fails, the running "
                "app process likely wasn't restarted after a code fix landed on disk "
                "(Python doesn't hot-reload changed modules) — restart the service "
                "and re-run the import again."
            )
            sys.exit(1)
        else:
            print("\n✓ All linjenummer values are correct.")
            sys.exit(0)
    finally:
        db.close()


if __name__ == "__main__":
    main()
