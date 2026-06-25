"""add indexes on users.email, rullenummer, is_stub and user_activity.user_id

Revision ID: 015_add_indexes
Revises: 014_mysql_session_blob
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "015_add_indexes"
down_revision: Union[str, None] = "014_mysql_session_blob"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_rullenummer", "users", ["rullenummer"])
    op.create_index("ix_users_is_stub", "users", ["is_stub"])
    op.create_index("ix_user_activity_user_id", "user_activity", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_rullenummer", table_name="users")
    op.drop_index("ix_users_is_stub", table_name="users")
    op.drop_index("ix_user_activity_user_id", table_name="user_activity")
