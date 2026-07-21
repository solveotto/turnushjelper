import logging
import random
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy import func

from app.database import get_db_session
from app.models import (
    DBUser,
    EmailVerificationToken,
    Favorites,
    Innplassering,
    Shifts,
    SoknadsskjemaChoice,
    TurnusSet,
    UserActivity,
)
from app.services.user_helpers import (
    _normalize_name,
    _username_filter,
    hash_password,
    normalize_medlemsnummer,
)

logger = logging.getLogger(__name__)


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
        result = (
            db_session.query(DBUser)
            .filter(_username_filter(username_or_email))
            .first()
        )

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
                "seniority_nr": result.seniority_nr,
                "ansatt_data": result.ans_dato,
                "has_seen_turnusliste_tour": result.has_seen_turnusliste_tour or 0,
                "has_seen_favorites_tour": result.has_seen_favorites_tour or 0,
                "has_seen_mintur_tour": result.has_seen_mintur_tour or 0,
                "has_seen_compare_tour": result.has_seen_compare_tour or 0,
                "has_seen_welcome": result.has_seen_welcome or 0,
                "has_seen_soknadsskjema_tour": result.has_seen_soknadsskjema_tour or 0,
                "not_on_nlf_list": result.not_on_nlf_list or 0,
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
        result = db_session.query(DBUser.password).filter(_username_filter(username)).first()
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
    """Get user by username (case-insensitive)"""
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter(_username_filter(username)).first()
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
            db_session.query(DBUser).filter(_username_filter(username)).first()
        )
        if existing_username:
            return False, "Brukernavnet er allerede tatt", None

        if rullenummer:
            existing_rnr = (
                db_session.query(DBUser)
                .filter_by(rullenummer=str(rullenummer))
                .first()
            )
            if existing_rnr:
                return False, "Rullenummeret er allerede i bruk av en annen bruker", None

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
                "medlemsnummer": user.medlemsnummer,
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
                "medlemsnummer": user.medlemsnummer,
                "name": user.name,
                "is_auth": user.is_auth,
                "email_verified": user.email_verified or 0,
                "is_stub": user.is_stub or 0,
                "stasjoneringssted": user.stasjoneringssted,
                "ans_dato": user.ans_dato,
                "fodt_dato": user.fodt_dato,
                "seniority_nr": user.seniority_nr,
            }
        return None
    finally:
        db_session.close()


def create_user(username, password, is_auth=0):
    """Create a new user (admin-created users are auto-verified)"""
    db_session = get_db_session()
    try:
        existing_user = db_session.query(DBUser).filter(_username_filter(username)).first()
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




# Sentinel for update_user: distinguishes "not provided" from an explicit
# None (which clears the column).
_UNSET = object()


def update_user(
    user_id,
    username,
    email=None,
    rullenummer=_UNSET,
    password=None,
    is_auth=_UNSET,
    name=_UNSET,
    medlemsnummer=_UNSET,
    email_verified=_UNSET,
    stasjoneringssted=_UNSET,
    ans_dato=_UNSET,
    fodt_dato=_UNSET,
    seniority_nr=_UNSET,
    is_stub=_UNSET,
):
    """Update an existing user.

    Fields left as ``_UNSET`` are untouched; passing ``None`` explicitly
    clears the column. ``email=None`` and ``password=None``/falsy keep their
    legacy meaning of "leave unchanged".
    """
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        if (username or "").lower() != (user.username or "").lower():
            existing_user = (
                db_session.query(DBUser)
                .filter(_username_filter(username), DBUser.id != user_id)
                .first()
            )
            if existing_user:
                return False, "Brukernavnet finnes allerede"

        if email and email != user.email:
            existing_email = (
                db_session.query(DBUser).filter_by(email=email.lower()).first()
            )
            if existing_email:
                return False, "E-postadressen finnes allerede"

        if medlemsnummer is not _UNSET and medlemsnummer is not None:
            medlemsnummer = normalize_medlemsnummer(medlemsnummer) or None
        if (
            medlemsnummer is not _UNSET
            and medlemsnummer is not None
            and medlemsnummer != (user.medlemsnummer or "")
        ):
            taken = (
                db_session.query(DBUser)
                .filter(
                    DBUser.medlemsnummer == medlemsnummer,
                    DBUser.id != user_id,
                )
                .first()
            )
            if taken:
                return False, "NLF-medlemsnummeret er allerede i bruk av en annen bruker"

        if (
            rullenummer is not _UNSET
            and rullenummer is not None
            and str(rullenummer) != (user.rullenummer or "")
        ):
            taken = (
                db_session.query(DBUser)
                .filter(
                    DBUser.rullenummer == str(rullenummer),
                    DBUser.id != user_id,
                )
                .first()
            )
            if taken:
                return False, "Rullenummeret er allerede i bruk av en annen bruker"

        user.username = username
        if email is not None:
            user.email = email.lower()
        if password:
            user.password = hash_password(password)
        for attr, val in [
            ("rullenummer", rullenummer),
            ("is_auth", is_auth),
            ("name", name),
            ("medlemsnummer", medlemsnummer),
            ("email_verified", email_verified),
            ("stasjoneringssted", stasjoneringssted),
            ("ans_dato", ans_dato),
            ("fodt_dato", fodt_dato),
            ("seniority_nr", seniority_nr),
            ("is_stub", is_stub),
        ]:
            if val is not _UNSET:
                setattr(user, attr, val)

        db_session.commit()
        return True, "Bruker oppdatert"
    except Exception as e:
        db_session.rollback()
        return False, f"Error updating user: {e}"
    finally:
        db_session.close()


def delete_user(user_id):
    """Delete a user and all associated personal data (GDPR right to erasure).

    Deletes everything explicitly rather than relying on DB-level FK cascades,
    since cascade behavior differs between SQLite (dev) and MySQL (prod) and
    some related data is not FK-linked to the user at all.
    """
    db_session = get_db_session()
    try:
        user = db_session.query(DBUser).filter_by(id=user_id).first()
        if not user:
            return False, "Bruker ikke funnet"

        rullenummer = user.rullenummer

        db_session.query(Favorites).filter_by(user_id=user_id).delete()
        db_session.query(SoknadsskjemaChoice).filter_by(user_id=user_id).delete()
        db_session.query(EmailVerificationToken).filter_by(user_id=user_id).delete()
        # UserActivity has ondelete='SET NULL', so delete these before the user
        # row, otherwise the rows are orphaned with user_id=NULL instead of removed.
        db_session.query(UserActivity).filter_by(user_id=user_id).delete()
        # Innplassering is linked by rullenummer string, not a user FK — explicit
        # deletion by rullenummer is the only way to remove it.
        if rullenummer:
            db_session.query(Innplassering).filter_by(rullenummer=rullenummer).delete()
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

    This sync only enriches users that already exist because they're on the
    NLF member list — it never creates new users. For each record in the PDF:
    - Existing user with that rullenummer   → update HR fields if changed
    - No rullenummer match, but exactly one user with the same name and no
      rullenummer (e.g. created by the NLF member list import) → merge the
      rullenummer + HR data into that user
    - Otherwise (no matching user at all) → skipped, no DB write

    After processing all PDF records, any DB user with a rullenummer that was
    NOT in the PDF has their seniority_nr cleared (set to NULL). This causes
    them to appear in the "not on list" section in the admin UI.

    Returns ``{"updated": int, "unchanged": int, "merged_by_name": int,
    "removed_from_list": int, "skipped_unmatched": int}``
    """
    db_session = get_db_session()
    skipped_unmatched = updated = unchanged = merged_by_name = merged_by_date = 0
    try:
        scraped_rullenummers = set()

        # Users without a rullenummer, keyed by normalized name, by
        # (normalized_lastname, ans_dato, fodt_dato), and by ans_dato alone —
        # so PDF rows can be merged into member-list users instead of duplicated.
        by_name = {}
        by_lastname = {}
        by_first_last = {}
        by_word_set = {}
        by_date = {}
        for u in db_session.query(DBUser).filter(DBUser.rullenummer.is_(None)).all():
            if u.name:
                by_name.setdefault(_normalize_name(u.name), []).append(u)
                if "," in u.name:
                    last_part, first_part = u.name.split(",", 1)
                    last_norm = _normalize_name(last_part.strip())
                    if u.ans_dato:
                        by_lastname.setdefault(last_norm, []).append(u)
                    for word in _normalize_name(first_part).split():
                        by_first_last.setdefault((last_norm, word), []).append(u)
                words = frozenset(_normalize_name(u.name).replace(",", " ").split())
                if words:
                    by_word_set.setdefault(words, []).append(u)
            if u.ans_dato:
                by_date.setdefault(u.ans_dato, []).append(u)
        merged_ids = set()
        # Track rullenummers processed in this run to guard against duplicate
        # rows in the PDF when autoflush=False would hide in-flight INSERTs.
        processed_this_run = set()

        rullenummer_to_nr = {
            str(emp.get("rullenummer", "")).strip(): emp.get("seniority_nr")
            for emp in employees
            if str(emp.get("rullenummer", "")).strip()
        }

        for emp in employees:
            rullenummer = str(emp.get("rullenummer", "")).strip()
            if not rullenummer:
                continue
            if rullenummer in processed_this_run:
                logger.warning(
                    "sync_employees: duplicate rullenummer %s in scraped data, skipping",
                    rullenummer,
                )
                continue
            processed_this_run.add(rullenummer)

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
                candidates = [
                    u for u in by_name.get(_normalize_name(name), [])
                    if u.id not in merged_ids
                ]
                if len(candidates) == 1:
                    user = candidates[0]
                    user.rullenummer = rullenummer
                    merged_ids.add(user.id)
                    merged_by_name += 1

            if user is None:
                pdf_words = frozenset(
                    _normalize_name(f"{etternavn} {fornavn}").split()
                )
                ws_candidates = [u for u in by_word_set.get(pdf_words, []) if u.id not in merged_ids]
                if len(ws_candidates) == 1:
                    user = ws_candidates[0]
                    user.rullenummer = rullenummer
                    merged_ids.add(user.id)
                    merged_by_name += 1

            if user is None and etternavn and fornavn:
                last_norm = _normalize_name(etternavn)
                fl_seen = {}
                for word in _normalize_name(fornavn).split():
                    for u in by_first_last.get((last_norm, word), []):
                        if u.id not in merged_ids:
                            fl_seen[u.id] = u
                if len(fl_seen) == 1:
                    user = next(iter(fl_seen.values()))
                    user.rullenummer = rullenummer
                    merged_ids.add(user.id)
                    merged_by_name += 1

            if user is None and etternavn and ans_dato:
                last_norm = _normalize_name(etternavn)
                try:
                    pdf_date = datetime.strptime(ans_dato, "%d.%m.%Y")
                    lastname_date_candidates = []
                    for u in by_lastname.get(last_norm, []):
                        if u.id in merged_ids:
                            continue
                        try:
                            stub_date = datetime.strptime(u.ans_dato, "%d.%m.%Y")
                            if abs((pdf_date - stub_date).days) <= 7:
                                lastname_date_candidates.append(u)
                        except ValueError:
                            pass
                    if len(lastname_date_candidates) == 1:
                        user = lastname_date_candidates[0]
                        user.rullenummer = rullenummer
                        merged_ids.add(user.id)
                        merged_by_date += 1
                except ValueError:
                    pass

            if user is None and ans_dato:
                date_candidates = [
                    u for u in by_date.get(ans_dato, [])
                    if u.id not in merged_ids
                ]
                if len(date_candidates) == 1:
                    user = date_candidates[0]
                    user.rullenummer = rullenummer
                    merged_ids.add(user.id)
                    merged_by_date += 1

            if user is None:
                username = f"__stub_{rullenummer}"
                # Fallback: a user may already hold this username but have had
                # their rullenummer cleared (e.g. absorbed by a member-list
                # import and later re-processed). Reclaim instead of skipping.
                user = db_session.query(DBUser).filter_by(username=username).first()
                if user is not None:
                    user.rullenummer = rullenummer
                    # fall through to update block
                else:
                    # Not on the NLF member list — this sync only enriches
                    # existing members with rullenummer/HR data, it never
                    # creates new users.
                    skipped_unmatched += 1
                    logger.warning(
                        "sync_employees: skipped rullenummer=%s name=%r pdf_ans_dato=%r",
                        rullenummer, name, ans_dato,
                    )
                    continue

            if user is not None:
                changed = False
                for attr, val in [
                    ("seniority_nr", seniority_nr),
                ]:
                    if getattr(user, attr) != val:
                        setattr(user, attr, val)
                        changed = True
                if changed:
                    updated += 1
                else:
                    unchanged += 1

        # Second pass: users with a manually-set rullenummer but no seniority_nr.
        # Covers registered users who entered their rullenummer after the last scan,
        # or cases where a stub with the same rullenummer was matched first above.
        nr_from_rullenummer = 0
        if rullenummer_to_nr:
            unlinked = (
                db_session.query(DBUser)
                .filter(DBUser.rullenummer.isnot(None), DBUser.seniority_nr.is_(None))
                .all()
            )
            for user in unlinked:
                if user.rullenummer in rullenummer_to_nr:
                    user.seniority_nr = rullenummer_to_nr[user.rullenummer]
                    nr_from_rullenummer += 1

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
            "sync_employees: updated=%d unchanged=%d merged_by_name=%d "
            "merged_by_date=%d removed_from_list=%d skipped_unmatched=%d nr_from_rullenummer=%d",
            updated,
            unchanged,
            merged_by_name,
            merged_by_date,
            removed_from_list,
            skipped_unmatched,
            nr_from_rullenummer,
        )
        return {
            "updated": updated,
            "unchanged": unchanged,
            "merged_by_name": merged_by_name,
            "merged_by_date": merged_by_date,
            "removed_from_list": removed_from_list,
            "skipped_unmatched": skipped_unmatched,
            "nr_from_rullenummer": nr_from_rullenummer,
        }
    except Exception as e:
        db_session.rollback()
        logger.error("Error syncing employees: %s", e)
        raise
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
    from app.models import Favorites as FavModel
    from app.models import TurnusSet

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
            "medlemsnummer": user.medlemsnummer,
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


# Passwords too trivial to ever provision an admin with. Guards against a
# stale .env carrying the old insecure DEFAULT_ADMIN_PASSWORD=admin default.
_WEAK_ADMIN_PASSWORDS = frozenset(
    {"admin", "password", "passord", "changeme", "admin123", "test", "1234", "12345678"}
)


def init_default_admin():
    """Creates a default admin user if no admin user exists yet.

    SECURITY: auto-provisioning is skipped unless DEFAULT_ADMIN_PASSWORD is set
    to a non-trivial value. There is no built-in default password, so a fresh
    deployment never ships with a guessable admin/admin account — the operator
    must explicitly supply a strong password to bootstrap the first admin.
    """
    from config import AppConfig

    db_session = get_db_session()
    try:
        target_username = AppConfig.DEFAULT_ADMIN_USERNAME
        if db_session.query(DBUser).filter(_username_filter(target_username)).first():
            return

        password = AppConfig.DEFAULT_ADMIN_PASSWORD or ""
        if not password:
            logger.warning(
                "DEFAULT_ADMIN_PASSWORD not set — skipping admin bootstrap. "
                "Set a strong DEFAULT_ADMIN_PASSWORD in the environment to "
                "create the initial admin user."
            )
            return

        if password.strip().lower() in _WEAK_ADMIN_PASSWORDS or password == target_username:
            logger.warning(
                "DEFAULT_ADMIN_PASSWORD is trivially weak — refusing to bootstrap "
                "admin '%s'. Choose a strong, unique password.",
                target_username,
            )
            return

        admin = DBUser(
            username=target_username,
            email=target_username,
            password=hash_password(password),
            is_auth=1,
            email_verified=1,
        )
        db_session.add(admin)
        db_session.commit()
        logger.info("Default admin created: %s", AppConfig.DEFAULT_ADMIN_USERNAME)
    except Exception as e:
        db_session.rollback()
        from sqlalchemy.exc import OperationalError

        if isinstance(e, OperationalError) and "no such table" in str(e):
            logger.warning(
                "Schema not ready yet — run 'alembic upgrade head' before starting the server"
            )
        else:
            logger.error("Error creating default admin: %s", e)
    finally:
        db_session.close()


def create_test_user_with_favorites():
    """Dev tool: create/reset testbruker with 5 random favorites per TurnusSet."""
    db_session = get_db_session()
    try:
        existing = db_session.query(DBUser).filter_by(username="testbruker").first()
        if existing:
            db_session.query(Favorites).filter_by(user_id=existing.id).delete()
            db_session.delete(existing)
            db_session.flush()

        new_user = DBUser(
            username="testbruker",
            email="testbruker@test.no",
            password=hash_password("test123"),
            is_auth=0,
            email_verified=1,
        )
        db_session.add(new_user)
        db_session.flush()
        user_id = new_user.id

        turnus_sets = db_session.query(TurnusSet).all()
        summary_parts = []
        for ts in turnus_sets:
            shifts = db_session.query(Shifts).filter_by(turnus_set_id=ts.id).all()
            sample = random.sample(shifts, min(5, len(shifts)))
            for i, shift in enumerate(sample):
                db_session.add(Favorites(
                    user_id=user_id,
                    shift_title=shift.title,
                    turnus_set_id=ts.id,
                    order_index=i,
                ))
            if sample:
                summary_parts.append(f"{len(sample)} i {ts.year_identifier}")

        db_session.commit()

        if summary_parts:
            msg = "Testbruker opprettet med " + ", ".join(summary_parts) + "."
        else:
            msg = "Testbruker opprettet (ingen turnussett med skift funnet)."
        return True, msg
    except Exception as e:
        db_session.rollback()
        logger.error("Error creating test user: %s", e)
        return False, f"Feil ved opprettelse av testbruker: {e}"
    finally:
        db_session.close()


# ---------------------------------------------------------------------------
# Backward-compatibility re-exports
# ---------------------------------------------------------------------------
# The member-sync and stub-lifecycle functions were extracted into dedicated
# modules (Phase 3 refactor). They are re-exported here so existing callers
# that reference them as ``user_service.<name>`` — and the ``app.utils.db_utils``
# facade — keep working unchanged. Placed at the bottom (after all core defs);
# the extracted modules import only from ``user_helpers`` (a leaf), never from
# ``user_service``, so this creates no import cycle regardless of load order.
from app.services.member_sync_service import sync_members_from_excel  # noqa: E402,F401
from app.services.stub_service import (  # noqa: E402,F401
    activate_stub_user,
    create_stub_user,
    delete_all_stubs,
    delete_missing_stubs,
    delete_stub_users,
    get_all_stub_users,
    get_user_by_medlemsnummer,
    get_user_by_rullenummer,
    reset_user_to_stub,
)
