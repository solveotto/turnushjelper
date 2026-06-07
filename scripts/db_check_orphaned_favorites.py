#!/usr/bin/env python3
"""
Check for orphaned favorites before adding foreign keys
"""
import sys
import os

project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from app.utils.db_utils import get_db_session, Favorites, DBUser, TurnusSet

def check_orphaned_favorites():
    """Check for favorites with invalid user_id or turnus_set_id"""
    session = get_db_session()
    
    try:
        print("Checking for orphaned favorites...")
        print("=" * 60)
        
        # Check for orphaned user_id
        orphaned_users = session.query(Favorites).filter(
            ~Favorites.user_id.in_(session.query(DBUser.id))
        ).all()
        
        if orphaned_users:
            print(f"\n⚠ WARNING: Found {len(orphaned_users)} favorites with invalid user_id:")
            for fav in orphaned_users[:10]:  # Show first 10
                print(f"  - Favorite ID {fav.id}: user_id={fav.user_id} (user doesn't exist)")
            if len(orphaned_users) > 10:
                print(f"  ... and {len(orphaned_users) - 10} more")
        else:
            print("✓ No orphaned user_id found")
        
        # Check for orphaned turnus_set_id
        orphaned_turnus = session.query(Favorites).filter(
            ~Favorites.turnus_set_id.in_(session.query(TurnusSet.id))
        ).all()
        
        if orphaned_turnus:
            print(f"\n⚠ WARNING: Found {len(orphaned_turnus)} favorites with invalid turnus_set_id:")
            for fav in orphaned_turnus[:10]:
                print(f"  - Favorite ID {fav.id}: turnus_set_id={fav.turnus_set_id} (turnus_set doesn't exist)")
            if len(orphaned_turnus) > 10:
                print(f"  ... and {len(orphaned_turnus) - 10} more")
        else:
            print("✓ No orphaned turnus_set_id found")
        
        print("\n" + "=" * 60)
        
        total_orphaned = len(orphaned_users) + len(orphaned_turnus)
        
        if total_orphaned > 0:
            print(f"\n⚠ TOTAL ORPHANED RECORDS: {total_orphaned}")
            print("\nYou must clean these up before adding foreign keys.")
            print("Run the cleanup script: python scripts/db_cleanup_orphaned_favorites.py")
            return False
        else:
            print("\n✓ Database is clean - safe to add foreign keys!")
            return True
            
    finally:
        session.close()

if __name__ == '__main__':
    check_orphaned_favorites()