#!/usr/bin/env python3
"""Generate a turnus set's strekliste from the command line.

Usage:
    python scripts/generate_strekliste.py --year R27
    python scripts/generate_strekliste.py --year R27 --keep-images

Does the three things the admin "Generer" button does, in the same order:
render one PNG per shift from turnusdata/<year>/streklister/<year>_streker.pdf,
scan the PDF for double and split shifts into double_shifts_<year>.json, and
parse the duties into strekliste_dagsverk/strekliste_aktivitet (replacing the
set's rows). Use it on the servers: the button runs all three inside one HTTP
request, which gunicorn kills after --timeout seconds, while this runs outside
gunicorn and does not occupy a web worker.

Images are regenerated from scratch unless --keep-images is given. A forced run
builds into a temp directory and swaps in only once complete, so an interrupted
run leaves the existing images untouched.

Restart the service afterwards: the workers cache the turnus data, including
the double-shift flags, for up to an hour.
"""

import argparse
import json
import os
import sys
import time

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

    from app.services import strekliste_service
    from app.services.turnus_service import get_turnus_set_by_year
    from app.utils.pdf import strekliste_generator
    from app.utils.pdf.double_shift_scanner import scan_double_shifts
    from config import AppConfig

    year = args.year.upper()
    version = year.lower()
    ts = get_turnus_set_by_year(year)
    if not ts:
        print(f"Fant ikke turnus-sett {year}", file=sys.stderr)
        return 1
    paths = strekliste_generator.get_paths(version)
    if not paths["pdf_exists"]:
        print(f"Fant ingen strekliste-PDF: {paths['pdf_path']}", file=sys.stderr)
        return 1
    print(f"Turnus-sett {year} (id {ts['id']}), PDF {paths['pdf_path']}")

    t = time.time()
    result = strekliste_generator.generate_all_images(version, force=not args.keep_images)
    if not result["success"]:
        print(f"Bildegenerering feilet: {result.get('error')}", file=sys.stderr)
        return 1
    print(f"Bilder: {len(result['generated'])} generert, {len(result['skipped'])} hoppet over, "
          f"{len(result['errors'])} feil av {result['total']} ({time.time() - t:.0f} s)")
    for err in result["errors"][:10]:
        print(f"  feil: {err}")

    t = time.time()
    double_shifts = scan_double_shifts(paths["pdf_path"])
    out = os.path.join(AppConfig.turnusfiler_dir, version, f"double_shifts_{version}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(double_shifts, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Dobbeltskift: {len(double_shifts['dobbelt_tur'])} dobbelt tur, "
          f"{len(double_shifts['delt_dagsverk'])} delt dagsverk -> {out} ({time.time() - t:.0f} s)")

    t = time.time()
    rapport = strekliste_service.import_strekliste(ts["id"], paths["pdf_path"])
    print(f"Strekliste: {rapport['dagsverk']} dagsverk, {rapport['aktiviteter']} aktiviteter, "
          f"{rapport['advarsler']} med advarsler, per sted {rapport.get('per_sted')} "
          f"({time.time() - t:.0f} s)")
    for warning in rapport.get("sidevarsler", [])[:10]:
        print(f"  side: {warning}")

    print("Ferdig. Husk: sudo systemctl restart turnushjelper")
    return 0


if __name__ == "__main__":
    sys.exit(main())
