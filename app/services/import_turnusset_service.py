"""Staging and finalization for turnusset imports.

A timeskjema import that needs admin adjudication (PDF cross-verification found
differences) is staged under the Flask instance dir — deliberately outside
``app/static/`` so unapproved data is never publicly served — and finalized
only when the admin approves it on the review page.

Layout: ``instance/pending_import/{year_id}/`` containing pending_import.json
(parsed turnus data), pending_diff.json, pending_meta.json (form state,
uploader, timestamp), the uploaded timeskjema file and, when provided, the
verification PDF. A new upload for the same year overwrites the directory, so
abandoned stagings never block.
"""

import json
import os
import re
import shutil
from datetime import datetime, timezone

from flask import current_app

from config import AppConfig

_YEAR_ID_RE = re.compile(r"^[A-Za-z0-9_-]{2,10}$")


def is_valid_year_id(year_id):
    """Guard for year ids used in filesystem paths (no traversal)."""
    return bool(year_id) and _YEAR_ID_RE.match(year_id) is not None


def _pending_root():
    return os.path.join(current_app.instance_path, "pending_import")


def pending_dir(year_id):
    return os.path.join(_pending_root(), year_id.upper())


def stage_pending_import(year_id, turnuser, diff, meta, timeskjema_bytes, pdf_bytes=None):
    """Write all approval state to the pending dir, replacing any previous
    staging for the same year."""
    directory = pending_dir(year_id)
    shutil.rmtree(directory, ignore_errors=True)
    os.makedirs(directory)

    meta = dict(meta, staged_at=datetime.now(timezone.utc).isoformat())
    with open(os.path.join(directory, "pending_import.json"), "w") as f:
        json.dump(turnuser, f, indent=4)
    with open(os.path.join(directory, "pending_diff.json"), "w") as f:
        json.dump(diff, f, indent=4)
    with open(os.path.join(directory, "pending_meta.json"), "w") as f:
        json.dump(meta, f, indent=4)
    with open(os.path.join(directory, f"turnuser_{year_id.upper()}.xls"), "wb") as f:
        f.write(timeskjema_bytes)
    if pdf_bytes:
        with open(os.path.join(directory, f"turnuser_{year_id.upper()}.pdf"), "wb") as f:
            f.write(pdf_bytes)


def load_pending_import(year_id):
    """Return {'turnuser', 'diff', 'meta'} for a staged import, or None."""
    directory = pending_dir(year_id)
    try:
        with open(os.path.join(directory, "pending_import.json")) as f:
            turnuser = json.load(f)
        with open(os.path.join(directory, "pending_diff.json")) as f:
            diff = json.load(f)
        with open(os.path.join(directory, "pending_meta.json")) as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return None
    return {"turnuser": turnuser, "diff": diff, "meta": meta}


def clear_pending_import(year_id):
    shutil.rmtree(pending_dir(year_id), ignore_errors=True)


def list_pending_imports():
    """[{year_id, meta}] for every staged import, for the manage page."""
    root = _pending_root()
    if not os.path.isdir(root):
        return []
    pending = []
    for year_id in sorted(os.listdir(root)):
        staged = load_pending_import(year_id)
        if staged is not None:
            pending.append({"year_id": year_id, "meta": staged["meta"]})
    return pending


def finalize_turnusset_import(year_id, name, is_active, turnuser):
    """Complete an import: write the live schedule JSON, move staged source
    files into turnusfiler, generate stats, create the TurnusSet row and its
    shifts. Returns (success, message).

    Called both by the direct create flow (no staging round-trip; source files
    are staged first either way so there is a single move-into-place path) and
    by the approval endpoint.
    """
    from app.services import turnus_service
    from app.utils.shift_stats import Turnus

    year_id = year_id.upper()
    version_dir = os.path.join(AppConfig.static_dir, "turnusfiler", year_id.lower())
    os.makedirs(version_dir, exist_ok=True)

    turnus_json_path = os.path.join(version_dir, f"turnus_schedule_{year_id}.json")
    with open(turnus_json_path, "w") as f:
        json.dump(turnuser, f, indent=4)

    staged = pending_dir(year_id)
    staged_timeskjema = os.path.join(staged, f"turnuser_{year_id}.xls")
    if os.path.exists(staged_timeskjema):
        shutil.copy(staged_timeskjema, os.path.join(version_dir, f"turnuser_{year_id}.xls"))
    staged_pdf = os.path.join(staged, f"turnuser_{year_id}.pdf")
    if os.path.exists(staged_pdf):
        pdf_dir = os.path.join(version_dir, "pdf")
        os.makedirs(pdf_dir, exist_ok=True)
        shutil.copy(staged_pdf, os.path.join(pdf_dir, f"turnuser_{year_id}.pdf"))

    stats = Turnus(turnus_json_path)
    df_json_path = os.path.join(version_dir, f"turnus_stats_{year_id}.json")
    stats.stats_df.to_json(df_json_path)

    success, message = turnus_service.create_turnus_set(
        name=name,
        year_identifier=year_id,
        is_active=is_active,
        turnus_file_path=turnus_json_path,
        df_file_path=df_json_path,
    )
    if not success:
        return False, message

    turnus_set = turnus_service.get_turnus_set_by_year(year_id)
    if not turnus_set:
        return False, "Turnussett opprettet, men kunne ikke hentes for vaktimport."
    turnus_service.add_shifts_to_turnus_set(turnus_json_path, turnus_set["id"])

    clear_pending_import(year_id)
    return True, f"Turnussett {year_id} opprettet!"
