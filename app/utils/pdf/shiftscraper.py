r"""
Shift Scraper - PDF to JSON/Excel Converter

This script scrapes PDF files containing shift schedules and converts them into
structured JSON and Excel files with color-coded formatting.

Features:
- Scrapes PDF turnus files with shift schedules
- Generates structured JSON data for database import
- Creates color-coded Excel files with conditional formatting
- Automatically organizes files in turnusfiler directory structure
- Supports command-line usage for batch processing

Usage:
    Command Line:
        python shiftscraper.py path/to/file.pdf R24
        python shiftscraper.py path/to/file.pdf R24 --output-dir custom/path
        eksempel: python "D:\\programmering\\Python Projects\\shift_rotation_organizer\\app\\static\\turnusfiler\\r23\\turnuser_R23.pdf" "r25"

    Programmatic:
        scraper = ShiftScraper()
        scraper.scrape_pdf('file.pdf', 'R24')
        scraper.create_json(year_id='R24')  # Auto-saves to turnusfiler/r24/

Color Coding (Excel):
    - Yellow: H-days (holidays)
    - Blue: Early shifts (3-16)
    - Orange: Early-Evening shifts (3-8, 16+)
    - Red: Evening shifts (9-18)
    - Purple: Night shifts (18-23)
    - Green: Free days (XX, OO, TT)
    - Light Purple: Hidden free days (empty cells)

Workflow Integration:
    1. Run shiftscraper.py to generate JSON and Excel files
    2. Use create_new_turnus_year.py to import JSON into database
    3. Files are automatically organized in turnusfiler structure
"""

import copy
import json
import logging
from datetime import datetime

import pandas as pd
import pdfplumber

logger = logging.getLogger(__name__)


class ShiftScraper:
    def __init__(self) -> None:

        ### Intitial Constants ###

        # Dagens dato
        self.TURNUS_START_DATO = datetime(2022, 12, 11)
        # Dimensjoner for hver tabellen
        # Y-akse: fra øverste til nederste verdi
        self.TURNUS_1_POS = [
            {1: (88, 115)},
            {2: (115, 142)},
            {3: (142, 168)},
            {4: (168, 195)},
            {5: (195, 222)},
            {6: (222, 248)},
        ]
        self.TURNUS_2_POS = [
            {1: (374, 401)},
            {2: (402, 427)},
            {3: (428, 454)},
            {4: (455, 480)},
            {5: (481, 507)},
            {6: (508, 533)},
        ]
        # X-akse: fra venstre til høyre
        self.DAG_POS = [
            {1: (51, 109)},
            {2: (109, 167)},
            {3: (167, 224)},
            {4: (224, 283)},
            {5: (283, 340)},
            {6: (340, 399)},
            {7: (399, 514)},
        ]
        self.REMOVE_FILTER = [
            "Materiell:",
            "Ruteterminperiode:",
            "start:",
            "Rutetermin:",
            "Turnus:",
            "Stasjoneringssted:",
            "OSL",
        ]
        self.ALLOW_FILTER = [":", "XX", "OO", "TT"]
        self.FRIDAG_FILTER = ["X", "O", "T"]
        self.FRIDAG_NORMALIZE = {"XX": "X", "OO": "O", "TT": "T"}

        self.turnuser = []

    # Scraper og sorterer pdf med turnuser
    def scrape_pdf(self, pdf_path="turnuser_R25.pdf", year_id=None):

        pdf = pdfplumber.open(pdf_path)
        pages_in_pdf = pdf.pages

        for page in pages_in_pdf:
            sorterte_turnuser = self.sort_page(page)
            for sortert_turnus in sorterte_turnuser:
                self.turnuser.append(sortert_turnus)

    def extract_turnus_name(self, text_objects, word_pos):
        """
        Extracts complete turnus name after 'Turnus:' by collecting all words
        until a known separator is found.
        """
        turnus_parts = []
        i = word_pos + 1
        separators = ["Stasjoneringssted:", "Rutetermin:", "Uke", "Materiell:"]

        # Collect words until we hit a separator or run out of words
        while i < len(text_objects):
            word = text_objects[i]
            # Stop if we hit a known separator or the y-position changes significantly
            # Tolerance of 10px allows for slight vertical offsets of suffix characters
            # (e.g., "F" in "5012-73 N05 5 F") while staying within the same line
            if (
                word["text"] in separators
                or abs(word["top"] - text_objects[word_pos]["top"]) > 10
            ):
                break
            turnus_parts.append(word["text"])
            i += 1

        return "_".join(turnus_parts) if turnus_parts else "UNKNOWN"

    def split_concatenated_times(self, text):
        """
        Splits concatenated time values like '19:014:24' into ['19:01', '4:24']
        Also handles cases like '8:0016:00' -> ['8:00', '16:00']
        """
        import re

        # Pattern to find time values: digits:digits
        # This will match patterns like 19:01, 4:24, etc.
        time_pattern = r"(\d{1,2}:\d{2})"

        matches = re.findall(time_pattern, text)

        # If we found multiple times in one string, return them separately
        if len(matches) > 1:
            return matches
        elif len(matches) == 1:
            return [matches[0]]
        else:
            return [text]

    def extract_shift_code(self, text):
        """
        Cleans up shift codes (dagsverk) - removes extra whitespace,
        handles concatenated codes better
        """
        # Remove leading/trailing whitespace
        text = text.strip()

        # Return cleaned text
        return text

    def sort_page(self, page):

        def sorter_turnus(search_obj):
            for txt_obj in text_objects:
                if (
                    int(txt_obj["x0"]) >= self.DAG_POS[0][1][0]
                    and int(txt_obj["x1"]) <= self.DAG_POS[6][7][1]
                ):
                    # Siler ut hvilken turnus (1 eller 2)
                    if (
                        int(txt_obj["top"]) >= self.TURNUS_1_POS[0][1][0]
                        and int(txt_obj["bottom"]) <= self.TURNUS_1_POS[5][6][1]
                    ):
                        uker_dag_iterering(
                            txt_obj, self.TURNUS_1_POS, turnus1, search_obj
                        )
                    elif (
                        int(txt_obj["top"]) >= self.TURNUS_2_POS[0][1][0]
                        and int(txt_obj["bottom"]) <= self.TURNUS_2_POS[5][6][1]
                    ):
                        uker_dag_iterering(
                            txt_obj, self.TURNUS_2_POS, turnus2, search_obj
                        )

        # Sjekker om objektet er innenfor verdiene til tabellen
        def objektet_innenfor_uke_dag(word, uke_verdi, dag_verdi):
            return (
                word["top"] >= uke_verdi[0]
                and word["bottom"] <= uke_verdi[1]
                and word["x0"] >= dag_verdi[0]
                and word["x0"] <= dag_verdi[1]
                and word["text"] not in self.REMOVE_FILTER
            )

        # Pakker ut uker og dager og mater det inn i plasseringslogikk
        def uker_dag_iterering(text_obj, turnus_pos, turnus, search_obj):
            for uker in turnus_pos:
                for uke, uke_verdi in uker.items():
                    for dager in self.DAG_POS:
                        for dag, dag_verdi in dager.items():
                            if objektet_innenfor_uke_dag(
                                text_obj, uke_verdi, dag_verdi
                            ):
                                if search_obj == "tid":
                                    plasseringslogikk_tid(text_obj, uke, dag, turnus)
                                elif search_obj == "dagsverk":
                                    plasseringslogikk_dagsverk(
                                        text_obj, uke, dag, turnus
                                    )

        def plasseringslogikk_tid(word, uke, dag, turnus):
            # Først, sjekk om teksten inneholder sammenkoblede tider og split dem
            text_to_process = word["text"]

            # Siler ut objektene som inneholder :, XX, OO, eller TT.
            if any(sub in text_to_process for sub in self.ALLOW_FILTER):
                # Split concatenated times if present (e.g., "19:014:24" -> ["19:01", "4:24"])
                if ":" in text_to_process and text_to_process not in self.ALLOW_FILTER:
                    split_times = self.split_concatenated_times(text_to_process)

                    # Check if the word crosses cell boundaries (indicates split shift)
                    # Get the current day's x boundary
                    for dager in self.DAG_POS:
                        for d, dag_verdi in dager.items():
                            if d == dag:
                                current_dag_x_end = dag_verdi[1]
                                # If word extends beyond current day's boundary and we split times
                                if (
                                    word["x1"] > current_dag_x_end
                                    and len(split_times) == 2
                                ):
                                    # First time in current day, second time in next day
                                    turnus[uke][dag]["tid"].append(split_times[0])
                                    # Place second time in next day if not Sunday
                                    if dag < 7:
                                        turnus[uke][dag + 1]["tid"].append(
                                            split_times[1]
                                        )
                                    elif dag == 7 and uke < 6:
                                        # Sunday to Monday next week
                                        turnus[uke + 1][1]["tid"].append(split_times[1])
                                    # Skip normal processing
                                    return

                    times_to_add = split_times
                else:
                    times_to_add = [text_to_process]

                # Process each time value normally
                for time_val in times_to_add:
                    # Normalize day-off codes: XX->X, OO->O, TT->T
                    time_val = self.FRIDAG_NORMALIZE.get(time_val, time_val)
                    # Hvis det er uke1 og dag 1 så skal det ikke sjekkes om objektet finnes i uken og dagen før,
                    # men lagres i nåværende dag og uke.
                    if (uke == 1 and dag == 1) or time_val in self.ALLOW_FILTER or time_val in self.FRIDAG_FILTER:
                        turnus[uke][dag]["tid"].append(time_val)

                    # Hvis det mandag men ikke uke1.
                    elif uke != 1 and dag == 1:
                        # Hopper over objekter på mandag hvis søndagen før har to objekter,
                        # mandagen har null objekter og objektet på søndag er likt det som skal plasseres.
                        if (
                            len(turnus[uke - 1][7]["tid"]) == 2
                            and len(turnus[uke][dag]["tid"]) == 0
                            and time_val == turnus[uke - 1][7]["tid"][1]
                        ):
                            pass
                        # hvis objektet er :, X, O eller T: lagre i nåværede dag og uke
                        elif any(
                            val in turnus[uke - 1][7]["tid"]
                            for val in self.ALLOW_FILTER + self.FRIDAG_FILTER
                        ):
                            turnus[uke][dag]["tid"].append(time_val)
                        # Hvis det bare er et objekt på søndag uke over: legg objekt til søndag
                        elif len(turnus[uke - 1][7]["tid"]) == 1:
                            turnus[uke - 1][7]["tid"].append(time_val)
                        else:
                            turnus[uke][dag]["tid"].append(time_val)

                    # Hvis det ikke er dag1
                    elif uke >= 1 and dag > 1:
                        # Putter objekt i nåværende dag hvis dagen før er :, X, T, eller O.
                        if any(
                            val in turnus[uke][dag - 1]["tid"]
                            for val in self.ALLOW_FILTER + self.FRIDAG_FILTER
                        ):
                            turnus[uke][dag]["tid"].append(time_val)
                        # Putter objekt i dagen før hvis det kun er en verdi der.
                        elif len(turnus[uke][dag - 1]["tid"]) == 1:
                            turnus[uke][dag - 1]["tid"].append(time_val)
                        else:
                            turnus[uke][dag]["tid"].append(time_val)

                if len(turnus[uke][dag]["tid"]) == 2:
                    turnus[uke][dag]["start"] = turnus[uke][dag]["tid"][0]
                    turnus[uke][dag]["slutt"] = turnus[uke][dag]["tid"][1]
                else:
                    turnus[uke][dag]["start"] = turnus[uke][dag]["tid"]

        def plasseringslogikk_dagsverk(word, uke, dag, turnus):
            # Hopper over iterering hvis de inneholder :, XX, OO eller TT.
            if any(sub in word["text"] for sub in self.ALLOW_FILTER):
                pass
            else:
                text_to_add = word["text"]

                # Check if this dagsverk text crosses into next day's column
                # Look for the current day's x boundary
                for dager in self.DAG_POS:
                    for d, dag_verdi in dager.items():
                        if d == dag:
                            current_dag_x_end = dag_verdi[1]
                            # If word extends beyond current day's boundary
                            if word["x1"] > current_dag_x_end:
                                # This dagsverk belongs to current day, but next text object
                                # might be a continuation (like "1511-N05" + "01")
                                # We'll mark this and let the next object be added to it
                                pass

                # Check if previous day has incomplete dagsverk that this might complete.
                # Two tiers:
                # 1) Tight spillover (within 8px of column boundary): dagsverk suffix chars
                #    like "5", "F" that spill just past the column edge. Only requires
                #    the previous dagsverk to contain an N-pattern (e.g., "N05").
                # 2) Wider spillover (within 20px): multi-char continuations like "01"
                #    in "1511-N05 01". Uses the original stricter checks.
                import re

                n_pattern = re.compile(r"N\d{2}")  # Matches N05, N01, etc.

                if dag > 1 and turnus[uke][dag - 1]["dagsverk"]:
                    prev_dagsverk = turnus[uke][dag - 1]["dagsverk"]
                    current_dag_x_start = self.DAG_POS[dag - 1][dag][0]
                    dist_from_start = word["x0"] - current_dag_x_start

                    # Tier 1: Tight spillover — suffix chars barely past column boundary
                    if (
                        dist_from_start < 8
                        and len(word["text"]) <= 3
                        and n_pattern.search(prev_dagsverk)
                    ):
                        turnus[uke][dag - 1]["dagsverk"] = (
                            prev_dagsverk + "_" + text_to_add
                        )
                        return

                    # Tier 2: Wider spillover — original logic for "01" continuations
                    if (
                        dist_from_start < 20
                        and len(word["text"]) <= 3
                        and word["text"].isdigit()
                        and len(turnus[uke][dag]["tid"]) == 0
                        and ("-N05" in prev_dagsverk or "-N" in prev_dagsverk)
                    ):
                        turnus[uke][dag - 1]["dagsverk"] = (
                            prev_dagsverk + "_" + text_to_add
                        )
                        return

                elif dag == 1 and uke > 1 and turnus[uke - 1][7]["dagsverk"]:
                    prev_dagsverk = turnus[uke - 1][7]["dagsverk"]
                    current_dag_x_start = self.DAG_POS[0][1][0]
                    dist_from_start = word["x0"] - current_dag_x_start

                    # Tier 1: Tight spillover
                    if (
                        dist_from_start < 8
                        and len(word["text"]) <= 3
                        and n_pattern.search(prev_dagsverk)
                    ):
                        turnus[uke - 1][7]["dagsverk"] = (
                            prev_dagsverk + "_" + text_to_add
                        )
                        return

                    # Tier 2: Wider spillover (original Sunday→Monday logic)
                    if (
                        word["x0"] < 130
                        and len(word["text"]) <= 3
                        and word["text"].isdigit()
                        and ("-N05" in prev_dagsverk or "-N" in prev_dagsverk)
                    ):
                        turnus[uke - 1][7]["dagsverk"] = (
                            prev_dagsverk + "_" + text_to_add
                        )
                        return

                # Normal placement logic
                # Hvis det er uke1 og dag1, lagres objektet i nåværende dag og uke.
                if (uke == 1 and dag == 1) and word["text"] not in self.REMOVE_FILTER:
                    if turnus[uke][dag]["dagsverk"]:
                        turnus[uke][dag]["dagsverk"] += "_" + text_to_add
                    else:
                        turnus[uke][dag]["dagsverk"] = text_to_add

                # Mandager som ikke er uke1
                elif uke != 1 and dag == 1:
                    # Hopper over iterering hvis dagsverket er likt dagsverket i søndagen uka før
                    # og tidene i de to dagene ikke er like.
                    if (
                        text_to_add == turnus[uke - 1][7]["dagsverk"]
                        and turnus[uke][dag]["tid"] != turnus[uke - 1][7]["tid"]
                    ):
                        pass
                    # Hvis det er to verdier av TID og ingen i DAGSVERK søndag uka før,
                    elif (
                        len(turnus[uke - 1][7]["tid"]) == 2
                        and turnus[uke - 1][7]["dagsverk"] == ""
                    ):
                        turnus[uke - 1][7]["dagsverk"] = text_to_add
                    else:
                        if turnus[uke][dag]["dagsverk"]:
                            turnus[uke][dag]["dagsverk"] += "_" + text_to_add
                        else:
                            turnus[uke][dag]["dagsverk"] = text_to_add

                # Hvis det ikke er dag1
                elif uke >= 1 and dag > 1:
                    # Check if previous day has 2 times and no dagsverk (shift spanning to current day)
                    if (
                        len(turnus[uke][dag - 1]["tid"]) == 2
                        and turnus[uke][dag - 1]["dagsverk"] == ""
                    ):
                        turnus[uke][dag - 1]["dagsverk"] = text_to_add
                    # Also handle case where current day has only 1 time (end of spanning shift) and prev day has 1 time
                    elif (
                        len(turnus[uke][dag]["tid"]) == 1
                        and len(turnus[uke][dag - 1]["tid"]) >= 1
                        and turnus[uke][dag - 1]["dagsverk"] == ""
                        and len(text_to_add) >= 3
                    ):
                        # This dagsverk likely belongs to the previous day's spanning shift
                        turnus[uke][dag - 1]["dagsverk"] = text_to_add
                    else:
                        # Skip single-digit numbers unless they look like valid codes
                        if len(text_to_add) == 1 and text_to_add.isdigit():
                            # Single digit - probably metadata, skip unless it's clearly part of a code
                            pass
                        else:
                            if turnus[uke][dag]["dagsverk"]:
                                turnus[uke][dag]["dagsverk"] += "_" + text_to_add
                            else:
                                turnus[uke][dag]["dagsverk"] = text_to_add

        def generer_turnus_mal():

            uke_mal = {
                1: {
                    "ukedag": "Mandag",
                    "tid": [],
                    "start": "",
                    "slutt": "",
                    "dagsverk": "",
                    "is_consecutive_shift": False,
                    "is_consecutive_receiver": False,
                },
                2: {
                    "ukedag": "Tirsdag",
                    "tid": [],
                    "start": "",
                    "slutt": "",
                    "dagsverk": "",
                    "is_consecutive_shift": False,
                    "is_consecutive_receiver": False,
                },
                3: {
                    "ukedag": "Onsdag",
                    "tid": [],
                    "start": "",
                    "slutt": "",
                    "dagsverk": "",
                    "is_consecutive_shift": False,
                    "is_consecutive_receiver": False,
                },
                4: {
                    "ukedag": "Torsdag",
                    "tid": [],
                    "start": "",
                    "slutt": "",
                    "dagsverk": "",
                    "is_consecutive_shift": False,
                    "is_consecutive_receiver": False,
                },
                5: {
                    "ukedag": "Fredag",
                    "tid": [],
                    "start": "",
                    "slutt": "",
                    "dagsverk": "",
                    "is_consecutive_shift": False,
                    "is_consecutive_receiver": False,
                },
                6: {
                    "ukedag": "Lørdag",
                    "tid": [],
                    "start": "",
                    "slutt": "",
                    "dagsverk": "",
                    "is_consecutive_shift": False,
                    "is_consecutive_receiver": False,
                },
                7: {
                    "ukedag": "Søndag",
                    "tid": [],
                    "start": "",
                    "slutt": "",
                    "dagsverk": "",
                    "is_consecutive_shift": False,
                    "is_consecutive_receiver": False,
                },
            }
            turnus = {}

            for uke in range(1, 7):
                mal_kopi = copy.deepcopy(uke_mal)
                turnus.update({uke: mal_kopi})

            return turnus

        def extract_totalsummer():
            """Find Totalsummer rows and extract KL.timer + Tj.timer for each turnus."""
            import re

            totalsummer_pattern = re.compile(r"\d{1,3}:\d{2}")  # matches HH:MM or HHH:MM totals

            # Collect all Totalsummer occurrences sorted by vertical position
            totalsummer_rows = [
                w for w in text_objects if w["text"] == "Totalsummer"
            ]
            totalsummer_rows.sort(key=lambda w: w["top"])  # turnus1 comes first (lower y)

            results = {}  # index (0, 1) -> {"kl_timer": ..., "tj_timer": ...}

            for idx, row_word in enumerate(totalsummer_rows):
                row_top = row_word["top"]
                # Gather words on the same horizontal line (within ±5 px) that are to the right
                same_line = [
                    w for w in text_objects
                    if abs(w["top"] - row_top) <= 5 and w["x0"] > row_word["x1"]
                ]
                same_line.sort(key=lambda w: w["x0"])  # left-to-right order

                # Extract time-like values (e.g., "203:27")
                times = []
                for w in same_line:
                    if totalsummer_pattern.fullmatch(w["text"]):
                        times.append(w["text"])
                    elif totalsummer_pattern.search(w["text"]):
                        # Handle edge case where value is embedded in a larger token
                        times.extend(totalsummer_pattern.findall(w["text"]))
                    if len(times) == 2:
                        break

                results[idx] = {
                    "kl_timer": times[0] if len(times) > 0 else None,
                    "tj_timer": times[1] if len(times) > 1 else None,
                }

            return results

        # Henter ut alle objektene i pdf-en med bedre toleranse for å få med komplette tall
        text_objects = page.extract_words(x_tolerance=3, y_tolerance=2)

        turnus_1_navn = None
        turnus_2_navn = None

        # Finne og navgi turnus - forbedret logikk
        for i, word in enumerate(text_objects):
            # Ser etter "Turnus:" label
            if word["text"] == "Turnus:":
                # Ekstraher komplett turnus navn etter "Turnus:"
                extracted_name = self.extract_turnus_name(text_objects, i)

                # Avgjør hvilken turnus basert på y-posisjon
                if word["top"] >= 50 and word["top"] <= 80:
                    turnus_1_navn = extracted_name
                elif word["top"] >= 330 and word["top"] <= 365:
                    turnus_2_navn = extracted_name

        turnus1 = generer_turnus_mal()
        turnus2 = generer_turnus_mal()

        # Sorterer først tiden. Sorteringen av dagsverk basserer seg på sorterte tider.
        sorter_turnus("tid")
        sorter_turnus("dagsverk")

        totalsummer = extract_totalsummer()

        turnus1["kl_timer"] = totalsummer.get(0, {}).get("kl_timer")
        turnus1["tj_timer"] = totalsummer.get(0, {}).get("tj_timer")
        turnus2["kl_timer"] = totalsummer.get(1, {}).get("kl_timer")
        turnus2["tj_timer"] = totalsummer.get(1, {}).get("tj_timer")

        sorterte_turnuser_lst = []

        # Legg til turnuser hvis de ble funnet
        if turnus_1_navn:
            sorterte_turnuser_lst.append({turnus_1_navn: turnus1})
        if turnus_2_navn:
            sorterte_turnuser_lst.append({turnus_2_navn: turnus2})

        return sorterte_turnuser_lst

    ### FILE CREATION ###
    def create_json(self, output_path="turnus_schedule_R25.json", year_id=None):
        """Create JSON file with optional custom path"""
        # If year_id is provided and output_path is default, create path in turnusfiler
        if year_id and output_path == "turnus_schedule_R25.json":
            import os
            import sys

            # Add project root to path to import config
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            sys.path.insert(0, project_root)
            from config import AppConfig

            # Create turnusfiler directory structure
            turnusfiler_dir = os.path.join(
                AppConfig.static_dir, "turnusfiler", year_id.lower()
            )
            os.makedirs(turnusfiler_dir, exist_ok=True)
            output_path = os.path.join(turnusfiler_dir, f"turnus_schedule_{year_id}.json")

        with open(output_path, "w") as f:
            json.dump(self.turnuser, f, indent=4)
        logger.info("JSON file created: %s", output_path)
        return output_path


if __name__ == "__main__":
    import argparse
    import os
    import sys

    parser = argparse.ArgumentParser(
        description="Scrape PDF turnus files and generate JSON and Excel"
    )
    parser.add_argument("pdf_path", help="Path to PDF file to scrape")
    parser.add_argument("year_id", help="Year identifier (e.g., R24, R25, r23)")
    parser.add_argument(
        "--output-dir", help="Custom output directory (default: turnusfiler/year_id)"
    )

    args = parser.parse_args()

    # Validate inputs
    if not os.path.exists(args.pdf_path):
        print(f"❌ Error: PDF file {args.pdf_path} does not exist")
        sys.exit(1)

    year_id = args.year_id.upper()

    print(f"🚀 Scraping PDF: {args.pdf_path}")
    print(f"📅 Year ID: {year_id}")

    # Initialize scraper and process PDF
    shift_scraper = ShiftScraper()
    shift_scraper.scrape_pdf(args.pdf_path, year_id)

    # Create JSON file
    if args.output_dir:
        json_path = os.path.join(args.output_dir, f"turnus_schedule_{year_id}.json")
        os.makedirs(args.output_dir, exist_ok=True)
        shift_scraper.create_json(json_path)
    else:
        json_path = shift_scraper.create_json(year_id=year_id)

    print("✅ Scraping completed successfully!")
    print(f"📄 JSON file created: {json_path}")
