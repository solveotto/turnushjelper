#!/usr/bin/env python3
"""List the most favourited turnuser in a turnus set.

Usage:
    venv/bin/python scripts/top_favorites.py              # active set, top 10
    venv/bin/python scripts/top_favorites.py --year R26
    venv/bin/python scripts/top_favorites.py --limit 20
    venv/bin/python scripts/top_favorites.py --ans-fra 100   # ans.nr 100 and further down the list
    venv/bin/python scripts/top_favorites.py --ans-til 100   # ans.nr 1-100
    venv/bin/python scripts/top_favorites.py --favoritter 3  # only each user's first 3

Ansiennitetsnummer 1 is the most senior. With either --ans option set, users
without a seniority number are left out.
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
    parser.add_argument("--ans-fra", type=int, help="Only users with ansiennitetsnr >= this")
    parser.add_argument("--ans-til", type=int, help="Only users with ansiennitetsnr <= this")
    parser.add_argument("--favoritter", type=int,
                        help="Only count each user's first N favourites (default: all)")
    args = parser.parse_args()

    from collections import Counter, defaultdict

    from config import AppConfig
    from app.database import get_db_session
    from app.models import DBUser, Favorites, TurnusSet

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

        filters = [Favorites.turnus_set_id == turnus_set.id]
        if args.ans_fra is not None:
            filters.append(DBUser.seniority_nr >= args.ans_fra)
        if args.ans_til is not None:
            filters.append(DBUser.seniority_nr <= args.ans_til)

        favorites = (
            db_session.query(Favorites.user_id, Favorites.shift_title)
            .join(DBUser, DBUser.id == Favorites.user_id)
            .filter(*filters)
            .order_by(Favorites.user_id, Favorites.order_index, Favorites.id)
            .all()
        )
    finally:
        db_session.close()

    # Rank by position, not by order_index itself: the values can have gaps
    # and legacy duplicates (see api.py reorder).
    per_user = defaultdict(list)
    for user_id, title in favorites:
        per_user[user_id].append(title)

    # (user_id, shift_title, turnus_set_id) is unique, so each title counts once per user.
    counts = Counter()
    for titles in per_user.values():
        counts.update(titles[:args.favoritter])

    total_users = len(per_user)
    rows = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:args.limit]

    ans_text = ""
    if args.ans_fra is not None or args.ans_til is not None:
        fra = args.ans_fra if args.ans_fra is not None else 1
        til = args.ans_til if args.ans_til is not None else ""
        ans_text = f", ansiennitet {fra}-{til}"
    fav_text = f", første {args.favoritter} favoritter" if args.favoritter else ""
    print(f"\n{turnus_set.name} ({turnus_set.year_identifier}{ans_text}{fav_text}): "
          f"{total_users} brukere med favoritter\n")
    if not rows:
        print("Ingen favoritter.")
        return

    width = max(len("Turnus"), *(len(title) for title, _ in rows))
    print(f"{'#':>3}  {'Turnus':<{width}}  {'Antall':>6}  {'Andel':>6}")
    for rank, (title, antall) in enumerate(rows, start=1):
        andel = antall / total_users * 100 if total_users else 0
        print(f"{rank:>3}  {title:<{width}}  {antall:>6}  {andel:>5.0f}%")


if __name__ == "__main__":
    main()
