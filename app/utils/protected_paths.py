"""Paths for files containing member/employee PII.

These files (NLF member list, seniority list, innplassering PDFs) must never
live under app/static/ — the static tree is served without authentication by
both Flask and nginx. They are stored in AppConfig.protected_dir
(instance/protected/), which is gitignored and never web-served.
tests/test_protected_files.py guards this invariant.
"""

import os
import re

from config import AppConfig

_YEAR_ID_RE = re.compile(r"^[A-Za-z0-9]+$")


def ensure_protected_dir() -> str:
    """Create the protected dir if missing; return its path. Call before writes."""
    os.makedirs(AppConfig.protected_dir, exist_ok=True)
    return AppConfig.protected_dir


def ensure_parent_dir(path: str) -> str:
    """Create a path's parent dir if missing; return the path. Call before writes."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def member_excel_path() -> str:
    """Storage path for the uploaded NLF member list (medlemsliste.xlsx)."""
    return os.path.join(AppConfig.protected_dir, "medlemsliste.xlsx")


def ansinitet_pdf_path() -> str:
    """Storage path for the uploaded seniority-list PDF (ansinitet.pdf)."""
    return os.path.join(AppConfig.protected_dir, "ansinitet.pdf")


def innplassering_pdf_path(year_identifier: str) -> str:
    """Storage path for a turnus set's innplassering PDF.

    year_identifier is validated at the form layer (CreateTurnusSetForm), but
    it becomes a filename component here, so re-check it as defense in depth.
    """
    if not _YEAR_ID_RE.match(year_identifier or ""):
        raise ValueError(f"Invalid year identifier: {year_identifier!r}")
    # Per-set subdir, mirroring the turnusfiler/{rxx}/ convention.
    return os.path.join(
        AppConfig.protected_dir,
        year_identifier.lower(),
        f"innplassering_{year_identifier}.pdf",
    )
