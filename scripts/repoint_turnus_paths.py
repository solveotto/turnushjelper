#!/usr/bin/env python3
"""Repoint TurnusSet.turnus_file_path / df_file_path at the current data store.

`TurnusSet` rows store ABSOLUTE paths, so relocating the data store leaves every
row dangling — moving `app/static/turnusfiler/` to `turnusdata/` (2026-07-29)
invalidated all of them. `DataframeManager` falls back to the conventional
location when a stored path is missing, so the app keeps working either way;
this script just makes the DB tell the truth and silences the fallback warning.

Safe to re-run. Rows already pointing at an existing file are left alone.

    venv/bin/python scripts/repoint_turnus_paths.py --dry-run
    venv/bin/python scripts/repoint_turnus_paths.py
"""

import argparse
import os
import sys

# Add project root to path (go up 2 levels: scripts -> project_root)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.database import SessionLocal  # noqa: E402
from app.models import TurnusSet  # noqa: E402
from config import AppConfig  # noqa: E402


def conventional_paths(year_identifier):
    year_id = year_identifier.lower()
    base = os.path.join(AppConfig.turnusfiler_dir, year_id)
    return (
        os.path.join(base, f"turnus_schedule_{year_identifier}.json"),
        os.path.join(base, f"turnus_stats_{year_identifier}.json"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="Report changes without writing"
    )
    args = parser.parse_args()

    session = SessionLocal()
    changed = 0
    try:
        rows = session.query(TurnusSet).all()
        if not rows:
            print("No turnus sets found.")
            return 0

        for ts in rows:
            turnus_path, df_path = conventional_paths(ts.year_identifier)
            stored_ok = (
                ts.turnus_file_path
                and ts.df_file_path
                and os.path.exists(ts.turnus_file_path)
                and os.path.exists(ts.df_file_path)
            )
            if stored_ok:
                print(f"  {ts.year_identifier}: OK, left alone")
                continue

            missing = [p for p in (turnus_path, df_path) if not os.path.exists(p)]
            if missing:
                print(
                    f"  {ts.year_identifier}: SKIPPED — target does not exist: "
                    f"{missing[0]}"
                )
                continue

            print(f"  {ts.year_identifier}: {ts.turnus_file_path} -> {turnus_path}")
            if not args.dry_run:
                ts.turnus_file_path = turnus_path
                ts.df_file_path = df_path
            changed += 1

        if args.dry_run:
            print(f"\nDry run — {changed} row(s) would change.")
        else:
            session.commit()
            print(f"\nUpdated {changed} row(s).")
        return 0
    except Exception as e:
        session.rollback()
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
