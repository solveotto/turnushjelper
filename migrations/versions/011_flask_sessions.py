"""add flask_sessions table

Revision ID: 011_flask_sessions
Revises: 010_add_performance_indexes
Create Date: 2026-05-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_flask_sessions"
down_revision: Union[str, None] = "010_add_performance_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "flask_sessions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(255), unique=True, nullable=False),
        sa.Column("data", sa.LargeBinary, nullable=False),
        sa.Column("expiry", sa.DateTime, nullable=False),
    )
    op.create_index("ix_flask_sessions_expiry", "flask_sessions", ["expiry"])


def downgrade() -> None:
    op.drop_index("ix_flask_sessions_expiry", table_name="flask_sessions")
    op.drop_table("flask_sessions")
