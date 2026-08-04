"""
Guards the on-disk form of the tracked double_shifts_{year}.json files.

Background (2026-08-04): the file is both generated and tracked — every
strekliste regeneration rewrites it, including on the servers. The scanner used
to return `list(set(delt_dagsverk_shifts))`, whose order follows Python's
randomized string hash seed, so each regeneration produced a semantically empty
30-line diff. That diff blocked `git pull` on staging.

The fix is that scan_double_shifts() emits `sorted(set(...))`. These tests pin
the resulting file contract, which is what actually determines whether a
regeneration shows up in `git status`. scan_double_shifts() itself can't be
exercised here — it needs the strekliste PDF, which is gitignored.

No DB or Flask app fixtures needed — file checks only.
"""

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_DOUBLE_SHIFT_FILES = sorted(_ROOT.glob("turnusdata/*/double_shifts_*.json"))


def test_double_shift_files_exist():
    """Tracked dataset files — an empty glob means the guard is silently dead."""
    assert _DOUBLE_SHIFT_FILES, "no tracked double_shifts_*.json found under turnusdata/"


@pytest.mark.parametrize("path", _DOUBLE_SHIFT_FILES, ids=lambda p: p.parent.name)
def test_delt_dagsverk_is_sorted_and_unique(path):
    """Regenerating must be byte-stable, so the list is sorted with no duplicates."""
    data = json.loads(path.read_text(encoding="utf-8"))
    delt_dagsverk = data["delt_dagsverk"]

    assert delt_dagsverk == sorted(delt_dagsverk), (
        f"{path.name} has hash-ordered delt_dagsverk — regenerating it will "
        f"churn the file and block git pull on the servers"
    )
    assert len(delt_dagsverk) == len(set(delt_dagsverk)), (
        f"{path.name} has duplicate delt_dagsverk entries"
    )


@pytest.mark.parametrize("path", _DOUBLE_SHIFT_FILES, ids=lambda p: p.parent.name)
def test_file_ends_with_newline(path):
    """A missing trailing newline makes every diff touch the last line too."""
    assert path.read_text(encoding="utf-8").endswith("\n"), (
        f"{path.name} is missing a trailing newline"
    )
