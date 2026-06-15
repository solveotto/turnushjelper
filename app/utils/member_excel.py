"""Parser for the NLF member list Excel file (Medlemsoppslag).

Expected format: first worksheet with a header row containing the columns
``Navn`` ("Etternavn, Fornavn") and ``Medlemsnr`` (integer member number).
"""
import logging

from openpyxl import load_workbook

logger = logging.getLogger(__name__)


def parse_member_excel(path):
    """Parse a member-list xlsx into ``[{"name", "medlemsnummer"}, ...]``.

    Raises ``ValueError`` if the expected header columns are missing.
    """
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        # Some export tools write a bogus dimension (e.g. "A1:A1"); read-only
        # mode trusts it and would truncate the sheet. Force a full read.
        ws.reset_dimensions()
        rows = ws.iter_rows(values_only=True)

        header = next(rows, None)
        if header is None:
            raise ValueError("Excel-fila er tom")
        col_index = {
            str(cell).strip().casefold(): i
            for i, cell in enumerate(header)
            if cell is not None
        }
        if "navn" not in col_index or "medlemsnr" not in col_index:
            raise ValueError(
                "Fant ikke kolonnene 'Navn' og 'Medlemsnr' i Excel-fila"
            )
        name_col = col_index["navn"]
        mnr_col = col_index["medlemsnr"]

        members = []
        for row in rows:
            name = row[name_col] if len(row) > name_col else None
            mnr = row[mnr_col] if len(row) > mnr_col else None
            if name is None and mnr is None:
                continue
            if isinstance(mnr, float) and mnr.is_integer():
                mnr = int(mnr)
            members.append(
                {
                    "name": str(name).strip() if name is not None else "",
                    "medlemsnummer": str(mnr).strip() if mnr is not None else "",
                }
            )
        logger.info("parse_member_excel: %d rows parsed from %s", len(members), path)
        return members
    finally:
        wb.close()
