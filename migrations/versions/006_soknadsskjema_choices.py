"""Add soknadsskjema_choices table for per-user Kolonne 2 & 4 selections

Revision ID: 006_soknadsskjema_choices
Revises: 005_shifts_drop_title_unique
Create Date: 2026-02-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_soknadsskjema_choices"
down_revision: Union[str, None] = "005_shifts_drop_title_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "soknadsskjema_choices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("turnus_set_id", sa.Integer(), nullable=False),
        sa.Column("shift_title", sa.String(255), nullable=False),
        sa.Column("linje_135", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linje_246", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linjeprioritering", sa.String(255), nullable=True),
        sa.Column("h_dag", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "user_id", "turnus_set_id", "shift_title",
            name="uq_soknadsskjema_choices",
        ),
    )


def downgrade() -> None:
    op.drop_table("soknadsskjema_choices")
