"""Drop the single-column unique index on shifts.title

Revision ID: 005_shifts_drop_title_unique
Revises: 004_shifts_title_unique_fix
Create Date: 2026-02-23

Migration 004 used batch_alter_table but the anonymous UNIQUE(title) constraint
survived because batch_alter_table reflects the existing schema (including that
constraint) before applying operations.

This migration rebuilds the shifts table using raw SQL so we have full control
over which constraints are kept:  only UNIQUE(title, turnus_set_id) survives.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005_shifts_drop_title_unique"
down_revision: Union[str, None] = "004_shifts_title_unique_fix"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE shifts_new (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            title VARCHAR(255) NOT NULL,
            turnus_set_id INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT uq_shifts_title_turnus_set UNIQUE (title, turnus_set_id)
        )
    """)
    op.execute("INSERT INTO shifts_new (id, title, turnus_set_id) SELECT id, title, turnus_set_id FROM shifts")
    op.execute("DROP TABLE shifts")
    op.execute("ALTER TABLE shifts_new RENAME TO shifts")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE shifts_old (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            title VARCHAR(255) NOT NULL UNIQUE,
            turnus_set_id INTEGER NOT NULL DEFAULT 1,
            CONSTRAINT uq_shifts_title_turnus_set UNIQUE (title, turnus_set_id)
        )
    """)
    op.execute("INSERT INTO shifts_old (id, title, turnus_set_id) SELECT id, title, turnus_set_id FROM shifts")
    op.execute("DROP TABLE shifts")
    op.execute("ALTER TABLE shifts_old RENAME TO shifts")
