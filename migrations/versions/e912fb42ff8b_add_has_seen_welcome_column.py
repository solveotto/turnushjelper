"""add has_seen_welcome column

Revision ID: e912fb42ff8b
Revises: fd3bdd7dac06
Create Date: 2026-04-04 07:34:50.873432

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e912fb42ff8b'
down_revision: Union[str, None] = 'fd3bdd7dac06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('has_seen_welcome', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'has_seen_welcome')
