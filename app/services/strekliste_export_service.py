"""Export a turnus set's parsed strekliste as one gzipped JSON file.

The sibling nlfstreik app imports this into its dagsverk_mal tables, the same
way it imports turnusplan_<Y>.json.gz. Unlike the roster export this names no
people — it is the duty plan as the PDF prints it — but it lives in the same
per-version data directory for the same operational reasons.

Payload:
    {"kode": "R26", "eksportert_at": "...", "antall": N,
     "dagsverk": [{...header..., "aktiviteter": [{...}, ...]}, ...]}
"""

import datetime
import gzip
import json
import os

from app.database import get_db_session
from app.models import StreklisteDagsverk, TurnusSet
from app.services.strekliste_service import _dagsverk_dict


def default_path(year_identifier):
    from config import AppConfig

    kode = year_identifier.upper()
    return os.path.join(AppConfig.turnusfiler_dir, kode.lower(), f"strekliste_{kode}.json.gz")


def build_payload(turnus_set_id):
    db_session = get_db_session()
    try:
        ts = db_session.query(TurnusSet).filter_by(id=turnus_set_id).first()
        if ts is None:
            raise ValueError(f"Turnus-sett {turnus_set_id} finnes ikke.")
        rader = (
            db_session.query(StreklisteDagsverk)
            .filter_by(turnus_set_id=turnus_set_id)
            .order_by(StreklisteDagsverk.side, StreklisteDagsverk.id)
            .all()
        )
        if not rader:
            raise ValueError(f"Ingen strekliste er lest inn for {ts.year_identifier}.")
        dagsverk = []
        for r in rader:
            d = _dagsverk_dict(r)
            d.pop("id")
            d.pop("turnus_set_id")
            dagsverk.append(d)
        return {
            "kode": ts.year_identifier.upper(),
            "eksportert_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "antall": len(dagsverk),
            "dagsverk": dagsverk,
        }
    finally:
        db_session.close()


def export(turnus_set_id, out_path):
    """Write the payload gzipped; returns {"dagsverk": N, "sti": out_path}."""
    payload = build_payload(turnus_set_id)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with gzip.open(out_path, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    return {"dagsverk": payload["antall"], "sti": out_path}
