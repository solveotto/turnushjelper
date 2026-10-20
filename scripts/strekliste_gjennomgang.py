#!/usr/bin/env python3
"""Write the strekliste review report: every parsed duty beside its PNG.

Usage:
    python scripts/strekliste_gjennomgang.py --year R26
    python scripts/strekliste_gjennomgang.py --year R26 --out /tmp/gjennomgang.html

Reads strekliste_dagsverk/strekliste_aktivitet (run "generer strekliste" in
the admin first) and the PNGs under turnusdata/<year>/streklister/png/. The
default output lands beside that folder, so the image links resolve. The
file is for reading in a browser, not for the app to serve.
"""

import argparse
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Deliberately no os.environ.setdefault("DB_TYPE", ...) here — see the comment
# in scripts/import_innplassering.py for the incident that rule comes from.


def main():
    parser = argparse.ArgumentParser(description="Review report for the parsed strekliste")
    parser.add_argument("--year", required=True, help="Year identifier, e.g. R26")
    parser.add_argument("--out", help="Output .html (default: turnusdata/<year>/streklister/gjennomgang_<year>.html)")
    args = parser.parse_args()

    from app.services import strekliste_service
    from app.services.turnus_service import get_turnus_set_by_year
    from app.utils import strekliste_rapport
    from app.utils.pdf.strekliste_generator import get_paths

    ts = get_turnus_set_by_year(args.year.upper())
    if not ts:
        print(f"Fant ikke turnus-sett {args.year}", file=sys.stderr)
        return 1
    hoder = strekliste_service.list_dagsverk(ts["id"])
    if not hoder:
        print("Ingen strekliste er lest inn for dette settet — kjør «generer strekliste» først.",
              file=sys.stderr)
        return 1
    # hent_dagsverk picks one variant per number; asking with the variant's
    # own first weekday keeps 1310/25 and 1310/34 apart.
    dagsverk = []
    for h in hoder:
        ukedag = int(h["kjoredager"][0]) if h.get("kjoredager") else None
        d = strekliste_service.hent_dagsverk(ts["id"], h["nr"], ukedag=ukedag)
        dagsverk.append(d if d and d["kjoredager"] == h["kjoredager"] else h)
    paths = get_paths(args.year.lower())
    ut = args.out or os.path.join(os.path.dirname(paths["images_dir"]), f"gjennomgang_{args.year.lower()}.html")
    strekliste_rapport.skriv_gjennomgang(dagsverk, paths["images_dir"], args.year.upper(), ut)
    med = sum(1 for d in dagsverk if d.get("advarsler"))
    print(f"Skrev {len(dagsverk)} dagsverk ({med} med advarsler) til {ut}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
