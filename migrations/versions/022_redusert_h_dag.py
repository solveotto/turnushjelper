"""redusert_stilling.h_dag_jobb — whether the driver works the tur's H-dag

Revision ID: 022_redusert_h_dag
Revises: 021_redusert_stilling
Create Date: 2026-11-03

Adds one column to the plan table and touches nothing else. Existing plans get
0, the default: the H-dag isn't worked.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_redusert_h_dag"
down_revision: Union[str, None] = "021_redusert_stilling"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("redusert_stilling") as batch_op:
        batch_op.add_column(
            sa.Column("h_dag_jobb", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("redusert_stilling") as batch_op:
        batch_op.drop_column("h_dag_jobb")
