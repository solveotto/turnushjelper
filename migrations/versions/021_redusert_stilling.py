"""redusert_stilling — a driver's plan for a reduced position on Min Tur

Revision ID: 021_redusert_stilling
Revises: 020_strekliste_nr_length
Create Date: 2026-11-02

Adds one table and touches nothing else. Autogenerate also proposes dropping
indexes and altering columns on existing tables, because the models and the
migrated schema have drifted apart. None of that belongs here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_redusert_stilling"
down_revision: Union[str, None] = "020_strekliste_nr_length"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "redusert_stilling",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("turnus_set_id", sa.Integer(), nullable=False),
        sa.Column("shift_title", sa.String(length=255), nullable=False),
        sa.Column("prosent", sa.Float(), nullable=True),
        sa.Column("fjernet", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["turnus_set_id"], ["turnus_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "turnus_set_id", "shift_title", name="uq_redusert_stilling"
        ),
    )


def downgrade() -> None:
    op.drop_table("redusert_stilling")
