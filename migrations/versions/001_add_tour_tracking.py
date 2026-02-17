"""add turnusliste tour tracking column

Revision ID: 001_add_tour_tracking
Revises:
Create Date: 2026-02-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_add_tour_tracking"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tour tracking column — default 0 means "not yet seen"
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("has_seen_turnusliste_tour", sa.Integer(), nullable=True, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("has_seen_turnusliste_tour")
