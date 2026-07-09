"""Parser for the "Timeskjema" turnus export (misleadingly named .xls).

The export is a tab-separated ISO-8859-1 text file: per turnus a small header
(``Turnus: OSL 01``), a ``Dag ... Dv.Nr. ... KL.TID ... Tj.t`` column header,
42 weekday-labeled day rows interleaved with ``Sum uke N`` rows at accounting
boundaries (which do NOT follow calendar weeks — a Sunday-night shift is listed
in the next week's block), and a ``Totalsummer for turnus`` row. A trailing
station-summary section ("Beregninger sum per stasjoneringssted") with its own
``Totalsummer`` row must not be consumed.

Output matches ShiftScraper's JSON structure exactly, so everything downstream
(``validate_turnus_json``, stats, DB import) is source-agnostic. Structural or
arithmetic violations anywhere fail the whole parse — no partial imports.
"""

import re
from dataclasses import dataclass, field
from datetime import date

WEEKDAYS = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]
_FREE_NORMALIZE = {"X": "X", "O": "O", "T": "T", "XX": "X", "OO": "O", "TT": "T"}
_TIME_RE = re.compile(r"^\d{1,3}:\d{2}$")
_DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
_REQUIRED_COLUMNS = ["Dv.Nr.", "Start tid", "Avslutningstid", "KL.TID", "Tj.t", "SIR"]


class TimeskjemaParseError(ValueError):
    """Raised when the timeskjema file violates the expected structure."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__(
            f"Timeskjema parse failed with {len(self.errors)} error(s): "
            + "; ".join(self.errors[:5])
            + ("; ..." if len(self.errors) > 5 else "")
        )


@dataclass
class ParseResult:
    turnuser: list = field(default_factory=list)
    rutetermin_start: date | None = None
    rutetermin_end: date | None = None

    def year_id_warning(self, year_id):
        """Warn if the admin-supplied year id (e.g. 'R26') does not match the
        rutetermin end year. The 'Ruteterminperiode:' header label is known to
        be wrong in real exports, so only the dates are checked."""
        if self.rutetermin_end is None:
            return None
        m = re.search(r"(\d{2})\b", year_id or "")
        if not m:
            return None
        if 2000 + int(m.group(1)) != self.rutetermin_end.year:
            return (
                f"Årsidentifikator {year_id} samsvarer ikke med ruteterminens "
                f"sluttår {self.rutetermin_end.year} i timeskjema-filen."
            )
        return None


def sniff_format(data: bytes) -> str:
    """Classify uploaded bytes as 'timeskjema', 'pdf' or 'unknown'.

    Never guesses: a real OLE2 Excel binary, HTML, or anything else the parser
    was not written for is 'unknown' and must be refused, not best-effort parsed.
    """
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\xd0\xcf\x11\xe0"):  # OLE2 (real legacy .xls)
        return "unknown"
    text = data.decode("iso-8859-1", errors="replace")
    if text.lstrip()[:1] == "<":  # HTML/XML masquerading as .xls
        return "unknown"
    if "Timeskjema for" in text and re.search(r"^Turnus:", text, re.MULTILINE):
        return "timeskjema"
    return "unknown"


def _clean(cell):
    return cell.strip().rstrip("&").strip()


def _to_minutes(value):
    if not value:
        return 0
    m = _TIME_RE.match(value)
    if m is None:
        return None
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _new_day(ukedag):
    return {
        "ukedag": ukedag,
        "tid": [],
        "start": [],
        "slutt": "",
        "dagsverk": "",
        "is_consecutive_shift": False,
        "is_consecutive_receiver": False,
    }


def _column_indexes(block, errors):
    header = block["columns"]
    if header is None:
        errors.append(f"{block['name']}: column header row ('Dag ...') not found")
        return None
    indexes = {}
    for column in _REQUIRED_COLUMNS:
        if column not in header:
            errors.append(f"{block['name']}: required column '{column}' not found in header")
            return None
        indexes[column] = header.index(column)
    return indexes


def _cell(row, index):
    return row[index] if index < len(row) else ""


def _parse_day(name, position, row, idx, errors):
    """Classify one day row as shift / fridag / blank; anything else is a
    structural surprise and an error."""
    day = _new_day(row[0])
    dv = _cell(row, idx["Dv.Nr."])
    start = _cell(row, idx["Start tid"])
    end = _cell(row, idx["Avslutningstid"])

    if dv in _FREE_NORMALIZE and not start and not end:
        code = _FREE_NORMALIZE[dv]
        day["tid"] = [code]
        day["start"] = [code]
    elif not dv and not start and not end:
        pass  # blank sleep-off day
    elif dv and _TIME_RE.match(start or "") and _TIME_RE.match(end or ""):
        day["tid"] = [start, end]
        day["start"] = start
        day["slutt"] = end
        day["dagsverk"] = dv
    else:
        errors.append(
            f"{name}: {position} has inconsistent values "
            f"(Dv.Nr.={dv!r}, start={start!r}, slutt={end!r})"
        )
    return day


def _check_arithmetic(name, kind, day_minutes, sum_rows, total_row, idx, errors):
    """Day values must sum exactly to each 'Sum uke' row, and week sums to the
    total. Same document, same units — zero tolerance.

    Tjenestetid (Tj.t) includes the per-week SIR allowance, which appears only
    on the sum rows: declared Tj.t == sum(day Tj.t) + SIR(sum row).
    """
    column = idx[kind]
    weeks_total = 0
    for sum_row, (label, segment_sum) in zip(sum_rows, day_minutes):
        declared = _to_minutes(_cell(sum_row, column))
        if declared is None:
            errors.append(f"{name}: {sum_row[0]} has malformed {kind} value")
            continue
        weeks_total += declared
        if kind == "Tj.t":
            sir = _to_minutes(_cell(sum_row, idx["SIR"]))
            segment_sum += sir if sir is not None else 0
        if declared != segment_sum:
            errors.append(
                f"{name}: {kind} mismatch in {label}: day rows sum to "
                f"{segment_sum // 60}:{segment_sum % 60:02d} but the row declares "
                f"{declared // 60}:{declared % 60:02d}"
            )
    declared_total = _to_minutes(_cell(total_row, column))
    if declared_total is None:
        errors.append(f"{name}: Totalsummer has malformed {kind} value")
    elif declared_total != weeks_total:
        errors.append(
            f"{name}: {kind} mismatch: week sums total "
            f"{weeks_total // 60}:{weeks_total % 60:02d} but Totalsummer declares "
            f"{declared_total // 60}:{declared_total % 60:02d}"
        )


def _segment_minutes(name, kind, block, idx, errors):
    """Per accounting segment (rows between 'Sum uke' markers), the sum of the
    day rows' minutes. Relies on raw row order, not calendar mapping."""
    column = idx[kind]
    segments = []
    day_iter = iter(block["day_rows"])
    rows_per_segment = _rows_per_segment(block)
    for seg_number, row_count in enumerate(rows_per_segment, start=1):
        total = 0
        for _ in range(row_count):
            row = next(day_iter)
            minutes = _to_minutes(_cell(row, column))
            if minutes is None:
                errors.append(f"{name}: day row '{row[0]}' has malformed {kind} value")
                minutes = 0
            total += minutes
        segments.append((f"Sum uke {seg_number}", total))
    return segments


def _rows_per_segment(block):
    """How many day rows precede each 'Sum uke' row, in raw file order."""
    counts = []
    day_index = 0
    # Rebuild the interleaving: day_rows and sum_rows were collected in file
    # order, so replay it via the recorded order markers.
    for marker in block["row_order"]:
        if marker == "sum":
            counts.append(day_index)
            day_index = 0
        else:
            day_index += 1
    return counts


def parse_timeskjema(source) -> ParseResult:
    """Parse a timeskjema export from a path or raw bytes.

    Raises TimeskjemaParseError listing every violation when the file does not
    match the expected structure or its internal arithmetic is inconsistent.
    """
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
    else:
        with open(source, "rb") as f:
            data = f.read()

    text = data.decode("iso-8859-1")
    errors = []

    result = ParseResult()
    date_match = None
    for line in text.split("\n"):
        if line.startswith("Rutetermin:"):
            date_match = _DATE_RE.findall(line)
            break
    if date_match and len(date_match) == 2:
        (d0, m0, y0), (d1, m1, y1) = date_match
        result.rutetermin_start = date(int(y0), int(m0), int(d0))
        result.rutetermin_end = date(int(y1), int(m1), int(d1))

    blocks = _split_blocks_with_order(text, errors)

    for block in blocks:
        name = block["name"]
        idx = _column_indexes(block, errors)
        if idx is None:
            continue
        if block["total_row"] is None:
            errors.append(f"{name}: 'Totalsummer for turnus' row not found")
            continue

        day_rows = block["day_rows"]
        if len(day_rows) != 42:
            errors.append(f"{name}: has {len(day_rows)} day rows (expected 42)")
        turnus = {}
        for i, row in enumerate(day_rows[:42]):
            uke, dag = i // 7 + 1, i % 7 + 1
            expected = WEEKDAYS[i % 7]
            if row[0] != expected:
                errors.append(
                    f"{name}: day row {i + 1} is '{row[0]}' (expected '{expected}')"
                )
                continue
            turnus.setdefault(uke, {})[dag] = _parse_day(
                name, f"uke {uke} dag {dag}", row, idx, errors
            )
        if len(day_rows) == 42 and all(
            dag in turnus.get(uke, {}) for uke in range(1, 7) for dag in range(1, 8)
        ):
            for kind in ("KL.TID", "Tj.t"):
                segments = _segment_minutes(name, kind, block, idx, errors)
                _check_arithmetic(
                    name, kind, segments, block["sum_rows"], block["total_row"], idx, errors
                )
            turnus["kl_timer"] = _cell(block["total_row"], idx["KL.TID"])
            turnus["tj_timer"] = _cell(block["total_row"], idx["Tj.t"])
            result.turnuser.append({name: turnus})

    if errors:
        raise TimeskjemaParseError(errors)
    return result


def _split_blocks_with_order(text, errors):
    """Like _split_blocks, but also records the day/sum interleaving order
    needed to reconstruct accounting segments."""
    blocks = []
    current = None
    for line in text.split("\n"):
        cells = [_clean(c) for c in line.split("\t")]
        first = cells[0]
        if first.startswith("Turnus:"):
            current = {
                "name": first[len("Turnus:"):].strip().replace(" ", "_"),
                "columns": None,
                "day_rows": [],
                "sum_rows": [],
                "total_row": None,
                "row_order": [],
            }
            blocks.append(current)
        elif current is None or current["total_row"] is not None:
            continue
        elif first == "Dag":
            current["columns"] = cells
        elif first in WEEKDAYS:
            current["day_rows"].append(cells)
            current["row_order"].append("day")
        elif first.startswith("Sum uke"):
            current["sum_rows"].append(cells)
            current["row_order"].append("sum")
        elif first.startswith("Totalsummer for turnus"):
            current["total_row"] = cells
    if not blocks:
        errors.append("No 'Turnus:' blocks found — not a timeskjema export")
    return blocks
