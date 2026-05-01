import logging

from app.database import get_db_session
from app.models import Innplassering

logger = logging.getLogger(__name__)


def import_innplassering(pdf_path: str, turnus_set_id: int, json_path: str) -> tuple[bool, str]:
    """Scrape Innplassering PDF and replace all records for this turnus set in the DB.

    Returns (True, summary_message) on success or (False, error_message) on failure.
    """
    from app.utils.pdf.innplassering_scraper import scrape_innplassering

    try:
        records = scrape_innplassering(pdf_path, json_path)
    except Exception as e:
        logger.error("Error scraping innplassering PDF: %s", e)
        return False, f"Feil ved lesing av PDF: {e}"

    if not records:
        return False, "Ingen poster funnet i PDF-en."

    db_session = get_db_session()
    try:
        # Replace all existing records for this turnus set
        deleted = db_session.query(Innplassering).filter_by(turnus_set_id=turnus_set_id).delete()
        for rec in records:
            db_session.add(Innplassering(
                turnus_set_id=turnus_set_id,
                rullenummer=rec["rullenummer"],
                shift_title=rec["shift_title"],
                linjenummer=rec["linjenummer"],
                ans_nr=rec["ans_nr"],
                is_7th_driver=rec["is_7th_driver"],
            ))

        db_session.commit()
        msg = f"Innplassering importert: {len(records)} poster ({deleted} gamle slettet)."
        logger.info(msg)
        return True, msg
    except Exception as e:
        db_session.rollback()
        logger.error("DB error during innplassering import: %s", e)
        return False, f"Databasefeil: {e}"
    finally:
        db_session.close()


def get_innplassering_by_turnus_set(turnus_set_id: int) -> list[dict]:
    """Return all innplassering records for a turnus set."""
    db_session = get_db_session()
    try:
        rows = db_session.query(Innplassering).filter_by(turnus_set_id=turnus_set_id).all()
        return [
            {
                "id": r.id,
                "turnus_set_id": r.turnus_set_id,
                "rullenummer": r.rullenummer,
                "shift_title": r.shift_title,
                "linjenummer": r.linjenummer,
                "ans_nr": r.ans_nr,
                "is_7th_driver": r.is_7th_driver,
            }
            for r in rows
        ]
    finally:
        db_session.close()


def get_innplassering_for_user(user_id: int) -> list[dict]:
    """Return all innplassering records for the user across all turnus sets.

    Looks up DBUser.rullenummer, then queries Innplassering joined with TurnusSet.
    Returns [] if user has no rullenummer or no innplassering records.
    """
    db_session = get_db_session()
    try:
        from app.models import DBUser, TurnusSet
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user or not user.rullenummer:
            return []
        rows = (
            db_session.query(Innplassering, TurnusSet)
            .join(TurnusSet, Innplassering.turnus_set_id == TurnusSet.id)
            .filter(Innplassering.rullenummer == str(user.rullenummer))
            .order_by(TurnusSet.id.desc())
            .all()
        )
        return [
            {
                "turnus_set_id": inn.turnus_set_id,
                "rullenummer": inn.rullenummer,
                "shift_title": inn.shift_title,
                "linjenummer": inn.linjenummer,
                "ans_nr": inn.ans_nr,
                "is_7th_driver": inn.is_7th_driver,
                "turnus_set_name": ts.name,
                "year_identifier": ts.year_identifier,
            }
            for inn, ts in rows
        ]
    finally:
        db_session.close()


def get_shift_for_rullenummer(rullenummer: str, turnus_set_id: int) -> dict | None:
    """Return the innplassering record for a specific driver in a turnus set."""
    db_session = get_db_session()
    try:
        row = db_session.query(Innplassering).filter_by(
            turnus_set_id=turnus_set_id,
            rullenummer=str(rullenummer),
        ).first()
        if row:
            return {
                "id": row.id,
                "turnus_set_id": row.turnus_set_id,
                "rullenummer": row.rullenummer,
                "shift_title": row.shift_title,
                "linjenummer": row.linjenummer,
                "ans_nr": row.ans_nr,
                "is_7th_driver": row.is_7th_driver,
            }
        return None
    finally:
        db_session.close()
