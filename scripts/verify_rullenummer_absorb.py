#!/usr/bin/env python3
"""One-off staging check: does sync_members_from_excel survive the unique
rullenummer index (migration 017)?

The unique index is passive; the code path it can break is the twin-absorb in
sync_members_from_excel, which copies a rullenummer from a duplicate stub onto
the kept user and then deletes the stub. Before the fix, an autoflush during
that delete left both rows holding the same value and violated the index.
A service restart does NOT exercise this — only a member import does. This
reproduces exactly that path against the real (MySQL) DB, then cleans up.

Safe on a shared DB: it seeds two throwaway rows with sentinel medlemsnummer/
rullenummer values, passes a one-row member list (users not on the list are
never touched — see sync_members_from_excel docstring), verifies the absorb,
and deletes its own rows in a finally block. It does NOT touch real users.

Usage (on staging):
    venv/bin/python scripts/verify_rullenummer_absorb.py
Exit 0 = absorb worked, index intact. Non-zero = something is wrong; read it.
"""

import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# No os.environ.setdefault("DB_TYPE", ...) — see check_7th_drivers.py for why.

# Sentinels unlikely to collide with real data.
TEST_MNR = "999999001"
TEST_RULLENR = "ZZ99001"
TEST_ANS_DATO = "01.01.2099"


def main():
    from config import AppConfig
    from app.database import get_db_session
    from app.models import DBUser
    from app.services import user_service

    print(f"DB_TYPE={AppConfig.DB_TYPE}")
    db = get_db_session()

    seeded_ids = []
    try:
        # Guard: refuse to run if the sentinels already exist (a prior crashed
        # run) — don't compound the mess.
        existing = (
            db.query(DBUser)
            .filter(
                (DBUser.medlemsnummer == TEST_MNR)
                | (DBUser.rullenummer == TEST_RULLENR)
                | (DBUser.username.in_(["__test_target_absorb", "__test_stub_absorb"]))
            )
            .all()
        )
        if existing:
            print("ABORT: sentinel rows already present (leftover from a failed run):")
            for u in existing:
                print(f"  id={u.id} username={u.username} "
                      f"mnr={u.medlemsnummer} rullenr={u.rullenummer}")
            print("Delete these manually, then re-run.")
            sys.exit(2)

        # Registered target user with the medlemsnummer but NO rullenummer yet.
        target = DBUser(
            username="__test_target_absorb",
            password=user_service.hash_password("x"),
            name="Testesen, Absorb",
            medlemsnummer=TEST_MNR,
            is_stub=0,
            is_auth=0,
            email_verified=0,
        )
        # Duplicate stub, same normalized name, holding the rullenummer that
        # must move onto the target.
        stub = DBUser(
            username="__test_stub_absorb",
            password=user_service.hash_password("x"),
            name="Testesen, Absorb",
            rullenummer=TEST_RULLENR,
            ans_dato=TEST_ANS_DATO,
            is_stub=1,
            is_auth=0,
            email_verified=0,
        )
        db.add(target)
        db.add(stub)
        db.commit()
        seeded_ids = [target.id, stub.id]
        print(f"Seeded target id={target.id}, duplicate stub id={stub.id} "
              f"(both name 'Testesen, Absorb', stub holds rullenummer {TEST_RULLENR})")

        # Run the REAL sync with a one-row list. This is the exact code path a
        # member-list import takes; the twin-absorb fires and (pre-fix) crashes.
        report = user_service.sync_members_from_excel([{
            "name": "Testesen, Absorb",
            "medlemsnummer": TEST_MNR,
            "ans_dato": TEST_ANS_DATO,
        }])
        print(f"sync report: matched={report.get('matched')} "
              f"updated={report.get('updated')} "
              f"deleted_stubs={report.get('deleted_stubs')} "
              f"conflicts={report.get('conflicts')}")

        # Verify: target now owns the rullenummer, the stub is gone.
        db.expire_all()
        target = db.query(DBUser).filter_by(medlemsnummer=TEST_MNR).first()
        stub_still = db.query(DBUser).filter_by(username="__test_stub_absorb").first()

        ok = True
        if target is None:
            print("FAIL: target user vanished"); ok = False
        elif target.rullenummer != TEST_RULLENR:
            print(f"FAIL: rullenummer did not move — target has "
                  f"{target.rullenummer!r}, expected {TEST_RULLENR!r}"); ok = False
        else:
            print(f"OK: rullenummer {TEST_RULLENR} moved onto target id={target.id}")
        if stub_still is not None:
            print(f"FAIL: duplicate stub id={stub_still.id} was not absorbed"); ok = False
        else:
            print("OK: duplicate stub absorbed (deleted)")

        if ok:
            print("=" * 60)
            print("PASS: member-import absorb works against the unique index.")
            sys.exit(0)
        else:
            print("=" * 60)
            print("FAIL: see above.")
            sys.exit(1)

    except Exception as e:
        print(f"ERROR during absorb: {type(e).__name__}: {e}")
        print("If this is an IntegrityError on users.rullenummer, the fix did "
              "NOT land on this server — do not migrate prod.")
        db.rollback()
        sys.exit(1)
    finally:
        # Clean up whatever survived, by sentinel, regardless of outcome.
        try:
            leftovers = (
                db.query(DBUser)
                .filter(
                    (DBUser.medlemsnummer == TEST_MNR)
                    | (DBUser.rullenummer == TEST_RULLENR)
                    | (DBUser.username.in_(
                        ["__test_target_absorb", "__test_stub_absorb"]))
                )
                .all()
            )
            for u in leftovers:
                db.delete(u)
            db.commit()
            if leftovers:
                print(f"Cleaned up {len(leftovers)} test row(s).")
        except Exception as ce:
            print(f"WARNING: cleanup failed: {ce}")
            print(f"  Manually delete users with medlemsnummer={TEST_MNR} / "
                  f"rullenummer={TEST_RULLENR} / usernames __test_*_absorb.")
        finally:
            db.close()


if __name__ == "__main__":
    main()
