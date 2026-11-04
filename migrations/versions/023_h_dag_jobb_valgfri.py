"""redusert_stilling.h_dag_jobb can be empty, meaning not chosen on Min Tur

Revision ID: 023_h_dag_jobb_valgfri
Revises: 022_redusert_h_dag
Create Date: 2026-11-04

While it's empty, the driver's søknadsskjema answer decides whether the H-dag is
worked. Existing 0s become empty, because 022 wrote 0 for everyone who hadn't
chosen. Touches only this column.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023_h_dag_jobb_valgfri"
down_revision: Union[str, None] = "022_redusert_h_dag"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("redusert_stilling") as batch_op:
        batch_op.alter_column(
            "h_dag_jobb", existing_type=sa.Integer(), nullable=True, server_default=None
        )
    op.execute("UPDATE redusert_stilling SET h_dag_jobb = NULL WHERE h_dag_jobb = 0")


def downgrade() -> None:
    op.execute("UPDATE redusert_stilling SET h_dag_jobb = 0 WHERE h_dag_jobb IS NULL")
    with op.batch_alter_table("redusert_stilling") as batch_op:
        batch_op.alter_column(
            "h_dag_jobb", existing_type=sa.Integer(), nullable=False, server_default="0"
        )
