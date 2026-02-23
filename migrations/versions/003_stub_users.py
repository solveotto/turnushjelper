"""Add stub user columns to users table

Revision ID: 003_stub_users
Revises: 002_authorized_emails_rullenummer_only
Create Date: 2026-02-22

Changes:
- users.is_stub: Integer default 0 (1 = not yet registered via self-registration)
- users.stasjoneringssted: String(100) nullable
- users.ans_dato: String(20) nullable  (hire date DD.MM.YYYY)
- users.fodt_dato: String(20) nullable (birth date DD.MM.YYYY)
- users.seniority_nr: Integer nullable (position in seniority list)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_stub_users"
down_revision: Union[str, None] = "002_authorized_emails_rullenummer_only"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("is_stub", sa.Integer(), nullable=True, server_default="0")
        )
        batch_op.add_column(
            sa.Column("stasjoneringssted", sa.String(100), nullable=True)
        )
        batch_op.add_column(sa.Column("ans_dato", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("fodt_dato", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("seniority_nr", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("seniority_nr")
        batch_op.drop_column("fodt_dato")
        batch_op.drop_column("ans_dato")
        batch_op.drop_column("stasjoneringssted")
        batch_op.drop_column("is_stub")
