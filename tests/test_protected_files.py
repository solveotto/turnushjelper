"""
Guards against member/employee PII being exposed through the public static tree.

Background (2026-07-18 audit): medlemsliste.xlsx, ansinitet.pdf and the
innplassering PDFs were stored under app/static/turnusfiler/, which Flask and
nginx serve without authentication. These tests pin the fix: PII files live in
the gitignored AppConfig.protected_dir (instance/protected/), never under
app/static/, and are never tracked by git.

No DB or Flask app fixtures needed — file-tree and path checks only.
"""

import os
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_STATIC = _ROOT / "app" / "static"

# Filename patterns that identify member/employee PII files.
_PII_PATTERNS = [
    "medlemsliste*.xls*",
    "ansinitet*.pdf",
    "innplassering*.pdf",
    "Innplassering*.pdf",
]


def test_no_pii_files_in_static_tree():
    offenders = []
    for pattern in _PII_PATTERNS:
        offenders.extend(_STATIC.rglob(pattern))
    assert offenders == [], (
        "PII files found under app/static/ (served without authentication): "
        f"{[str(p.relative_to(_ROOT)) for p in offenders]}. "
        "Move them to AppConfig.protected_dir (instance/protected/)."
    )


def test_git_does_not_track_pii_files():
    tracked = subprocess.run(
        ["git", "ls-files", "app/static"],
        cwd=_ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    offenders = [
        f for f in tracked
        if any(Path(f).match(pattern) for pattern in _PII_PATTERNS)
    ]
    assert offenders == [], (
        f"PII files tracked by git under app/static/: {offenders}. "
        "Remove with git rm --cached and store them in instance/protected/."
    )


def test_protected_paths_are_outside_static():
    from config import AppConfig
    from app.utils import protected_paths

    paths = [
        protected_paths.member_excel_path(),
        protected_paths.ansinitet_pdf_path(),
        protected_paths.innplassering_pdf_path("R26"),
    ]
    for path in paths:
        assert os.path.commonpath([path, AppConfig.static_dir]) != AppConfig.static_dir, (
            f"{path} resolves inside the public static tree"
        )
        assert os.path.commonpath([path, AppConfig.protected_dir]) == AppConfig.protected_dir, (
            f"{path} is not under AppConfig.protected_dir"
        )


def test_innplassering_pdf_is_grouped_per_turnus_set():
    """Per-set files live in a per-set subdir (mirrors turnusfiler/{rxx}/)."""
    from config import AppConfig
    from app.utils import protected_paths

    path = protected_paths.innplassering_pdf_path("R26")
    assert path == os.path.join(
        AppConfig.protected_dir, "r26", "innplassering_R26.pdf"
    )


def test_innplassering_pdf_path_rejects_path_traversal():
    from app.utils import protected_paths
    import pytest

    for bad in ("../evil", "r26/../..", "a/b", "r26\\evil"):
        with pytest.raises(ValueError):
            protected_paths.innplassering_pdf_path(bad)
