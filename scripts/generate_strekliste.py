#!/usr/bin/env python3
"""Generate a turnus set's strekliste from the command line.

Usage:
    python scripts/generate_strekliste.py --year R27
    python scripts/generate_strekliste.py --year R27 --keep-images

Renders one PNG per shift from the set's strekliste PDF
(turnusdata/<year>/streklister/<year>_streker_<STED>.pdf, or <year>_streker.pdf
for sets uploaded before the split), scans it for double and split shifts into
double_shifts_<year>.json, and parses the duties into
strekliste_dagsverk/strekliste_aktivitet (replacing the set's rows).

The admin "Generer" button starts this same script in the background
(app/services/strekliste_job.py), so a run started here shows up on the admin
page too, and the two cannot overlap.

Images are regenerated from scratch unless --keep-images is given. A forced run
builds into a temp directory and swaps in only once complete, so an interrupted
run leaves the existing images untouched.
"""

import argparse
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Deliberately no os.environ.setdefault("DB_TYPE", ...) here — see the comment
# in scripts/import_innplassering.py for the incident that rule comes from.


def main():
    parser = argparse.ArgumentParser(description="Generate strekliste images, double shifts and parsed duties")
    parser.add_argument("--year", required=True, help="Year identifier, e.g. R27")
    parser.add_argument("--keep-images", action="store_true",
                        help="Only render shifts that have no PNG yet (default: regenerate all)")
    args = parser.parse_args()

    from app.services import strekliste_job

    code = strekliste_job.run(args.year.upper(), force=not args.keep_images)
    if code == 0:
        print("Ferdig.")
    return code


if __name__ == "__main__":
    sys.exit(main())
