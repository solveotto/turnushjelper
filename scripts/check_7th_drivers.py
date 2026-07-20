#!/usr/bin/env python3
"""Verify 7.fører linjenummer data after an innplassering import.

7.fører (7th driver) rows in the Innplassering PDF have their own column
layout; a past parser bug stored a sequential row counter (1..10, 1..N) as
the linjenummer instead of the real "L" column value, which must always be
in 1-6 (a turnus only has linjer 1-6). This script re-checks that invariant
after any innplassering import/re-import, so you don't have to eyeball the
database by hand.

Usage:
    venv/bin/python scripts/check_7th_drivers.py --year R26
"""

import argparse
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

os.environ.setdefault("DB_TYPE", "sqlite")

VALID_LINJER = {1, 2, 3, 4, 5, 6}


def main():
    parser = argparse.ArgumentParser(
        description="Check 7.fører linjenummer values for a turnus set"
    )
    parser.add_argument("--year", required=True, help="Year identifier (e.g. R26)")
    args = parser.parse_args()
    year_id = args.year.upper()

    from app.database import get_db_session
    from app.models import Innplassering, TurnusSet

    db = get_db_session()
    try:
        turnus_set = db.query(TurnusSet).filter_by(year_identifier=year_id).first()
        if not turnus_set:
            print(f"Error: No turnus set found for year '{year_id}'")
            sys.exit(1)

        rows = (
            db.query(Innplassering)
            .filter_by(turnus_set_id=turnus_set.id, is_7th_driver=1)
            .order_by(Innplassering.rullenummer)
            .all()
        )

        print(f"{len(rows)} 7.fører row(s) for {year_id}")
        print("=" * 60)

        if not rows:
            print("No 7.fører rows found — nothing to check.")
            sys.exit(0)

        bad_rows = []
        for r in rows:
            flag = "" if r.linjenummer in VALID_LINJER else "  <-- INVALID"
            print(f"rullenummer={r.rullenummer:>6}  linje={r.linjenummer}  tur={r.shift_title}{flag}")
            if r.linjenummer not in VALID_LINJER:
                bad_rows.append(r)

        print("=" * 60)
        if bad_rows:
            print(
                f"\n⚠ {len(bad_rows)} row(s) have a linjenummer outside 1-6. "
                "This is the row-counter bug pattern (sequential 1..N instead "
                "of the real 'L' column) — the import likely needs to be re-run "
                "with the current parser."
            )
            sys.exit(1)
        else:
            print("\n✓ All linjenummer values are in 1-6. Looks correct.")
            sys.exit(0)
    finally:
        db.close()


if __name__ == "__main__":
    main()
