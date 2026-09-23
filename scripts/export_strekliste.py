#!/usr/bin/env python3
"""Export the parsed strekliste for one rutetermin as a flat file.

One entry per duty as the strekliste PDF prints it, with its activities, for
the sibling nlfstreik app (which imports it into dagsverk_mal).

Usage:
    python scripts/export_strekliste.py --year R26
    python scripts/export_strekliste.py --year R26 --out /tmp/strekliste_R26.json.gz

The strekliste must have been parsed first (the admin "generer strekliste"
step does that). No names in the output, but it goes in turnusdata/<year>/
beside the roster export.
"""

import argparse
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Deliberately no os.environ.setdefault("DB_TYPE", ...) here — see the comment
# in scripts/import_innplassering.py for the incident that rule comes from.


def main():
    parser = argparse.ArgumentParser(description="Export the parsed strekliste for one rutetermin")
    parser.add_argument("--year", required=True, help="Year identifier, e.g. R26")
    parser.add_argument("--out", help="Output path (.json.gz). Default: turnusdata/<year>/")
    args = parser.parse_args()

    from app.services import strekliste_export_service as eksport
    from app.services.turnus_service import get_turnus_set_by_year

    ts = get_turnus_set_by_year(args.year.upper())
    if not ts:
        print(f"Fant ikke turnus-sett {args.year}", file=sys.stderr)
        return 1
    out = args.out or eksport.default_path(args.year)
    rapport = eksport.export(ts["id"], out)
    print(f"Skrev {rapport['dagsverk']} dagsverk til {rapport['sti']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
