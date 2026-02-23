import logging
import secrets

import bcrypt
from sqlalchemy import func

from app.database import get_db_session
from app.models import DBUser, Favorites

logger = logging.getLogger(__name__)


def hash_password(password):
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed_pw.decode("utf-8")


def create_new_user(username, password, is_auth):
    db_session = get_db_session()
    try:
        new_user = DBUser(
            username=username, password=hash_password(password), is_auth=is_auth
        )
        db_session.add(new_user)
        db_session.commit()
        logger.info("User created")
        return True, "Bruker opprettet"
    except Exception as e:
        db_session.rollback()
        logger.error("Error creating user: %s", e)
        return False, f"Error creating user: {e}"
    finally:
        db_session.close()


def get_user_data(username_or_email):
    """Get user data by username or email"""
    db_session = get_db_session()
    try:
        result = db_session.query(DBUser).filter_by(username=username_or_email).first()

        if not result:
            result = (
                db_session.query(DBUser)
                .filter_by(email=username_or_email.lower())
                .first()
            )

        if result:
            data = {
                "id": result.id,
                "username": result.username,
                "password": result.password,
                "is_auth": result.is_auth,
                "email": result.email,
                "email_verified": result.email_verified,
                "is_stub": result.is_stub or 0,
            }
            return data
        else:
            logger.warning("User not found: %s", username_or_email)
            return None
    finally:
        db_session.close()


def get_user_password(username):
    db_session = get_db_session()
    try:
        result = db_session.query(DBUser.password).filter_by(username=username).first()
        return result.password if result else None
    finally:
        db_session.close()


def get_user_by_email(email):
    """Get user by email address"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(email=email.lower()).first()
        if user:
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "email_verified": user.email_verified,
                "is_auth": user.is_auth,
                "created_at": user.created_at,
                "password": user.password,
            }
        return None
    finally:
        db_session.close()


def get_user_by_username(username):
    """Get user by username"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(username=username).first()
        if user:
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "email_verified": user.email_verified,
                "is_auth": user.is_auth,
            }
        return None
    finally:
        db_session.close()


def create_user_with_email(email, username, password, verified=False, rullenummer=None):
    """Create user account with email (for self-registration)"""
    db_session = get_db_session()
    try:
        existing_email = db_session.query(DBUser).filter_by(email=email.lower()).first()
        if existing_email:
            return False, "E-postadressen er allerede registrert", None

        existing_username = (
            db_session.query(DBUser).filter_by(username=username).first()
        )
        if existing_username:
            return False, "Brukernavnet er allerede tatt", None

        new_user = DBUser(
            username=username,
            email=email.lower(),
            password=hash_password(password),
            rullenummer=rullenummer,
            is_auth=0,
            email_verified=1 if verified else 0,
            created_at=func.now(),
        )
        db_session.add(new_user)
        db_session.commit()
        db_session.refresh(new_user)
        return True, "Bruker opprettet", new_user.id
    except Exception as e:
        db_session.rollback()
        return False, f"Error creating user: {e}", None
    finally:
        db_session.close()


def get_all_users():
    """Get all users from the database"""
    db_session = get_db_session()
    try:
        users = db_session.query(DBUser).all()
        return [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "rullenummer": user.rullenummer,
                "is_auth": user.is_auth,
                "email_verified": user.email_verified,
                "created_at": user.created_at,
                "seniority_nr": user.seniority_nr,
            }
            for user in users
        ]
    finally:
        db_session.close()


def get_user_by_id(user_id):
    """Get a specific user by ID"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if user:
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "rullenummer": user.rullenummer,
                "is_auth": user.is_auth,
            }
        return None
    finally:
        db_session.close()


def create_user(username, password, is_auth=0):
    """Create a new user (admin-created users are auto-verified)"""
    db_session = get_db_session()
    try:
        existing_user = db_session.query(DBUser).filter_by(username=username).first()
        if existing_user:
            return False, "Brukernavnet finnes allerede"

        new_user = DBUser(
            username=username,
            email=username,
            password=hash_password(password),
            is_auth=is_auth,
            email_verified=1,
            created_at=func.now(),
        )
        db_session.add(new_user)
        db_session.commit()
        return True, "Bruker opprettet"
    except Exception as e:
        db_session.rollback()
        return False, f"Error creating user: {e}"
    finally:
        db_session.close()


def update_user(
    user_id, username, email=None, rullenummer=None, password=None, is_auth=None
):
    """Update an existing user"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        if username != user.username:
            existing_user = (
                db_session.query(DBUser).filter_by(username=username).first()
            )
            if existing_user:
                return False, "Brukernavnet finnes allerede"

        if email and email != user.email:
            existing_email = (
                db_session.query(DBUser).filter_by(email=email.lower()).first()
            )
            if existing_email:
                return False, "E-postadressen finnes allerede"

        user.username = username
        if email is not None:
            user.email = email.lower()
        if rullenummer is not None:
            user.rullenummer = rullenummer
        if password:
            user.password = hash_password(password)
        if is_auth is not None:
            user.is_auth = is_auth

        db_session.commit()
        return True, "Bruker oppdatert"
    except Exception as e:
        db_session.rollback()
        return False, f"Error updating user: {e}"
    finally:
        db_session.close()


def delete_user(user_id):
    """Delete a user and all associated data"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        db_session.query(Favorites).filter_by(user_id=user_id).delete()
        db_session.delete(user)
        db_session.commit()
        return True, "Bruker slettet"
    except Exception as e:
        db_session.rollback()
        return False, f"Error deleting user: {e}"
    finally:
        db_session.close()


def toggle_user_auth(user_id):
    """Toggle user authentication status"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        user.is_auth = 1 if user.is_auth == 0 else 0
        db_session.commit()
        return (
            True,
            f"Administratorrettigheter {'aktivert' if user.is_auth == 1 else 'deaktivert'}",
        )
    except Exception as e:
        db_session.rollback()
        return False, f"Error toggling user auth: {e}"
    finally:
        db_session.close()


def update_user_password(user_id, current_password, new_password):
    """Update user password with current password verification"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        if not bcrypt.checkpw(
            current_password.encode("utf-8"), user.password.encode("utf-8")
        ):
            return False, "Nåværende passord er feil"

        user.password = hash_password(new_password)
        db_session.commit()
        return True, "Passord oppdatert"
    except Exception as e:
        db_session.rollback()
        return False, f"Error updating password: {e}"
    finally:
        db_session.close()


def sync_employees_from_scrape(employees: list) -> dict:
    """Sync a scraped employee list into the database.

    For each record in the PDF:
    - No existing user with that rullenummer → create stub
    - Existing stub (is_stub=1)             → update HR fields if changed
    - Existing registered user (is_stub=0)  → update HR fields if changed
                                              (username/email/password untouched)

    After processing all PDF records, any DB user with a rullenummer that was
    NOT in the PDF has their seniority_nr cleared (set to NULL). This causes
    them to appear in the "not on list" section in the admin UI.

    Returns ``{"added": int, "updated": int, "unchanged": int, "removed_from_list": int}``
    """
    db_session = get_db_session()
    added = updated = unchanged = 0
    try:
        scraped_rullenummers = set()

        for emp in employees:
            rullenummer = str(emp.get("rullenummer", "")).strip()
            if not rullenummer:
                continue

            scraped_rullenummers.add(rullenummer)

            etternavn = (emp.get("etternavn") or "").strip()
            fornavn = (emp.get("fornavn") or "").strip()
            name = f"{etternavn}, {fornavn}"
            stasjoneringssted = emp.get("stasjoneringssted") or None
            ans_dato = emp.get("ans_dato") or None
            fodt_dato = emp.get("fodt_dato") or None
            seniority_nr = emp.get("seniority_nr") or None

            user = db_session.query(DBUser).filter_by(rullenummer=rullenummer).first()

            if user is None:
                stub = DBUser(
                    username=f"__stub_{rullenummer}",
                    password=hash_password(secrets.token_hex(32)),
                    name=name,
                    rullenummer=rullenummer,
                    is_stub=1,
                    email_verified=0,
                    is_auth=0,
                    stasjoneringssted=stasjoneringssted,
                    ans_dato=ans_dato,
                    fodt_dato=fodt_dato,
                    seniority_nr=seniority_nr,
                )
                db_session.add(stub)
                added += 1
            else:
                changed = False
                for attr, val in [
                    ("name", name),
                    ("stasjoneringssted", stasjoneringssted),
                    ("ans_dato", ans_dato),
                    ("fodt_dato", fodt_dato),
                    ("seniority_nr", seniority_nr),
                ]:
                    if getattr(user, attr) != val:
                        setattr(user, attr, val)
                        changed = True
                if changed:
                    updated += 1
                else:
                    unchanged += 1

        # Clear seniority_nr for any employee no longer present in the PDF.
        # Only targets rows that previously had a seniority_nr (i.e. were from a
        # prior PDF import) — avoids touching system/admin users with no rullenummer.
        removed_from_list = 0
        if scraped_rullenummers:
            missing = (
                db_session.query(DBUser)
                .filter(
                    DBUser.rullenummer.isnot(None),
                    DBUser.seniority_nr.isnot(None),
                    DBUser.rullenummer.notin_(scraped_rullenummers),
                )
                .all()
            )
            for user in missing:
                user.seniority_nr = None
                removed_from_list += 1

        db_session.commit()
        logger.info(
            "sync_employees: added=%d updated=%d unchanged=%d removed_from_list=%d",
            added, updated, unchanged, removed_from_list,
        )
        return {
            "added": added,
            "updated": updated,
            "unchanged": unchanged,
            "removed_from_list": removed_from_list,
        }
    except Exception as e:
        db_session.rollback()
        logger.error("Error syncing employees: %s", e)
        raise
    finally:
        db_session.close()


def get_user_by_rullenummer(rullenummer):
    """Get user by rullenummer"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(rullenummer=str(rullenummer)).first()
        if user:
            return {
                "id": user.id,
                "rullenummer": user.rullenummer,
                "name": user.name,
                "stasjoneringssted": user.stasjoneringssted,
                "ans_dato": user.ans_dato,
                "fodt_dato": user.fodt_dato,
                "seniority_nr": user.seniority_nr,
                "is_stub": user.is_stub or 0,
                "email": user.email,
                "username": user.username,
            }
        return None
    finally:
        db_session.close()


def create_stub_user(
    rullenummer,
    etternavn,
    fornavn,
    stasjoneringssted=None,
    ans_dato=None,
    fodt_dato=None,
    seniority_nr=None,
):
    """Create a stub user for an employee who hasn't registered yet.

    Uses a reserved username prefix ``__stub_<rullenummer>`` and a random
    unusable password so the account cannot be logged into directly.
    """
    db_session = get_db_session()
    try:
        existing = db_session.query(DBUser).filter_by(rullenummer=str(rullenummer)).first()
        if existing:
            return False, "Rullenummer finnes allerede"

        stub = DBUser(
            username=f"__stub_{rullenummer}",
            password=hash_password(secrets.token_hex(32)),
            name=f"{etternavn}, {fornavn}",
            rullenummer=str(rullenummer),
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
        logger.info("Stub user created for rullenummer %s", rullenummer)
        return True, "Stub opprettet"
    except Exception as e:
        db_session.rollback()
        logger.error("Error creating stub user: %s", e)
        return False, f"Feil ved oppretting: {e}"
    finally:
        db_session.close()


def activate_stub_user(user_id, username, email, password):
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
        existing_username = db_session.query(DBUser).filter_by(username=username).first()
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
        users = db_session.query(DBUser).order_by(
            func.coalesce(DBUser.seniority_nr, 999999).asc(),
            DBUser.id.asc(),
        ).all()
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
            result.append({
                "id": u.id,
                "rullenummer": u.rullenummer,
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
            })
        return result
    finally:
        db_session.close()


def delete_missing_stubs():
    """Delete all unregistered stub users that are no longer on the current PDF.

    Targets only rows where ``is_stub=1`` AND ``seniority_nr IS NULL``
    AND ``rullenummer IS NOT NULL``.  Registered users missing from the list
    (is_stub=0) are left completely untouched.

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
            )
            .all()
        )
        count = len(targets)
        for user in targets:
            db_session.query(FavModel).filter_by(user_id=user.id).delete()
            db_session.delete(user)
        db_session.commit()
        logger.info("delete_missing_stubs: deleted %d rows", count)
        return True, f"{count} stub-brukere slettet.", count
    except Exception as e:
        db_session.rollback()
        logger.error("Error deleting missing stubs: %s", e)
        return False, f"Feil ved sletting: {e}", 0
    finally:
        db_session.close()


def reset_user_to_stub(user_id):
    """Reset a registered user back to stub state, preserving all their favorites.

    Clears email, replaces password with a random unusable hash, resets
    username to ``__stub_<rullenummer>``, and sets is_stub=1.
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
        if not user.rullenummer:
            return False, "Kan ikke tilbakestille bruker uten rullenummer"

        user.username = f"__stub_{user.rullenummer}"
        user.email = None
        user.password = hash_password(secrets.token_hex(32))
        user.is_stub = 1
        user.email_verified = 0
        user.is_auth = 0

        db_session.commit()
        logger.info("User %s reset to stub (favorites preserved)", user_id)
        return True, "Brukerkonto tilbakestilt til stub. Favoritter er beholdt."
    except Exception as e:
        db_session.rollback()
        logger.error("Error resetting user %s to stub: %s", user_id, e)
        return False, f"Feil ved tilbakestilling: {e}"
    finally:
        db_session.close()


def get_user_detail(user_id):
    """Get full user detail including favorites grouped by turnus set.

    Returns a dict with all user fields plus:
      favorites_by_set  — list of {set_id, set_name, year_identifier, shifts[]}
      total_favorites   — int
      sets_used         — int
      is_registered     — bool
    Returns None if user not found.
    """
    from app.models import TurnusSet, Favorites as FavModel

    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return None

        # Fetch all favorites joined with turnus set in one query
        rows = (
            db_session.query(FavModel, TurnusSet)
            .join(TurnusSet, FavModel.turnus_set_id == TurnusSet.id)
            .filter(FavModel.user_id == user_id)
            .order_by(TurnusSet.id, FavModel.order_index)
            .all()
        )

        sets_dict = {}
        for fav, ts in rows:
            if ts.id not in sets_dict:
                sets_dict[ts.id] = {
                    "set_id": ts.id,
                    "set_name": ts.name,
                    "year_identifier": ts.year_identifier,
                    "shifts": [],
                }
            sets_dict[ts.id]["shifts"].append(fav.shift_title)

        favorites_by_set = list(sets_dict.values())

        if user.name and "," in user.name:
            parts = user.name.split(",", 1)
            etternavn = parts[0].strip()
            fornavn = parts[1].strip()
        else:
            etternavn = user.name or ""
            fornavn = ""

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "rullenummer": user.rullenummer,
            "name": user.name,
            "etternavn": etternavn,
            "fornavn": fornavn,
            "stasjoneringssted": user.stasjoneringssted,
            "ans_dato": user.ans_dato,
            "fodt_dato": user.fodt_dato,
            "seniority_nr": user.seniority_nr,
            "is_stub": user.is_stub or 0,
            "is_auth": user.is_auth or 0,
            "email_verified": user.email_verified or 0,
            "has_seen_tour": user.has_seen_turnusliste_tour or 0,
            "created_at": user.created_at,
            "favorites_by_set": favorites_by_set,
            "total_favorites": sum(len(s["shifts"]) for s in favorites_by_set),
            "sets_used": len(favorites_by_set),
            "is_registered": (user.is_stub or 0) == 0 and user.email is not None,
        }
    finally:
        db_session.close()


def init_default_admin():
    """Creates a default admin user if database is empty"""
    from config import AppConfig

    db_session = get_db_session()
    try:
        if db_session.query(DBUser).count() > 0:
            return

        if not AppConfig.DEFAULT_ADMIN_PASSWORD:
            logger.warning("No DEFAULT_ADMIN_PASSWORD set, skipping admin creation")
            return

        admin = DBUser(
            username=AppConfig.DEFAULT_ADMIN_USERNAME,
            email=AppConfig.DEFAULT_ADMIN_USERNAME,
            password=hash_password(AppConfig.DEFAULT_ADMIN_PASSWORD),
            is_auth=1,
            email_verified=1,
        )
        db_session.add(admin)
        db_session.commit()
        logger.info("Default admin created: %s", AppConfig.DEFAULT_ADMIN_USERNAME)
    except Exception as e:
        db_session.rollback()
        logger.error("Error creating default admin: %s", e)
    finally:
        db_session.close()
