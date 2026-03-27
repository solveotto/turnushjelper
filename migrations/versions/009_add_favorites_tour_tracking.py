"""add favorites tour tracking column

Revision ID: 009_add_favorites_tour_tracking
Revises: 008_user_activity
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009_add_favorites_tour_tracking"
down_revision: Union[str, None] = "008_user_activity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("has_seen_favorites_tour", sa.Integer(), nullable=True, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("has_seen_favorites_tour")
