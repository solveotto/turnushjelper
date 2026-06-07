#!/usr/bin/env python3
"""
Clean up orphaned favorites before adding foreign keys
"""
import sys
import os

project_root = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from app.utils.db_utils import get_db_session, Favorites, DBUser, TurnusSet

def cleanup_orphaned_favorites():
    """Remove favorites with invalid user_id or turnus_set_id"""
    session = get_db_session()
    
    try:
        # Find orphaned records
        orphaned_users = session.query(Favorites).filter(
            ~Favorites.user_id.in_(session.query(DBUser.id))
        ).all()
        
        orphaned_turnus = session.query(Favorites).filter(
            ~Favorites.turnus_set_id.in_(session.query(TurnusSet.id))
        ).all()
        
        total = len(orphaned_users) + len(orphaned_turnus)
        
        if total == 0:
            print("✓ No orphaned records found")
            return
        
        print(f"\nFound {total} orphaned favorites:")
        print(f"  - {len(orphaned_users)} with invalid user_id")
        print(f"  - {len(orphaned_turnus)} with invalid turnus_set_id")
        
        response = input("\nDelete these orphaned records? (yes/no): ")
        
        if response.lower() == 'yes':
            # Delete orphaned records
            for fav in orphaned_users + orphaned_turnus:
                session.delete(fav)
            
            session.commit()
            print(f"\n✓ Deleted {total} orphaned favorites")
        else:
            print("\nCleanup cancelled")
            
    except Exception as e:
        session.rollback()
        print(f"✗ Error during cleanup: {e}")
        raise
    finally:
        session.close()

if __name__ == '__main__':
    cleanup_orphaned_favorites()