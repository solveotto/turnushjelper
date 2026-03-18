"""Add user_activity table for tracking logins, logouts, and favorite changes

Revision ID: 008_user_activity
Revises: 007_innplassering
Create Date: 2026-03-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008_user_activity"
down_revision: Union[str, None] = "007_innplassering"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_activity",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("details", sa.String(255), nullable=True),
        sa.Column("session_duration_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_activity")
