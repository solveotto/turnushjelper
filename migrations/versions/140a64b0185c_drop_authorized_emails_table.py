"""drop authorized_emails table

Revision ID: 140a64b0185c
Revises: 013_add_not_on_nlf_list
Create Date: 2026-06-20 07:41:25.336346

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '140a64b0185c'
down_revision: Union[str, None] = '013_add_not_on_nlf_list'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('authorized_emails')


def downgrade() -> None:
    op.create_table(
        'authorized_emails',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('rullenummer', sa.String(50), nullable=True),
        sa.Column('added_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('added_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rullenummer', name='unique_rullenummer'),
    )
