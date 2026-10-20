"""strekliste_dagsverk.dobbelt_tur — which pair a split double duty came from

Revision ID: 019_strekliste_dobbelt_tur
Revises: 018_strekliste_tables
Create Date: 2026-10-20

A strekliste row marked ``<<`` (3006<<3007) holds two duties, one in the
afternoon and the other the next morning. The parser splits it into two
duties that both carry the pair label here. Added as its own revision
because 018 had already run on production when the column was introduced.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_strekliste_dobbelt_tur"
down_revision: Union[str, None] = "018_strekliste_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "strekliste_dagsverk",
        sa.Column("dobbelt_tur", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strekliste_dagsverk", "dobbelt_tur")
