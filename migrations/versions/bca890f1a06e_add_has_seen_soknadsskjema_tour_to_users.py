"""add has_seen_soknadsskjema_tour to users

Revision ID: bca890f1a06e
Revises: e912fb42ff8b
Create Date: 2026-04-30 11:49:43.261000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bca890f1a06e'
down_revision: Union[str, None] = 'e912fb42ff8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('has_seen_soknadsskjema_tour', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'has_seen_soknadsskjema_tour')
