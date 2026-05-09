"""add performance indexes

Revision ID: 010_add_performance_indexes
Revises: bca890f1a06e
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "010_add_performance_indexes"
down_revision: Union[str, None] = "bca890f1a06e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_favorites_user_ts", "favorites", ["user_id", "turnus_set_id"])
    op.create_index("ix_innplassering_ts_rullenr", "innplassering", ["turnus_set_id", "rullenummer"])
    op.create_index("ix_user_activity_timestamp", "user_activity", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_favorites_user_ts", table_name="favorites")
    op.drop_index("ix_innplassering_ts_rullenr", table_name="innplassering")
    op.drop_index("ix_user_activity_timestamp", table_name="user_activity")
