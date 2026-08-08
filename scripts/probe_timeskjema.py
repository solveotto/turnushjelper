#!/usr/bin/env python3
"""Structural probe for a Timeskjema export, diffed against a known-good one.

Run this on a NEW rutetermin's Timeskjema file BEFORE importing it, so that a
parser failure on import day is a 30-second read instead of a debugging
session. It answers one question: *has the shape of the file changed?*

What this is NOT:

  * Not a validator. ``validate_turnus_json`` remains the only gate that
    decides whether data may be imported, and this script never writes
    anything, touches the database, or replaces that check.
  * Not a correctness check. It says "there is a new off-code 'F'", never
    "this shift's hours are wrong".
  * Not pass/fail. The baseline is a sample of one real export, so anything
    idiosyncratic to it reads as "normal" and any deviation reads as
    suspicious — including deviations that are perfectly fine. The output is
    something you read and judge.

The scan is deliberately tolerant: it does its own permissive pass over the
lines rather than calling ``parse_timeskjema``, which raises on the first set
of structural violations and would therefore report nothing about a file that
changed shape. The real parser is run once at the end, separately, as an
informational "would the import accept this?" line.

Structural constants (``_REQUIRED_COLUMNS``, ``_FREE_NORMALIZE``, ``WEEKDAYS``,
``_TIME_RE``) are imported from the parser rather than restated, so the probe
cannot drift away from what the parser actually enforces.

Usage:
    venv/bin/python scripts/probe_timeskjema.py <new-file.xls>
    venv/bin/python scripts/probe_timeskjema.py <new.xls> --baseline <old.xls>
    venv/bin/python scripts/probe_timeskjema.py <new.xls> --json

Exit codes: 0 = no structural differences, 1 = differences to look at,
2 = the file could not be read as a timeskjema at all.
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.utils.timeskjema_parser import (  # noqa: E402
    _FREE_NORMALIZE,
    _REQUIRED_COLUMNS,
    _TIME_RE,
    WEEKDAYS,
    TimeskjemaParseError,
    _clean,
    parse_timeskjema,
    sniff_format,
)

# AppConfig raises without SECRET_KEY; this probe only needs a directory name,
# so fall back to the conventional location rather than requiring a usable .env.
try:
    from config import AppConfig

    TURNUSDATA_DIR = AppConfig.turnusfiler_dir
except Exception:  # pragma: no cover - depends on local .env
    TURNUSDATA_DIR = os.path.join(project_root, "turnusdata")

DEFAULT_BASELINE_GLOB = os.path.join(TURNUSDATA_DIR, "r26", "*.xls")

# UTF-8 'ø','æ','å','é' misread as ISO-8859-1 all start with these two bytes.
# The parser hardcodes an iso-8859-1 decode that CANNOT fail (all 256 byte
# values map), so a switch to UTF-8 upstream produces silent mojibake in shift
# names rather than an error. This is the check for that.
_MOJIBAKE_MARKERS = ("Ã¸", "Ã¦", "Ã¥", "Ã©", "Ã˜", "Ã†", "Ã…")


def _find_default_baseline():
    matches = sorted(glob.glob(DEFAULT_BASELINE_GLOB))
    return matches[0] if matches else None


def fingerprint(path):
    """Permissive structural scan. Never raises on malformed content — an
    unexpected shape is a finding to report, not a crash."""
    with open(path, "rb") as f:
        data = f.read()

    fmt = sniff_format(data)
    text = data.decode("iso-8859-1")
    lines = text.split("\n")

    fp = {
        "path": path,
        "sniff_format": fmt,
        "mojibake_markers": sorted({m for m in _MOJIBAKE_MARKERS if m in text}),
        "decodes_as_utf8": _decodes_as_utf8(data),
        "rutetermin_line": None,
        "ruteterminperiode_line": None,
        "turnus_names": [],
        "column_headers": Counter(),
        "required_columns_missing": {},
        "day_row_counts": Counter(),
        "weekday_sequence_breaks": [],
        "off_codes": Counter(),
        "unknown_off_codes": [],
        "row_shape_anomalies": [],
        "segment_patterns": Counter(),
        "blocks_without_total_row": [],
        "trailing_section": False,
        "amp_suffix_rows": 0,
        "bad_time_values": [],
        "hours_over_24": 0,
    }

    current = None
    blocks = []
    for raw_line in lines:
        if "&" in raw_line:
            fp["amp_suffix_rows"] += 1
        cells = [_clean(c) for c in raw_line.split("\t")]
        first = cells[0]

        if first.startswith("Rutetermin:") and fp["rutetermin_line"] is None:
            fp["rutetermin_line"] = raw_line.strip()
        elif first.startswith("Ruteterminperiode:") and fp["ruteterminperiode_line"] is None:
            fp["ruteterminperiode_line"] = raw_line.strip()
        elif first.startswith("Beregninger sum per stasjoneringssted"):
            fp["trailing_section"] = True
            current = None  # station summary is not a turnus block
            continue

        if first.startswith("Turnus:"):
            current = {
                "name": first[len("Turnus:"):].strip().replace(" ", "_"),
                "columns": None,
                "day_rows": [],
                "row_order": [],
                "has_total": False,
            }
            blocks.append(current)
            fp["turnus_names"].append(current["name"])
        elif current is None:
            continue
        elif first == "Dag":
            current["columns"] = tuple(c for c in cells if c)
            fp["column_headers"][current["columns"]] += 1
        elif first in WEEKDAYS:
            current["day_rows"].append(cells)
            current["row_order"].append("day")
        elif first.startswith("Sum uke"):
            current["row_order"].append("sum")
        elif first.startswith("Totalsummer for turnus"):
            current["has_total"] = True

    if not blocks:
        return fp

    for block in blocks:
        name = block["name"]
        columns = block["columns"] or ()
        missing = [c for c in _REQUIRED_COLUMNS if c not in columns]
        if missing:
            fp["required_columns_missing"][name] = missing

        fp["day_row_counts"][len(block["day_rows"])] += 1
        if not block["has_total"]:
            fp["blocks_without_total_row"].append(name)
        fp["segment_patterns"][_segment_shape(block["row_order"])] += 1

        idx = {c: columns.index(c) for c in _REQUIRED_COLUMNS if c in columns}
        _scan_day_rows(fp, name, block["day_rows"], idx)

    fp["unknown_off_codes"] = sorted(
        code for code in fp["off_codes"] if code not in _FREE_NORMALIZE
    )
    return fp


def _decodes_as_utf8(data):
    """True when the bytes are valid UTF-8 *and* contain multibyte sequences —
    i.e. the export was probably re-encoded and the parser's hardcoded
    iso-8859-1 read is now silently producing mojibake."""
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return any(b >= 0x80 for b in data)


def _segment_shape(row_order):
    """Day rows per accounting segment, in raw file order — the 'Sum uke'
    interleaving that the parser replays. Sunday-night shifts land in the next
    week's block, so these are NOT all 7."""
    counts = []
    day_index = 0
    for marker in row_order:
        if marker == "sum":
            counts.append(day_index)
            day_index = 0
        else:
            day_index += 1
    if day_index:
        counts.append(day_index)
    return tuple(counts)


def _scan_day_rows(fp, name, day_rows, idx):
    for i, row in enumerate(day_rows):
        expected = WEEKDAYS[i % 7]
        if row[0] != expected:
            if len(fp["weekday_sequence_breaks"]) < 10:
                fp["weekday_sequence_breaks"].append(
                    f"{name}: day row {i + 1} is {row[0]!r} (expected {expected!r})"
                )
            continue
        if not all(c in idx for c in ("Dv.Nr.", "Start tid", "Avslutningstid")):
            continue

        dv = _cell(row, idx["Dv.Nr."])
        start = _cell(row, idx["Start tid"])
        end = _cell(row, idx["Avslutningstid"])

        if dv and not start and not end:
            fp["off_codes"][dv] += 1
        elif not dv and not start and not end:
            pass  # blank sleep-off day
        elif dv and _TIME_RE.match(start or "") and _TIME_RE.match(end or ""):
            for value in (start, end):
                if int(value.split(":")[0]) >= 24:
                    fp["hours_over_24"] += 1
        else:
            if len(fp["row_shape_anomalies"]) < 10:
                fp["row_shape_anomalies"].append(
                    f"{name}: row {i + 1} Dv.Nr.={dv!r} start={start!r} slutt={end!r}"
                )

        for kind in ("KL.TID", "Tj.t"):
            if kind not in idx:
                continue
            value = _cell(row, idx[kind])
            if value and not _TIME_RE.match(value):
                if len(fp["bad_time_values"]) < 10:
                    fp["bad_time_values"].append(f"{name}: row {i + 1} {kind}={value!r}")


def _cell(row, index):
    return row[index] if index < len(row) else ""


def compare(base, new):
    """Structural differences worth a human look. Returns a list of strings.

    A wrong encoding or a renamed column makes every later check fail too —
    weekday labels stop matching ``WEEKDAYS``, day-row counts collapse, off-code
    scanning is skipped. Those are cascade effects, not independent findings, so
    the root causes are counted and a note is appended when others follow them.
    """
    diffs = []
    root_causes = 0

    if new["sniff_format"] != base["sniff_format"]:
        diffs.append(
            f"format: baseline is {base['sniff_format']!r}, new file is "
            f"{new['sniff_format']!r} — the import will refuse anything but 'timeskjema'"
        )
    if new["mojibake_markers"] and not base["mojibake_markers"]:
        diffs.append(
            "encoding: mojibake markers present "
            f"({', '.join(new['mojibake_markers'])}) — the file looks like UTF-8 but "
            "the parser hardcodes an iso-8859-1 decode that cannot fail, so Norwegian "
            "characters will be silently mangled rather than error"
        )
        root_causes += 1
    elif new["decodes_as_utf8"] and not base["decodes_as_utf8"]:
        diffs.append(
            "encoding: the new file is valid UTF-8 with multibyte characters while the "
            "baseline is not — check shift names for mangled æøå before importing"
        )
        root_causes += 1

    base_cols = set(base["column_headers"])
    new_cols = set(new["column_headers"])
    if new_cols != base_cols:
        for header in sorted(new_cols - base_cols):
            diffs.append(f"columns: new header layout {list(header)}")
        for header in sorted(base_cols - new_cols):
            diffs.append(f"columns: baseline header layout no longer present {list(header)}")
    if new["required_columns_missing"]:
        for name, missing in sorted(new["required_columns_missing"].items())[:5]:
            diffs.append(f"columns: {name} is missing required {missing} — hard parse failure")
        root_causes += 1

    if set(new["day_row_counts"]) != {42}:
        diffs.append(
            "rotation: day-row counts per turnus are "
            f"{dict(new['day_row_counts'])} — 42 (6 weeks x 7) is hardcoded in "
            "timeskjema_parser.py, scraper_validator.py and kompdag_utils.py; "
            "another length is a code change, not a config change"
        )
    if new["weekday_sequence_breaks"]:
        diffs.append(
            f"weekdays: {len(new['weekday_sequence_breaks'])} row(s) out of order, e.g. "
            + new["weekday_sequence_breaks"][0]
        )

    if new["unknown_off_codes"]:
        diffs.append(
            f"off-codes: {new['unknown_off_codes']} not in _FREE_NORMALIZE "
            f"{sorted(set(_FREE_NORMALIZE))} — these rows fail _parse_day, and kompdag "
            "counting keys off exactly X/O/T"
        )
    else:
        gained = set(new["off_codes"]) - set(base["off_codes"])
        lost = set(base["off_codes"]) - set(new["off_codes"])
        if gained:
            diffs.append(f"off-codes: {sorted(gained)} used here but not in the baseline")
        if lost:
            diffs.append(f"off-codes: {sorted(lost)} used in the baseline but not here")

    if new["row_shape_anomalies"]:
        diffs.append(
            f"day rows: {len(new['row_shape_anomalies'])} row(s) match no known shape, e.g. "
            + new["row_shape_anomalies"][0]
        )
    if new["bad_time_values"]:
        diffs.append(
            f"time values: {len(new['bad_time_values'])} unparseable, e.g. "
            + new["bad_time_values"][0]
        )

    base_segments = set(base["segment_patterns"])
    new_segments = set(new["segment_patterns"])
    if new_segments - base_segments:
        diffs.append(
            "accounting weeks: new Sum-uke groupings "
            f"{sorted(new_segments - base_segments)[:3]} (baseline: "
            f"{sorted(base_segments)[:3]}) — grouping is not calendar weeks, so a "
            "difference is plausible but changes the arithmetic check"
        )

    if new["blocks_without_total_row"]:
        diffs.append(
            f"totals: {len(new['blocks_without_total_row'])} block(s) without a "
            f"'Totalsummer for turnus' row, e.g. {new['blocks_without_total_row'][0]}"
        )
    if base["trailing_section"] and not new["trailing_section"]:
        diffs.append(
            "sections: the trailing station-summary section is gone (baseline had one)"
        )
    if new["rutetermin_line"] is None:
        diffs.append(
            "dates: no 'Rutetermin:' line — the rutetermin start/end would be unset "
            "and the year-id cross-check silently skipped"
        )

    if root_causes and len(diffs) > root_causes:
        diffs.append(
            "NOTE: an encoding or column problem is listed above. Fix that first and "
            "re-run — the remaining differences are very likely consequences of it, "
            "not separate problems."
        )
    return diffs


def _print_summary(fp, label):
    print(f"  {label}")
    print(f"    file            {os.path.basename(fp['path'])}")
    print(f"    format          {fp['sniff_format']}")
    print(f"    turnuser        {len(fp['turnus_names'])}")
    print(f"    day rows/turnus {dict(fp['day_row_counts']) or '-'}")
    print(f"    off-codes       {dict(fp['off_codes']) or '-'}")
    print(f"    column layouts  {len(fp['column_headers'])}")
    print(f"    rutetermin      {fp['rutetermin_line'] or '(missing)'}")
    if fp["ruteterminperiode_line"]:
        print(f"    (header, known unreliable) {fp['ruteterminperiode_line']}")
    print(f"    trailing sect.  {fp['trailing_section']}")
    print(f"    '&' rows        {fp['amp_suffix_rows']}")
    if fp["hours_over_24"]:
        print(f"    hours >= 24:00  {fp['hours_over_24']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("new_file", help="the Timeskjema .xls to probe")
    ap.add_argument(
        "--baseline",
        help=f"known-good file to compare against (default: newest match of "
        f"{DEFAULT_BASELINE_GLOB})",
    )
    ap.add_argument("--json", action="store_true", help="dump both fingerprints as JSON")
    args = ap.parse_args()

    baseline_path = args.baseline or _find_default_baseline()
    if baseline_path is None:
        print(
            f"No baseline found at {DEFAULT_BASELINE_GLOB}. Timeskjema sources are "
            "gitignored and do not travel with git — pass --baseline explicitly.",
            file=sys.stderr,
        )
        return 2
    for path in (args.new_file, baseline_path):
        if not os.path.isfile(path):
            print(f"Not a file: {path}", file=sys.stderr)
            return 2

    base = fingerprint(baseline_path)
    new = fingerprint(args.new_file)

    if args.json:
        payload = {"baseline": _jsonable(base), "new": _jsonable(new)}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print()
    print("Timeskjema structure probe")
    print("=" * 70)
    _print_summary(base, "BASELINE")
    print()
    _print_summary(new, "NEW")
    print()

    if not new["turnus_names"]:
        print("STOP: no 'Turnus:' blocks found — this is not a timeskjema export.")
        print("      sniff_format() says: " + new["sniff_format"])
        return 2

    diffs = compare(base, new)
    print("Structural differences")
    print("-" * 70)
    if diffs:
        for d in diffs:
            print(f"  * {d}")
    else:
        print("  none — the file has the same shape as the baseline")
    print()

    print("Would the real parser accept it?")
    print("-" * 70)
    try:
        result = parse_timeskjema(args.new_file)
    except TimeskjemaParseError as e:
        print(f"  NO — {len(e.errors)} error(s), first 10:")
        for err in e.errors[:10]:
            print(f"    - {err}")
    else:
        print(
            f"  yes — {len(result.turnuser)} turnuser, rutetermin "
            f"{result.rutetermin_start} .. {result.rutetermin_end}"
        )
        print("  (parsing is not validation — validate_turnus_json still gates the import)")
    print()

    # Baseline is a sample of one, so differences are prompts to look, not verdicts.
    return 1 if diffs else 0


def _jsonable(obj):
    """Recursively make a fingerprint JSON-safe.

    Counter is a dict subclass, so json.dumps iterates it directly and never
    consults a `default` hook — its tuple keys (column layouts, Sum-uke
    groupings) have to be stringified here, before the encoder sees them.
    """
    if isinstance(obj, dict):
        return {_json_key(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _json_key(key):
    if isinstance(key, tuple):
        return " | ".join(str(k) for k in key)
    return str(key)


if __name__ == "__main__":
    sys.exit(main())
