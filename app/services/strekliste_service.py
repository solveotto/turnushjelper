"""Store what the strekliste parser read, and hand it back per duty.

A turnus set's rows are replaced wholesale on every parse: this is the plan
for a rutetermin as the PDF states it, not a record anyone acted on, so
there is no history to preserve and nothing to mark as superseded.
"""

import logging
import re
from collections import Counter

from app.database import get_db_session
from app.models import StreklisteAktivitet, StreklisteDagsverk

logger = logging.getLogger(__name__)

_BASE = re.compile(r"^\d+")

AKTIVITET_FELT = (
    "radnr", "fra_tid", "til_tid", "fra_neste_dag", "til_neste_dag",
    "fra_stasjon", "til_stasjon", "type", "monster", "tognumre", "tekst",
)


def nr_base(nr):
    m = _BASE.match(nr or "")
    return m.group(0) if m else ""


def lagre_parse(turnus_set_id, res):
    """Replace the turnus set's strekliste rows with a ParseResult's duties."""
    db_session = get_db_session()
    try:
        gamle = [r.id for r in db_session.query(StreklisteDagsverk.id)
                 .filter_by(turnus_set_id=turnus_set_id).all()]
        if gamle:
            (db_session.query(StreklisteAktivitet)
             .filter(StreklisteAktivitet.dagsverk_id.in_(gamle))
             .delete(synchronize_session=False))
            (db_session.query(StreklisteDagsverk)
             .filter(StreklisteDagsverk.id.in_(gamle))
             .delete(synchronize_session=False))

        antall_akt = 0
        per_sted = Counter()
        med_advarsler = 0
        for d in res.duties:
            rad = StreklisteDagsverk(
                turnus_set_id=turnus_set_id,
                stasjoneringssted=d.get("stasjoneringssted"),
                nr=d["nr"],
                nr_base=nr_base(d["nr"]),
                kjoredager=d.get("kjoredager") or "",
                dobbelt_tur=d.get("dobbelt_tur"),
                materiell=d.get("materiell"),
                start=d.get("start"),
                slutt=d.get("slutt"),
                slutt_neste_dag=int(d.get("slutt_neste_dag") or 0),
                side=d.get("side"),
                beregninger=d.get("beregninger"),
                kommentar=d.get("kommentar"),
                advarsler=d.get("advarsler") or None,
            )
            for a in d.get("aktiviteter", []):
                rad.aktiviteter.append(StreklisteAktivitet(**{f: a.get(f) for f in AKTIVITET_FELT}))
                antall_akt += 1
            db_session.add(rad)
            per_sted[d.get("stasjoneringssted")] += 1
            if d.get("advarsler"):
                med_advarsler += 1
        db_session.commit()
        return {
            "dagsverk": len(res.duties),
            "aktiviteter": antall_akt,
            "advarsler": med_advarsler,
            "sidevarsler": list(res.warnings),
            "per_sted": dict(per_sted),
            "slettet": len(gamle),
        }
    except Exception:
        db_session.rollback()
        raise
    finally:
        db_session.close()


def import_strekliste(turnus_set_id, pdf_path):
    """Parse the PDF and store it. Raises on an unreadable file."""
    from app.utils.pdf.strekliste_parser import parse_strekliste

    res = parse_strekliste(pdf_path)
    rapport = lagre_parse(turnus_set_id, res)
    logger.info("Strekliste importert for turnus_set %s: %s dagsverk, %s aktiviteter, %s med advarsler",
                turnus_set_id, rapport["dagsverk"], rapport["aktiviteter"], rapport["advarsler"])
    return rapport


def _aktivitet_dict(a):
    return {f: getattr(a, f) for f in AKTIVITET_FELT}


def _dagsverk_dict(rad, med_aktiviteter=True):
    d = {
        "id": rad.id,
        "turnus_set_id": rad.turnus_set_id,
        "stasjoneringssted": rad.stasjoneringssted,
        "nr": rad.nr,
        "nr_base": rad.nr_base,
        "kjoredager": rad.kjoredager,
        "dobbelt_tur": rad.dobbelt_tur,
        "materiell": rad.materiell,
        "start": rad.start,
        "slutt": rad.slutt,
        "slutt_neste_dag": rad.slutt_neste_dag,
        "side": rad.side,
        "beregninger": rad.beregninger,
        "kommentar": rad.kommentar,
        "advarsler": rad.advarsler or [],
    }
    if med_aktiviteter:
        d["aktiviteter"] = [_aktivitet_dict(a) for a in rad.aktiviteter]
    return d


def hent_dagsverk(turnus_set_id, nr, ukedag=None):
    """One duty with its activities, or None.

    ``nr`` may be the number as printed or just its digits; ``ukedag`` (ISO,
    1=Monday) picks between variants of one number that run on different
    days, and a variant that does not run that day is not an answer.
    """
    db_session = get_db_session()
    try:
        q = db_session.query(StreklisteDagsverk).filter_by(turnus_set_id=turnus_set_id)
        rader = q.filter_by(nr=nr).all() or q.filter_by(nr_base=nr_base(nr)).all()
        if ukedag is not None:
            rader = [r for r in rader if str(ukedag) in (r.kjoredager or "")]
        if not rader:
            return None
        rader.sort(key=lambda r: (r.nr, r.kjoredager))
        return _dagsverk_dict(rader[0])
    finally:
        db_session.close()


def list_dagsverk(turnus_set_id, stasjoneringssted=None):
    """Every duty header for a turnus set, in page order, without activities."""
    db_session = get_db_session()
    try:
        q = db_session.query(StreklisteDagsverk).filter_by(turnus_set_id=turnus_set_id)
        if stasjoneringssted:
            q = q.filter_by(stasjoneringssted=stasjoneringssted)
        rader = q.order_by(StreklisteDagsverk.side, StreklisteDagsverk.id).all()
        return [_dagsverk_dict(r, med_aktiviteter=False) for r in rader]
    finally:
        db_session.close()
