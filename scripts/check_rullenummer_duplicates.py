#!/usr/bin/env python3
"""Audit users.rullenummer for duplicates before adding a unique index.

Innplassering rows are joined to users on the rullenummer *string*
(`innplassering_service.py`), so two users sharing a rullenummer means one
sees the other's innplassering data. App-level collision checks exist in
`activate_stub_user`, `create_user_with_email` and `update_user`, but any
future write path that forgets the check reintroduces the exposure — hence
the plan to enforce it in the database.

A unique index cannot be added while duplicates exist, so this script is the
gate: run it against PRODUCTION and only migrate if it exits 0.

Three distinct problems are reported separately, because the fix differs:

  * duplicate real values  -> Solve adjudicates which user keeps the number
  * duplicate empty strings -> normalize '' to NULL first; MySQL allows many
    NULLs in a unique index but treats '' as an ordinary, colliding value
  * whitespace/case variants -> not caught by a plain unique index at all
    (MySQL's default collation is case-insensitive, but ' 123' != '123'),
    reported as a warning so they can be normalized before the constraint
    locks in the inconsistency

Usage:
    venv/bin/python scripts/check_rullenummer_duplicates.py
"""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Deliberately no os.environ.setdefault("DB_TYPE", ...) here: config.py's
# load_dotenv() does not override an already-set env var, so forcing a
# default here BEFORE .env loads would silently shadow a real DB_TYPE=mysql
# in production and redirect every query to an empty local SQLite file
# instead (this bit us once — see TODO_forensic_audit.md Task 0.1). Let
# config.py's own load_dotenv() + its own internal default handle it.


def main():
    from config import AppConfig
    from app.database import get_db_session
    from app.models import DBUser

    # Print which DB this is actually about to hit — a wrong DB_TYPE here
    # (e.g. accidentally defaulting to sqlite in production) fails loudly
    # instead of silently querying an unrelated empty database.
    print(f"DB_TYPE={AppConfig.DB_TYPE}")

    db = get_db_session()
    try:
        users = db.query(DBUser.id, DBUser.username, DBUser.rullenummer).all()

        total = len(users)
        nulls = [u for u in users if u.rullenummer is None]
        empties = [u for u in users if u.rullenummer is not None and u.rullenummer.strip() == ""]
        real = [u for u in users if u.rullenummer is not None and u.rullenummer.strip() != ""]

        print(f"{total} user(s): {len(real)} with a rullenummer, "
              f"{len(nulls)} NULL, {len(empties)} empty string")
        print("=" * 60)

        problems = 0

        # --- Duplicate real values (the exposure risk) ---
        by_value = {}
        for u in real:
            by_value.setdefault(u.rullenummer, []).append(u)
        dupes = {v: us for v, us in by_value.items() if len(us) > 1}

        if dupes:
            problems += 1
            print(f"DUPLICATE rullenummer — {len(dupes)} value(s) shared by 2+ users:")
            for value, us in sorted(dupes.items()):
                print(f"  '{value}' -> {len(us)} users:")
                for u in us:
                    print(f"      id={u.id} username={u.username}")
            print("  ACTION: decide which user keeps each number, clear the others,")
            print("          THEN run the migration.")
            print()
        else:
            print("OK: no duplicate rullenummer values.")

        # --- Empty strings (would collide under a unique index) ---
        if len(empties) > 1:
            problems += 1
            print(f"EMPTY STRING rullenummer on {len(empties)} users — these collide")
            print("  with each other under a unique index (only NULL is exempt):")
            for u in empties:
                print(f"      id={u.id} username={u.username}")
            print("  ACTION: normalize to NULL before migrating, e.g.")
            print("          UPDATE users SET rullenummer = NULL WHERE rullenummer = '';")
            print()
        elif empties:
            print("OK: 1 empty-string rullenummer (harmless alone, but worth normalizing).")
        else:
            print("OK: no empty-string rullenummer.")

        # --- Whitespace / case variants a unique index would NOT catch ---
        by_normalized = {}
        for u in real:
            by_normalized.setdefault(u.rullenummer.strip().lower(), []).append(u)
        near = {
            n: us for n, us in by_normalized.items()
            if len(us) > 1 and len({u.rullenummer for u in us}) > 1
        }
        if near:
            print(f"WARNING: {len(near)} rullenummer(s) differ only by whitespace/case.")
            print("  A unique index would accept these as distinct while the")
            print("  innplassering join may still mismatch:")
            for n, us in sorted(near.items()):
                variants = sorted({repr(u.rullenummer) for u in us})
                print(f"  normalized '{n}': {', '.join(variants)}")
            print("  ACTION: normalize before migrating (not a blocker on its own).")
            print()

        print("=" * 60)
        if problems:
            print("NOT SAFE to add the unique index yet — fix the items above first.")
            sys.exit(1)

        print("SAFE to add the unique index on users.rullenummer.")
        sys.exit(0)
    finally:
        db.close()


if __name__ == "__main__":
    main()
