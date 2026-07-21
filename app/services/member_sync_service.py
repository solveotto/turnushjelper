"""NLF member-list (medlemsliste) sync, extracted from ``user_service.py``.

Imports shared helpers from :mod:`app.services.user_helpers` (a leaf module)
rather than from ``user_service``, so there is no circular import.
``user_service`` re-exports :func:`sync_members_from_excel` for backward
compatibility with callers that reference it as ``user_service.sync_members_from_excel``.
"""

import logging
import secrets

from app.database import get_db_session
from app.models import DBUser, Favorites
from app.services.user_helpers import (
    _normalize_name,
    hash_password,
    normalize_medlemsnummer,
)

logger = logging.getLogger(__name__)


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
        by_stub_lastname_words = {}  # normalized last-name word → stub list
        by_stub_ans_dato = {}        # ans_dato string → stub list
        for u in users:
            if u.name:
                by_name.setdefault(_normalize_name(u.name), []).append(u)
            if (u.is_stub or 0) == 1 and u.name and "," in u.name:
                for w in _normalize_name(u.name.split(",", 1)[0].strip()).split():
                    by_stub_lastname_words.setdefault(w, []).append(u)
                if u.ans_dato:
                    by_stub_ans_dato.setdefault(u.ans_dato, []).append(u)

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
                # Capture first, delete the twin, THEN write to target.
                # rullenummer is unique (migration 017), so target must not
                # hold the twin's value while the twin's row still exists —
                # delete_stub() flushes, so afterwards the row is gone and the
                # UPDATE below is safe. Assigning before the delete fails:
                # a flush orders same-table UPDATEs by primary key, not by
                # assignment order, so target's UPDATE can land first.
                moved = {
                    attr: getattr(twin, attr)
                    for attr in ("rullenummer", "stasjoneringssted", "ans_dato",
                                 "fodt_dato", "seniority_nr")
                    if getattr(target, attr) in (None, "")
                    and getattr(twin, attr) not in (None, "")
                }
                delete_stub(twin)
                for attr, val in moved.items():
                    setattr(target, attr, val)

        def absorb_fuzzy_twins(target, stub_ans_dato):
            """Absorb stubs that share an ans_dato and at least one last-name
            word with the target — handles compound/hyphenated last names where
            the PDF stub and the NLF stub don't share an exact name."""
            if not stub_ans_dato or not target.name or "," not in target.name:
                return
            target_last_words = set(
                _normalize_name(target.name.split(",", 1)[0].strip()).split()
            )
            for u in by_stub_ans_dato.get(stub_ans_dato, []):
                if u.id == target.id:
                    continue
                if u.id in deleted_user_ids or u.id in claimed_user_ids:
                    continue
                if not u.name or "," not in u.name:
                    continue
                u_last_words = set(
                    _normalize_name(u.name.split(",", 1)[0].strip()).split()
                )
                if target_last_words & u_last_words:
                    # Capture, delete, then write — see absorb_twins().
                    moved = {
                        attr: getattr(u, attr)
                        for attr in ("rullenummer", "stasjoneringssted", "ans_dato",
                                     "fodt_dato", "seniority_nr")
                        if getattr(target, attr) in (None, "")
                        and getattr(u, attr) not in (None, "")
                    }
                    delete_stub(u)
                    for attr, val in moved.items():
                        setattr(target, attr, val)

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
                    absorb_fuzzy_twins(owner, ans_dato)
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
                        absorb_fuzzy_twins(owner, ans_dato)
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
                absorb_fuzzy_twins(target, ans_dato)
                matched += 1
            elif len(stub_twins) == 1:
                stub = stub_twins[0]
                stub.medlemsnummer = mnr
                by_mnr[mnr] = stub
                claimed_user_ids.add(stub.id)
                for attr, val in hr_fields:
                    if val is not None:
                        setattr(stub, attr, val)
                absorb_twins(stub, norm)
                absorb_fuzzy_twins(stub, ans_dato)
                matched += 1
            elif stub_twins:
                for stub in stub_twins:
                    delete_stub(stub)
                create_member_stub(name, mnr, ans_dato=ans_dato,
                                   fodt_dato=fodt_dato,
                                   stasjoneringssted=stasjoneringssted)
            else:
                # Fuzzy fallback B: last-name word overlap + ans_dato match
                # (safer — date is a strong anchor; handles compound last names)
                fuzzy_by_date = []
                if ans_dato and "," in name:
                    nlf_last_words = set(
                        _normalize_name(name.split(",", 1)[0].strip()).split()
                    )
                    for u in by_stub_ans_dato.get(ans_dato, []):
                        if u.id in claimed_user_ids or u.id in deleted_user_ids:
                            continue
                        if not u.name or "," not in u.name:
                            continue
                        db_last_words = set(
                            _normalize_name(u.name.split(",", 1)[0].strip()).split()
                        )
                        if nlf_last_words & db_last_words:
                            fuzzy_by_date.append(u)

                if len(fuzzy_by_date) == 1:
                    stub = fuzzy_by_date[0]
                    stub.name = name
                    stub.medlemsnummer = mnr
                    by_mnr[mnr] = stub
                    claimed_user_ids.add(stub.id)
                    for attr, val in hr_fields:
                        if val is not None:
                            setattr(stub, attr, val)
                    absorb_twins(stub, norm)
                    absorb_fuzzy_twins(stub, ans_dato)
                    matched += 1
                    continue

                # Fuzzy fallback A: exact last name + first-name prefix
                # (no date available; handles PDF stubs missing middle names)
                fuzzy_by_first = []
                if "," in name:
                    nlf_last = _normalize_name(name.split(",", 1)[0].strip())
                    nlf_first = _normalize_name(name.split(",", 1)[1].strip())
                    for w in nlf_last.split():
                        for u in by_stub_lastname_words.get(w, []):
                            if u.id in claimed_user_ids or u.id in deleted_user_ids:
                                continue
                            if not u.name or "," not in u.name:
                                continue
                            db_last = _normalize_name(u.name.split(",", 1)[0].strip())
                            db_first = _normalize_name(u.name.split(",", 1)[1].strip())
                            if db_last == nlf_last:
                                if nlf_first.startswith(db_first) or db_first.startswith(nlf_first):
                                    if u not in fuzzy_by_first:
                                        fuzzy_by_first.append(u)

                if len(fuzzy_by_first) == 1:
                    stub = fuzzy_by_first[0]
                    stub.name = name
                    stub.medlemsnummer = mnr
                    by_mnr[mnr] = stub
                    claimed_user_ids.add(stub.id)
                    for attr, val in hr_fields:
                        if val is not None:
                            setattr(stub, attr, val)
                    absorb_twins(stub, norm)
                    absorb_fuzzy_twins(stub, ans_dato)
                    matched += 1
                    continue

                create_member_stub(name, mnr, ans_dato=ans_dato,
                                   fodt_dato=fodt_dato,
                                   stasjoneringssted=stasjoneringssted)

        # Set/clear the persistent not_on_nlf_list flag using the pre-captured
        # users list. A fresh query would incorrectly flag newly created stubs
        # (they are not in claimed_user_ids but are legitimately new).
        flagged = unflagged = 0
        for u in users:
            if u.id in deleted_user_ids:
                continue
            if u.id in claimed_user_ids:
                if u.not_on_nlf_list:
                    u.not_on_nlf_list = 0   # re-appeared on list — clear flag
                    unflagged += 1
            elif u.name and (u.medlemsnummer or u.rullenummer):
                if not u.not_on_nlf_list:
                    u.not_on_nlf_list = 1
                    flagged += 1

        db_session.commit()
        logger.info(
            "sync_members: matched=%d created=%d updated=%d unchanged=%d "
            "invalid=%d deleted_stubs=%d conflicts=%d flagged=%d unflagged=%d",
            matched, created, updated, unchanged, skipped_invalid,
            deleted_stubs, len(conflicts), flagged, unflagged,
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
            "flagged": flagged,
            "unflagged": unflagged,
        }
    except Exception as e:
        db_session.rollback()
        logger.error("Error syncing members from Excel: %s", e)
        raise
    finally:
        db_session.close()
