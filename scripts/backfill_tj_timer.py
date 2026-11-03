#!/usr/bin/env python3
"""Add the per-shift Tj.t to one rutetermin's stored turnus schedule.

Touches no database and changes nothing but that key. Without --write it only
reports what it would do. Exits 0 when clean and 1 otherwise. Run it as the user
the app runs as.

Usage:
    venv/bin/python scripts/backfill_tj_timer.py --year R27
    venv/bin/python scripts/backfill_tj_timer.py --year R27 --write

To undo, copy the .bak-<timestamp> file it names back over the schedule.
"""

import argparse
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

MAX_PROBLEMS_SHOWN = 20


def main(argv=None):
    from app.services.tj_timer_backfill import backfill

    parser = argparse.ArgumentParser(description="Add per-shift Tj.t to a stored schedule")
    parser.add_argument("--year", required=True, help="Rutetermin, e.g. R27")
    parser.add_argument("--write", action="store_true", help="Write the change (default is a dry run)")
    args = parser.parse_args(argv)

    result = backfill(args.year, write=args.write)

    if result["problems"]:
        print(f"{args.year}: stopped, nothing changed. {len(result['problems'])} problem(s):")
        for problem in result["problems"][:MAX_PROBLEMS_SHOWN]:
            print(f"  {problem}")
        if len(result["problems"]) > MAX_PROBLEMS_SHOWN:
            print(f"  ... and {len(result['problems']) - MAX_PROBLEMS_SHOWN} more")
        return 1

    if result["written"]:
        print(f"{args.year}: added Tj.t to {result['cells_to_fill']} cells.")
        print(f"  Backup: {result['backup']}")
    elif result["cells_to_fill"] == 0:
        print(f"{args.year}: nothing to do, every cell already has Tj.t.")
    else:
        print(f"{args.year}: clean. Would add Tj.t to {result['cells_to_fill']} cells. Run with --write to do it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
