"""Fix shifts.title unique constraint — composite only

Revision ID: 004_shifts_title_unique_fix
Revises: 003_stub_users
Create Date: 2026-02-23

The shifts table was originally created with two overlapping unique constraints:
  1. unique=True on the title column alone  → prevents the same shift name from
     appearing in more than one turnus set (wrong behaviour)
  2. UniqueConstraint('title', 'turnus_set_id')  → the correct per-set constraint

This migration drops constraint #1 so that shift names are only unique *within*
a turnus set, allowing e.g. OSL_Ramme_03 to exist in both R25 and R26.

SQLite does not support DROP CONSTRAINT directly; we use batch_alter_table which
recreates the table without the offending index.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004_shifts_title_unique_fix"
down_revision: Union[str, None] = "003_stub_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table recreates the table, giving us full control over
    # which constraints survive.  We keep only the composite (title, turnus_set_id).
    with op.batch_alter_table("shifts", recreate="always") as batch_op:
        batch_op.alter_column("title", existing_type=sa.String(255), nullable=False)
        # The batch recreate drops all existing indexes; we re-add only the
        # composite one via create_unique_constraint.
        batch_op.create_unique_constraint("uq_shifts_title_turnus_set", ["title", "turnus_set_id"])


def downgrade() -> None:
    # Restore the original (broken) state: both constraints back.
    with op.batch_alter_table("shifts", recreate="always") as batch_op:
        batch_op.create_unique_constraint("uq_shifts_title_turnus_set", ["title", "turnus_set_id"])
        batch_op.create_unique_constraint("uq_shifts_title", ["title"])
