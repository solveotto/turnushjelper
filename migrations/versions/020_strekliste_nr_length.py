"""strekliste_dagsverk.nr and dobbelt_tur — room for R27's longer duty labels

Revision ID: 020_strekliste_nr_length
Revises: 019_strekliste_dobbelt_tur
Create Date: 2026-10-22

R26's longest printed duty label was 17 characters; R27 prints up to 22
("1208-mod_1___N05_13_17"), which MySQL refused for nr String(20) while
SQLite in development had accepted it. nr goes to 60 and dobbelt_tur, which
holds two labels joined by "<<", to 130. Batch mode so SQLite can run it too.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_strekliste_nr_length"
down_revision: Union[str, None] = "019_strekliste_dobbelt_tur"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("strekliste_dagsverk") as batch_op:
        batch_op.alter_column(
            "nr", existing_type=sa.String(length=20), type_=sa.String(length=60),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "dobbelt_tur", existing_type=sa.String(length=30), type_=sa.String(length=130),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("strekliste_dagsverk") as batch_op:
        batch_op.alter_column(
            "dobbelt_tur", existing_type=sa.String(length=130), type_=sa.String(length=30),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "nr", existing_type=sa.String(length=60), type_=sa.String(length=20),
            existing_nullable=False,
        )
