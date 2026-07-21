"""Shared low-level helpers for the user / member-sync / stub service modules.

Extracted from ``user_service.py`` so that ``user_service``,
``member_sync_service`` and ``stub_service`` can all depend on these without
importing one another (which would create a circular import). This module is a
leaf: it imports only bcrypt, SQLAlchemy and the ORM models — never any service
module — so every service can import *down* from it and nothing points back up.
"""

import bcrypt
from sqlalchemy import func

from app.models import DBUser


def hash_password(password):
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed_pw.decode("utf-8")


def _username_filter(username):
    """Case-insensitive username predicate.

    Usernames are case-insensitive identifiers (policy: "Admin" == "admin").
    Comparing with lower() in the query makes lookups and uniqueness checks
    behave identically on SQLite (dev, case-sensitive '=') and MySQL (prod,
    case-insensitive collation), instead of silently relying on DB collation.
    The stored value keeps its original case for display.
    """
    return func.lower(DBUser.username) == (username or "").lower()


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
    replace hyphens with spaces, collapse internal whitespace, casefold."""
    name = name or ""
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{last.strip()}, {first.strip()}"
    return " ".join(name.replace("-", " ").split()).casefold()


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
