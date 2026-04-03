"""add mintur and compare tour seen columns

Revision ID: fd3bdd7dac06
Revises: 009_add_favorites_tour_tracking
Create Date: 2026-04-03 13:29:02.914387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd3bdd7dac06'
down_revision: Union[str, None] = '009_add_favorites_tour_tracking'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('has_seen_mintur_tour', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('has_seen_compare_tour', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'has_seen_compare_tour')
    op.drop_column('users', 'has_seen_mintur_tour')
