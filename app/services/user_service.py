import logging
import random
import secrets
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy import func

from app.database import get_db_session
from app.models import DBUser, Favorites, Shifts, TurnusSet

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
        result = (
            db_session.query(DBUser)
            .filter(DBUser.username.ilike(username_or_email))
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


def admin_create_user(
    username=None,
    password=None,
    email=None,
    is_auth=0,
    name=None,
    rullenummer=None,
    medlemsnummer=None,
    stasjoneringssted=None,
    ans_dato=None,
    fodt_dato=None,
    seniority_nr=None,
    is_stub=0,
):
    """Create a user with the full attribute set from the admin UI.

    ``is_stub=1``: a member stub — requires name + NLF-medlemsnummer;
    username/password are generated (reserved prefix + unusable hash).
    ``is_stub=0``: a real account — requires username + password;
    medlemsnummer optional (admin/system accounts have none).
    """
    db_session = get_db_session()
    try:
        medlemsnummer = normalize_medlemsnummer(medlemsnummer) or None
        rullenummer = str(rullenummer).strip() if rullenummer else None
        name = (name or "").strip() or None

        if is_stub:
            if not name:
                return False, "Navn er påkrevd for en stub-bruker"
            if not medlemsnummer:
                return False, "NLF-medlemsnummer er påkrevd for en stub-bruker"
            username = f"__stub_m{medlemsnummer}"
            password_hash = hash_password(secrets.token_hex(32))
            email = None
            email_verified = 0
        else:
            if not username or not password:
                return False, "Brukernavn og passord er påkrevd"
            password_hash = hash_password(password)
            email_verified = 1

        if db_session.query(DBUser).filter_by(username=username).first():
            return False, "Brukernavnet finnes allerede"
        if email and db_session.query(DBUser).filter_by(email=email.lower()).first():
            return False, "E-postadressen finnes allerede"
        if medlemsnummer and (
            db_session.query(DBUser).filter_by(medlemsnummer=medlemsnummer).first()
        ):
            return False, "NLF-medlemsnummeret finnes allerede"
        if rullenummer and (
            db_session.query(DBUser).filter_by(rullenummer=rullenummer).first()
        ):
            return False, "Rullenummeret finnes allerede"

        new_user = DBUser(
            username=username,
            password=password_hash,
            email=email.lower() if email else None,
            is_auth=is_auth,
            name=name,
            rullenummer=rullenummer,
            medlemsnummer=medlemsnummer,
            stasjoneringssted=stasjoneringssted or None,
            ans_dato=ans_dato or None,
            fodt_dato=fodt_dato or None,
            seniority_nr=seniority_nr,
            is_stub=1 if is_stub else 0,
            email_verified=email_verified,
            created_at=func.now(),
        )
        db_session.add(new_user)
        db_session.commit()
        return True, "Stub opprettet" if is_stub else "Bruker opprettet"
    except Exception as e:
        db_session.rollback()
        logger.error("Error creating user: %s", e)
        return False, f"Feil ved oppretting: {e}"
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
        by_date = {}
        for u in db_session.query(DBUser).filter(DBUser.rullenummer.is_(None)).all():
            if u.name:
                by_name.setdefault(_normalize_name(u.name), []).append(u)
                if u.ans_dato and "," in u.name:
                    last_norm = _normalize_name(u.name.split(",")[0].strip())
                    by_lastname.setdefault(last_norm, []).append(u)
            if u.ans_dato:
                by_date.setdefault(u.ans_dato, []).append(u)
        merged_ids = set()
        # Track rullenummers processed in this run to guard against duplicate
        # rows in the PDF when autoflush=False would hide in-flight INSERTs.
        processed_this_run = set()

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
            "sync_employees: updated=%d unchanged=%d merged_by_name=%d "
            "merged_by_date=%d removed_from_list=%d skipped_unmatched=%d",
            updated,
            unchanged,
            merged_by_name,
            merged_by_date,
            removed_from_list,
            skipped_unmatched,
        )
        return {
            "updated": updated,
            "unchanged": unchanged,
            "merged_by_name": merged_by_name,
            "merged_by_date": merged_by_date,
            "removed_from_list": removed_from_list,
            "skipped_unmatched": skipped_unmatched,
        }
    except Exception as e:
        db_session.rollback()
        logger.error("Error syncing employees: %s", e)
        raise
    finally:
        db_session.close()


def normalize_medlemsnummer(value):
    """Canonical form of an NLF-medlemsnummer: trimmed, and leading zeros
    stripped for all-digit values so '068588' (as stored in the member list
    export) and '68588' (as typed by the member) refer to the same number."""
    value = str(value or "").strip()
    if value.isdigit():
        value = str(int(value))
    return value


def _normalize_name(name):
    """Normalize an "Etternavn, Fornavn" name for matching: trim each part,
    collapse internal whitespace, casefold."""
    name = name or ""
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{last.strip()}, {first.strip()}"
    return " ".join(name.split()).casefold()


def sync_members_from_excel(members: list) -> dict:
    """Sync the NLF member list (name + medlemsnummer) into the database.

    Registered users (is_stub=0) are matched by exact normalized name and get
    their medlemsnummer set — they are never deleted, and a differing existing
    medlemsnummer is reported as a conflict, never overwritten.

    Unregistered stubs (is_stub=1) are disposable during matching: name
    mismatches and duplicates are resolved by deleting the conflicting
    stub(s) and creating a fresh one from the Excel row. Same-name duplicate
    stubs (e.g. from a PDF sync that ran before the member list was
    imported) have their rullenummer/HR data absorbed into the kept user
    before deletion.

    Anyone — stub or registered — not claimed by a row in this run is never
    auto-deleted; they are surfaced in ``not_on_list`` for manual review,
    since a stub may just be a name-matching miss and a registered user may
    have simply not been re-added yet.

    Returns ``{"total_rows", "matched", "created", "unchanged",
    "skipped_invalid", "deleted_stubs", "conflicts", "not_on_list"}``.
    """
    db_session = get_db_session()
    matched = created = unchanged = updated = skipped_invalid = deleted_stubs = 0
    conflicts = []
    updated_users = []
    try:
        users = db_session.query(DBUser).all()
        by_mnr = {u.medlemsnummer: u for u in users if u.medlemsnummer}
        by_name = {}
        for u in users:
            if u.name:
                by_name.setdefault(_normalize_name(u.name), []).append(u)

        seen_mnr = set()
        claimed_user_ids = set()
        deleted_user_ids = set()

        def delete_stub(stub):
            nonlocal deleted_stubs
            db_session.query(Favorites).filter_by(user_id=stub.id).delete()
            db_session.delete(stub)
            deleted_user_ids.add(stub.id)
            if stub.medlemsnummer:
                by_mnr.pop(stub.medlemsnummer, None)
            deleted_stubs += 1
            # Flush now: SQLAlchemy orders INSERTs before DELETEs within a
            # flush, which would violate the unique medlemsnummer index when
            # a replacement stub reuses the deleted stub's number.
            db_session.flush()

        def create_member_stub(name, mnr, ans_dato=None, fodt_dato=None,
                               stasjoneringssted=None):
            nonlocal created
            stub = DBUser(
                username=f"__stub_m{mnr}",
                password=hash_password(secrets.token_hex(32)),
                name=name,
                medlemsnummer=mnr,
                is_stub=1,
                email_verified=0,
                is_auth=0,
                ans_dato=ans_dato,
                fodt_dato=fodt_dato,
                stasjoneringssted=stasjoneringssted,
            )
            db_session.add(stub)
            by_mnr[mnr] = stub
            created += 1

        def absorb_twins(target, norm):
            """Merge HR data (rullenummer, station, dates, seniority) from
            same-name duplicate stubs — typically created by a PDF sync that
            ran before the member list was imported — into the kept user,
            then delete the duplicates."""
            twins = [
                u for u in by_name.get(norm, [])
                if u.id != target.id
                and (u.is_stub or 0) == 1
                and u.id not in deleted_user_ids
                and u.id not in claimed_user_ids
            ]
            for twin in twins:
                for attr in ("rullenummer", "stasjoneringssted", "ans_dato",
                             "fodt_dato", "seniority_nr"):
                    if getattr(target, attr) in (None, "") and getattr(
                        twin, attr
                    ) not in (None, ""):
                        setattr(target, attr, getattr(twin, attr))
                delete_stub(twin)

        for member in members:
            name = (member.get("name") or "").strip()
            mnr = str(member.get("medlemsnummer") or "").strip()
            if not name or not mnr.isdigit():
                skipped_invalid += 1
                continue
            mnr = normalize_medlemsnummer(mnr)

            if mnr in seen_mnr:
                conflicts.append(
                    {"name": name, "medlemsnummer": mnr,
                     "reason": "Duplikat medlemsnummer i Excel-fila"}
                )
                continue
            seen_mnr.add(mnr)
            norm = _normalize_name(name)

            # HR fields from the enriched NLF export (None when absent)
            ans_dato = member.get("ans_dato")
            fodt_dato = member.get("fodt_dato")
            stasjoneringssted = member.get("stasjoneringssted")
            hr_fields = [("ans_dato", ans_dato), ("fodt_dato", fodt_dato),
                         ("stasjoneringssted", stasjoneringssted)]

            owner = by_mnr.get(mnr)
            if owner is not None:
                if _normalize_name(owner.name) == norm:
                    claimed_user_ids.add(owner.id)
                    fields_changed = []
                    # NLF list is authoritative for stubs; non-destructive for
                    # registered users (don't overwrite manually-set values).
                    if (owner.is_stub or 0) == 1:
                        for attr, val in hr_fields:
                            if val is not None and getattr(owner, attr) != val:
                                setattr(owner, attr, val)
                                fields_changed.append(attr)
                    else:
                        for attr, val in hr_fields:
                            if val is not None and not getattr(owner, attr):
                                setattr(owner, attr, val)
                                fields_changed.append(attr)
                    absorb_twins(owner, norm)
                    if fields_changed:
                        updated += 1
                        updated_users.append({
                            "name": owner.name,
                            "is_stub": owner.is_stub or 0,
                            "fields": fields_changed,
                        })
                    else:
                        unchanged += 1
                    continue
                if (owner.is_stub or 0) == 0:
                    # Check if it's the same person with a name variation
                    # (e.g. middle name added in NLF). Compare last names only.
                    owner_last = _normalize_name(
                        (owner.name or "").split(",")[0].strip()
                    )
                    nlf_last = _normalize_name(name.split(",")[0].strip())
                    if owner_last and owner_last == nlf_last:
                        # Same person — update name to NLF version and claim.
                        old_name = owner.name
                        owner.name = name
                        claimed_user_ids.add(owner.id)
                        fields_changed = ["name"] if old_name != name else []
                        for attr, val in hr_fields:
                            if val is not None and not getattr(owner, attr):
                                setattr(owner, attr, val)
                                fields_changed.append(attr)
                        absorb_twins(owner, norm)
                        matched += 1
                        if fields_changed:
                            updated_users.append({
                                "name": name,
                                "is_stub": owner.is_stub or 0,
                                "fields": fields_changed,
                            })
                    else:
                        conflicts.append(
                            {"name": name, "medlemsnummer": mnr,
                             "reason": f"Medlemsnummeret tilhører registrert bruker "
                                       f"'{owner.name or owner.username}' (id {owner.id})"}
                        )
                    continue
                # A stub holds the number under a different name — replace it.
                delete_stub(owner)

            candidates = [
                u for u in by_name.get(norm, [])
                if u.id not in claimed_user_ids and u.id not in deleted_user_ids
            ]
            registered = [u for u in candidates if (u.is_stub or 0) == 0]
            stub_twins = [u for u in candidates if (u.is_stub or 0) == 1]

            if registered:
                target = registered[0]
                if len(registered) > 1:
                    conflicts.append(
                        {"name": name, "medlemsnummer": mnr,
                         "reason": "Flere registrerte brukere med samme navn: "
                                   + ", ".join(str(u.id) for u in registered)}
                    )
                    continue
                if target.medlemsnummer and target.medlemsnummer != mnr:
                    conflicts.append(
                        {"name": name, "medlemsnummer": mnr,
                         "reason": f"Registrert bruker (id {target.id}) har allerede "
                                   f"medlemsnummer {target.medlemsnummer}"}
                    )
                    continue
                target.medlemsnummer = mnr
                by_mnr[mnr] = target
                claimed_user_ids.add(target.id)
                for attr, val in hr_fields:
                    if val is not None and not getattr(target, attr):
                        setattr(target, attr, val)
                absorb_twins(target, norm)
                matched += 1
            elif len(stub_twins) == 1:
                stub = stub_twins[0]
                stub.medlemsnummer = mnr
                by_mnr[mnr] = stub
                claimed_user_ids.add(stub.id)
                for attr, val in hr_fields:
                    if val is not None:
                        setattr(stub, attr, val)
                matched += 1
            elif stub_twins:
                for stub in stub_twins:
                    delete_stub(stub)
                create_member_stub(name, mnr, ans_dato=ans_dato,
                                   fodt_dato=fodt_dato,
                                   stasjoneringssted=stasjoneringssted)
            else:
                create_member_stub(name, mnr, ans_dato=ans_dato,
                                   fodt_dato=fodt_dato,
                                   stasjoneringssted=stasjoneringssted)

        # Anyone (stub or registered) not claimed by a row in this run is not
        # on the current member list. Never auto-delete — surface for manual
        # review instead.
        not_on_list = [
            {
                "id": u.id,
                "name": u.name,
                "username": u.username,
                "medlemsnummer": u.medlemsnummer,
                "is_stub": u.is_stub or 0,
            }
            for u in users
            if u.id not in deleted_user_ids
            and u.id not in claimed_user_ids
            and u.name
        ][:200]

        db_session.commit()
        logger.info(
            "sync_members: matched=%d created=%d updated=%d unchanged=%d "
            "invalid=%d deleted_stubs=%d conflicts=%d",
            matched, created, updated, unchanged, skipped_invalid,
            deleted_stubs, len(conflicts),
        )
        return {
            "total_rows": len(members),
            "matched": matched,
            "created": created,
            "updated": updated,
            "updated_users": updated_users,
            "unchanged": unchanged,
            "skipped_invalid": skipped_invalid,
            "deleted_stubs": deleted_stubs,
            "conflicts": conflicts,
            "not_on_list": not_on_list,
        }
    except Exception as e:
        db_session.rollback()
        logger.error("Error syncing members from Excel: %s", e)
        raise
    finally:
        db_session.close()


def _user_identity_dict(user):
    """Shared dict shape for identity lookups (rullenummer/medlemsnummer)."""
    return {
        "id": user.id,
        "rullenummer": user.rullenummer,
        "medlemsnummer": user.medlemsnummer,
        "name": user.name,
        "stasjoneringssted": user.stasjoneringssted,
        "ans_dato": user.ans_dato,
        "fodt_dato": user.fodt_dato,
        "seniority_nr": user.seniority_nr,
        "is_stub": user.is_stub or 0,
        "email": user.email,
        "username": user.username,
    }


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
            db_session.query(DBUser).filter_by(username=username).first()
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
            user.rullenummer = rullenummer
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
            db_session.query(DBUser)
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
        for user in targets:
            db_session.query(FavModel).filter_by(user_id=user.id).delete()
            db_session.delete(user)
        db_session.commit()
        logger.info("delete_stub_users: deleted %d of %d requested ids", count, len(user_ids))
        return True, f"{count} stub-brukere slettet.", count
    except Exception as e:
        db_session.rollback()
        logger.error("Error bulk-deleting stub users: %s", e)
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


def init_default_admin():
    """Creates a default admin user if no admin user exists yet"""
    from config import AppConfig

    db_session = get_db_session()
    try:
        target_username = AppConfig.DEFAULT_ADMIN_USERNAME
        if db_session.query(DBUser).filter_by(username=target_username).first():
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
