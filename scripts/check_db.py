#!/usr/bin/env python3
"""Check database connectivity and table contents.

Tables are managed by Alembic — run `alembic upgrade head` to create them.
"""

import sys
import os

# Add project root to path (go up 2 levels: scripts -> project_root)
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from sqlalchemy import exc

from app.database import get_db_session
from app.models import DBUser, Favorites, Innplassering, RedusertStilling, Shifts, SoknadsskjemaChoice

def check_database():
    try:
        session = get_db_session()
        try:
            user_count = session.query(DBUser).count()
            favorites_count = session.query(Favorites).count()
            shifts_count = session.query(Shifts).count()
            choices_count = session.query(SoknadsskjemaChoice).count()
            placements_count = session.query(Innplassering).count()
            # Counted apart, so a host can take its baseline before migrating
            # and a migration that didn't run shows up here afterwards.
            try:
                plans_count = session.query(RedusertStilling).count()
            except exc.DBAPIError:
                session.rollback()
                plans_count = "table missing, run 'alembic upgrade head'"

            print(f"Database connection successful")
            print(f"  - Users: {user_count}")
            print(f"  - Favorites: {favorites_count}")
            print(f"  - Shifts: {shifts_count}")
            print(f"  - Søknadsskjema choices: {choices_count}")
            print(f"  - Placements: {placements_count}")
            print(f"  - Reduced-position plans: {plans_count}")

        finally:
            session.close()

    except Exception as e:
        print(f"Database error: {e}")
        print("Have you run 'alembic upgrade head' to create the tables?")

if __name__ == "__main__":
    check_database()
