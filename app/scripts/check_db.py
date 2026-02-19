#!/usr/bin/env python3
"""Check database connectivity and table contents.

Tables are managed by Alembic — run `alembic upgrade head` to create them.
"""

import sys
import os

# Add project root to path (go up 3 levels: scripts -> app -> project_root)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from app.database import get_db_session
from app.models import DBUser, Favorites, Shifts
from app.services.user_service import create_new_user

def check_database():
    try:
        session = get_db_session()
        try:
            user_count = session.query(DBUser).count()
            favorites_count = session.query(Favorites).count()
            shifts_count = session.query(Shifts).count()

            print(f"Database connection successful")
            print(f"  - Users: {user_count}")
            print(f"  - Favorites: {favorites_count}")
            print(f"  - Shifts: {shifts_count}")

        finally:
            session.close()

    except Exception as e:
        print(f"Database error: {e}")
        print("Have you run 'alembic upgrade head' to create the tables?")

if __name__ == "__main__":
    check_database()
    create_new_user('admin', 'admin', is_auth=1)
