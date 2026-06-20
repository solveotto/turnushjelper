"""Add not_on_nlf_list column to users table

Revision ID: 013_add_not_on_nlf_list
Revises: 012_add_medlemsnummer
Create Date: 2026-06-19

Changes:
- users.not_on_nlf_list: Integer nullable — set to 1 by NLF sync when a user
  is not found in the member list Excel; cleared when they reappear. Blocks login.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013_add_not_on_nlf_list"
down_revision: Union[str, None] = "012_add_medlemsnummer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("not_on_nlf_list", sa.Integer, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("not_on_nlf_list")
