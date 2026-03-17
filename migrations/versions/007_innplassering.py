"""Add innplassering table for shift assignment data from Innplassering PDF

Revision ID: 007_innplassering
Revises: 006_soknadsskjema_choices
Create Date: 2026-03-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "007_innplassering"
down_revision: Union[str, None] = "006_soknadsskjema_choices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "innplassering",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("turnus_set_id", sa.Integer(), sa.ForeignKey("turnus_sets.id"), nullable=False),
        sa.Column("rullenummer", sa.String(20), nullable=False),
        sa.Column("shift_title", sa.String(255), nullable=False),
        sa.Column("linjenummer", sa.Integer(), nullable=True),
        sa.Column("ans_nr", sa.Integer(), nullable=True),
        sa.Column("is_7th_driver", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("turnus_set_id", "rullenummer", name="uq_innplassering_turnus_rullenr"),
    )


def downgrade() -> None:
    op.drop_table("innplassering")
