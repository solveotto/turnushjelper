"""make users.rullenummer unique

Revision ID: 017_unique_rullenummer
Revises: 016_add_fk_constraints
Create Date: 2026-07-20

Innplassering rows join to users on the rullenummer *string*
(app/services/innplassering_service.py), so two users sharing a rullenummer
means one sees the other's innplassering data. App-level collision checks
exist in activate_stub_user, create_user_with_email and update_user, but any
future write path that forgets the check reintroduces the exposure. This
enforces it in the database instead.

Migration 015 already created ix_users_rullenummer as a NON-unique index for
lookup speed. This replaces it in place with a unique one — the unique index
serves lookups equally well, so nothing is lost and no redundant second index
is left behind.

NULL is exempt: both MySQL and SQLite allow multiple NULLs in a unique index,
so the 75 users without a rullenummer are unaffected. Empty string is NOT
exempt — it is an ordinary colliding value.

IMPORTANT: Before running this on production, verify there are no duplicates:
    venv/bin/python scripts/check_rullenummer_duplicates.py
It must exit 0. Verified clean on STAGING 2026-07-20 (395 users, 320 with a
rullenummer, 0 duplicates, 0 empty strings) and applied there. Re-run the
check against PRODUCTION immediately before upgrading prod — users register
between snapshots, so a stale audit is not a guarantee.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "017_unique_rullenummer"
down_revision: Union[str, None] = "016_add_fk_constraints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_users_rullenummer", table_name="users")
    op.create_index("ix_users_rullenummer", "users", ["rullenummer"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_rullenummer", table_name="users")
    op.create_index("ix_users_rullenummer", "users", ["rullenummer"])
