"""Add medlemsnummer column to users table

Revision ID: 012_add_medlemsnummer
Revises: 011_flask_sessions
Create Date: 2026-06-11

Changes:
- users.medlemsnummer: String(20) nullable, unique index
  (NLF member number — replaces rullenummer as the registration identifier)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "012_add_medlemsnummer"
down_revision: Union[str, None] = "011_flask_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("medlemsnummer", sa.String(20), nullable=True))
    op.create_index("ix_users_medlemsnummer", "users", ["medlemsnummer"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_medlemsnummer", table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("medlemsnummer")
