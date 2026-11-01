#!/usr/bin/env python3
"""List the most favourited turnuser in a turnus set.

Usage:
    venv/bin/python scripts/top_favorites.py              # active set, top 10
    venv/bin/python scripts/top_favorites.py --year R26
    venv/bin/python scripts/top_favorites.py --limit 20
"""

import argparse
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def main() -> None:
    parser = argparse.ArgumentParser(description="Most favourited turnuser")
    parser.add_argument("--year", help="Year identifier, e.g. R26 (default: active set)")
    parser.add_argument("--limit", type=int, default=10, help="How many to show (default 10)")
    args = parser.parse_args()

    from sqlalchemy import func

    from config import AppConfig
    from app.database import get_db_session
    from app.models import Favorites, TurnusSet

    print(f"DB_TYPE={AppConfig.DB_TYPE}")

    db_session = get_db_session()
    try:
        query = db_session.query(TurnusSet)
        if args.year:
            turnus_set = query.filter_by(year_identifier=args.year.upper()).first()
        else:
            turnus_set = query.filter_by(is_active=1).first()
        if not turnus_set:
            print(f"Error: no turnus set found ({args.year or 'active'})")
            sys.exit(1)

        total_users = (
            db_session.query(func.count(func.distinct(Favorites.user_id)))
            .filter(Favorites.turnus_set_id == turnus_set.id)
            .scalar()
        )

        # (user_id, shift_title, turnus_set_id) is unique, so each row is one user.
        rows = (
            db_session.query(Favorites.shift_title, func.count(Favorites.id).label("antall"))
            .filter(Favorites.turnus_set_id == turnus_set.id)
            .group_by(Favorites.shift_title)
            .order_by(func.count(Favorites.id).desc(), Favorites.shift_title)
            .limit(args.limit)
            .all()
        )
    finally:
        db_session.close()

    print(f"\n{turnus_set.name} ({turnus_set.year_identifier}): "
          f"{total_users} brukere med favoritter\n")
    if not rows:
        print("Ingen favoritter.")
        return

    width = max(len(title) for title, _ in rows)
    print(f"{'#':>3}  {'Turnus':<{width}}  {'Antall':>6}  {'Andel':>6}")
    for rank, (title, antall) in enumerate(rows, start=1):
        andel = antall / total_users * 100 if total_users else 0
        print(f"{rank:>3}  {title:<{width}}  {antall:>6}  {andel:>5.0f}%")


if __name__ == "__main__":
    main()
