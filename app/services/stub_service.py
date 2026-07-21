"""Stub-user lifecycle — create / activate / list / delete / reset — plus the
rullenummer/medlemsnummer identity lookups, extracted from ``user_service.py``.

Imports shared helpers from :mod:`app.services.user_helpers` (a leaf module)
rather than from ``user_service``, so there is no circular import.
``user_service`` re-exports these functions for backward compatibility with
callers that reference them as ``user_service.<name>``.
"""

import logging
import secrets

from sqlalchemy import func

from app.database import get_db_session
from app.models import DBUser
from app.services.user_helpers import (
    _user_identity_dict,
    _username_filter,
    hash_password,
    normalize_medlemsnummer,
)

logger = logging.getLogger(__name__)


def get_user_by_rullenummer(rullenummer):
    """Get user by rullenummer"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(rullenummer=str(rullenummer)).first()
        return _user_identity_dict(user) if user else None
    finally:
        db_session.close()


def get_user_by_medlemsnummer(medlemsnummer):
    """Get user by NLF-medlemsnummer"""
    db_session = get_db_session()
    try:
        user = (
            db_session.query(DBUser)
            .filter_by(medlemsnummer=normalize_medlemsnummer(medlemsnummer))
            .first()
        )
        return _user_identity_dict(user) if user else None
    finally:
        db_session.close()


def create_stub_user(
    etternavn,
    fornavn,
    medlemsnummer,
    rullenummer=None,
    stasjoneringssted=None,
    ans_dato=None,
    fodt_dato=None,
    seniority_nr=None,
):
    """Create a stub user for an employee who hasn't registered yet.

    NLF-medlemsnummer is the required identifier; rullenummer is optional
    HR data. Uses a reserved username prefix ``__stub_m<medlemsnummer>``
    and a random unusable password so the account cannot be logged into
    directly.
    """
    db_session = get_db_session()
    try:
        medlemsnummer = normalize_medlemsnummer(medlemsnummer)
        if not medlemsnummer:
            return False, "NLF-medlemsnummer er påkrevd"

        existing = (
            db_session.query(DBUser).filter_by(medlemsnummer=medlemsnummer).first()
        )
        if existing:
            return False, "NLF-medlemsnummeret finnes allerede"

        if rullenummer:
            existing_rnr = (
                db_session.query(DBUser)
                .filter_by(rullenummer=str(rullenummer))
                .first()
            )
            if existing_rnr:
                return False, "Rullenummeret finnes allerede"

        stub = DBUser(
            username=f"__stub_m{medlemsnummer}",
            password=hash_password(secrets.token_hex(32)),
            name=f"{etternavn}, {fornavn}",
            medlemsnummer=medlemsnummer,
            rullenummer=str(rullenummer) if rullenummer else None,
            is_stub=1,
            email_verified=0,
            is_auth=0,
            stasjoneringssted=stasjoneringssted,
            ans_dato=ans_dato,
            fodt_dato=fodt_dato,
            seniority_nr=seniority_nr,
        )
        db_session.add(stub)
        db_session.commit()
        logger.info("Stub user created for medlemsnummer %s", medlemsnummer)
        return True, "Stub opprettet"
    except Exception as e:
        db_session.rollback()
        logger.error("Error creating stub user: %s", e)
        return False, f"Feil ved oppretting: {e}"
    finally:
        db_session.close()


def activate_stub_user(user_id, username, email, password, rullenummer=None):
    """Activate a stub user with real credentials.

    Returns ``(bool, str, user_id|None)`` — same shape as
    ``create_user_with_email()`` so registration callers need no branching.
    """
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet", None
        if (user.is_stub or 0) != 1:
            return False, "Bruker er ikke en stub-bruker", None

        # Uniqueness checks
        existing_username = (
            db_session.query(DBUser).filter(_username_filter(username)).first()
        )
        if existing_username and existing_username.id != user_id:
            return False, "Brukernavnet er allerede tatt", None

        existing_email = db_session.query(DBUser).filter_by(email=email.lower()).first()
        if existing_email and existing_email.id != user_id:
            return False, "E-postadressen er allerede registrert", None

        user.username = username
        user.email = email.lower()
        user.password = hash_password(password)
        user.is_stub = 0
        user.email_verified = 0
        if rullenummer and not user.rullenummer:
            taken = (
                db_session.query(DBUser)
                .filter(DBUser.rullenummer == str(rullenummer), DBUser.id != user_id)
                .first()
            )
            if taken:
                return False, "Rullenummeret er allerede i bruk av en annen bruker", None
            user.rullenummer = str(rullenummer)
        db_session.commit()
        logger.info("Stub user %s activated as %s", user_id, username)
        return True, "Aktivert", user_id
    except Exception as e:
        db_session.rollback()
        logger.error("Error activating stub user %s: %s", user_id, e)
        return False, f"Feil ved aktivering: {e}", None
    finally:
        db_session.close()


def get_all_stub_users():
    """Get all users ordered by seniority_nr (nulls last), with registration status.

    ``is_registered`` is True when the user has activated their stub account
    (is_stub == 0 and email is set).
    """
    db_session = get_db_session()
    try:
        users = (
            db_session.query(
                DBUser.id,
                DBUser.rullenummer,
                DBUser.medlemsnummer,
                DBUser.name,
                DBUser.stasjoneringssted,
                DBUser.ans_dato,
                DBUser.fodt_dato,
                DBUser.seniority_nr,
                DBUser.is_stub,
                DBUser.is_auth,
                DBUser.email,
                DBUser.username,
                DBUser.not_on_nlf_list,
            )
            .order_by(
                func.coalesce(DBUser.seniority_nr, 999999).asc(),
                DBUser.id.asc(),
            )
            .all()
        )
        result = []
        for u in users:
            is_registered = (u.is_stub or 0) == 0 and u.email is not None
            # name is stored as "Etternavn, Fornavn" for stub-created users
            if u.name and "," in u.name:
                parts = u.name.split(",", 1)
                etternavn = parts[0].strip()
                fornavn = parts[1].strip()
            else:
                etternavn = u.name or ""
                fornavn = ""
            result.append(
                {
                    "id": u.id,
                    "rullenummer": u.rullenummer,
                    "medlemsnummer": u.medlemsnummer,
                    "name": u.name,
                    "etternavn": etternavn,
                    "fornavn": fornavn,
                    "stasjoneringssted": u.stasjoneringssted,
                    "ans_dato": u.ans_dato,
                    "fodt_dato": u.fodt_dato,
                    "seniority_nr": u.seniority_nr,
                    "is_stub": u.is_stub or 0,
                    "is_auth": u.is_auth or 0,
                    "email": u.email,
                    "username": u.username,
                    "is_registered": is_registered,
                    "not_on_nlf_list": u.not_on_nlf_list or 0,
                }
            )
        return result
    finally:
        db_session.close()


def delete_missing_stubs():
    """Delete all unregistered stub users that are no longer on the current PDF.

    Targets only rows where ``is_stub=1`` AND ``seniority_nr IS NULL``
    AND ``rullenummer IS NOT NULL`` AND ``medlemsnummer IS NULL``.
    Stubs with a medlemsnummer are kept — they are on the NLF member list
    and must remain available for self-registration. Registered users
    missing from the list (is_stub=0) are left completely untouched.

    Returns ``(bool, str, int)`` — success, message, number deleted.
    """
    from app.models import Favorites as FavModel

    db_session = get_db_session()
    try:
        targets = (
            db_session.query(DBUser)
            .filter(
                DBUser.is_stub == 1,
                DBUser.seniority_nr.is_(None),
                DBUser.rullenummer.isnot(None),
                DBUser.medlemsnummer.is_(None),
            )
            .all()
        )
        count = len(targets)
        if count:
            ids = [u.id for u in targets]
            db_session.query(FavModel).filter(FavModel.user_id.in_(ids)).delete(synchronize_session=False)
            db_session.query(DBUser).filter(DBUser.id.in_(ids)).delete(synchronize_session=False)
        db_session.commit()
        logger.info("delete_missing_stubs: deleted %d rows", count)
        return True, f"{count} stub-brukere slettet.", count
    except Exception as e:
        db_session.rollback()
        logger.error("Error deleting missing stubs: %s", e)
        return False, f"Feil ved sletting: {e}", 0
    finally:
        db_session.close()


def delete_stub_users(user_ids):
    """Bulk-delete specific stub users by id.

    Used for the medlemsliste "not on list" review report's bulk-cleanup
    button. Any id in ``user_ids`` belonging to a registered (non-stub)
    user is silently skipped — this never deletes a registered account.

    Returns ``(bool, str, int)`` — success, message, number deleted.
    """
    from app.models import Favorites as FavModel

    db_session = get_db_session()
    try:
        targets = (
            db_session.query(DBUser)
            .filter(DBUser.id.in_(user_ids), DBUser.is_stub == 1)
            .all()
        )
        count = len(targets)
        if count:
            ids = [u.id for u in targets]
            db_session.query(FavModel).filter(FavModel.user_id.in_(ids)).delete(synchronize_session=False)
            db_session.query(DBUser).filter(DBUser.id.in_(ids)).delete(synchronize_session=False)
        db_session.commit()
        logger.info("delete_stub_users: deleted %d of %d requested ids", count, len(user_ids))
        return True, f"{count} stub-brukere slettet.", count
    except Exception as e:
        db_session.rollback()
        logger.error("Error bulk-deleting stub users: %s", e)
        return False, f"Feil ved sletting: {e}", 0
    finally:
        db_session.close()


def delete_all_stubs() -> tuple[bool, str, int]:
    """Delete every stub user (is_stub=1). Registered users are never touched."""
    from app.models import Favorites as FavModel

    db_session = get_db_session()
    try:
        stub_ids = [row.id for row in db_session.query(DBUser.id).filter_by(is_stub=1).all()]
        if not stub_ids:
            return True, "Ingen stub-brukere å slette.", 0
        db_session.query(FavModel).filter(FavModel.user_id.in_(stub_ids)).delete(synchronize_session=False)
        db_session.query(DBUser).filter(DBUser.id.in_(stub_ids)).delete(synchronize_session=False)
        db_session.commit()
        logger.info("delete_all_stubs: deleted %d stub users", len(stub_ids))
        return True, f"{len(stub_ids)} stub-brukere slettet.", len(stub_ids)
    except Exception as e:
        db_session.rollback()
        logger.error("Error deleting all stubs: %s", e)
        return False, f"Feil ved sletting: {e}", 0
    finally:
        db_session.close()


def reset_user_to_stub(user_id):
    """Reset a registered user back to stub state, preserving all their favorites.

    Clears email, replaces password with a random unusable hash, resets
    username to ``__stub_m<medlemsnummer>`` (or ``__stub_<rullenummer>``
    for legacy users without one), and sets is_stub=1.
    The user row and all Favorites rows are kept intact.

    Returns ``(bool, str)``.
    """
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"
        if (user.is_stub or 0) == 1:
            return False, "Bruker er allerede en stub"
        if not user.medlemsnummer and not user.rullenummer:
            return False, "Kan ikke tilbakestille bruker uten NLF-medlemsnummer"

        if user.medlemsnummer:
            user.username = f"__stub_m{user.medlemsnummer}"
        else:
            user.username = f"__stub_{user.rullenummer}"
        user.email = None
        user.password = hash_password(secrets.token_hex(32))
        user.is_stub = 1
        user.email_verified = 0
        user.is_auth = 0
        user.has_seen_turnusliste_tour = 0

        db_session.commit()
        logger.info("User %s reset to stub (favorites preserved)", user_id)
        return True, "Brukerkonto tilbakestilt til stub. Favoritter er beholdt."
    except Exception as e:
        db_session.rollback()
        logger.error("Error resetting user %s to stub: %s", user_id, e)
        return False, f"Feil ved tilbakestilling: {e}"
    finally:
        db_session.close()
