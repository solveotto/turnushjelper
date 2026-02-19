"""Re-export facade for backward compatibility.

All models, database infrastructure, and service functions have been
extracted into dedicated modules during Phase 3 refactoring:

  - app.database          — Base, engine, SessionLocal, get_db_session
  - app.models            — DBUser, AuthorizedEmails, EmailVerificationToken, TurnusSet, Favorites, Shifts
  - app.services.turnus_service    — turnus set CRUD
  - app.services.user_service      — user management
  - app.services.favorites_service — favorites management
  - app.services.auth_service      — auth, tokens, password reset

Existing imports like ``from app.utils import db_utils`` or
``from app.utils.db_utils import DBUser`` continue to work via this file.
"""

# Database infrastructure
from app.database import Base, engine, SessionLocal, get_db_session  # noqa: F401

# ORM models
from app.models import (  # noqa: F401
    DBUser, AuthorizedEmails, EmailVerificationToken,
    TurnusSet, Favorites, Shifts,
)

# Turnus service
from app.services.turnus_service import (  # noqa: F401
    create_turnus_set, get_all_turnus_sets, get_turnus_set_by_year,
    get_turnus_set_by_id, set_active_turnus_set, get_active_turnus_set,
    add_shifts_to_turnus_set, get_shifts_by_turnus_set, delete_turnus_set,
    update_turnus_set_paths, refresh_turnus_set_shifts,
)

# User service
from app.services.user_service import (  # noqa: F401
    hash_password, create_new_user, get_user_data, get_user_password,
    get_user_by_email, get_user_by_username, create_user_with_email,
    get_all_users, get_user_by_id, create_user, update_user,
    delete_user, toggle_user_auth, update_user_password,
)

# Favorites service
from app.services.favorites_service import (  # noqa: F401
    get_favorite_lst, user_has_favorites_in_other_sets,
    update_favorite_order, get_max_ordered_index,
    cleanup_duplicate_favorites, add_favorite, remove_favorite,
)

# Auth service
from app.services.auth_service import (  # noqa: F401
    is_email_authorized, add_authorized_email, get_all_authorized_emails,
    delete_authorized_email, create_verification_token, verify_token,
    can_send_verification_email, update_verification_sent_time,
    create_password_reset_token, verify_password_reset_token,
    reset_user_password, can_send_password_reset_email,
)
