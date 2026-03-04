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
    # Drop the anonymous single-column UNIQUE(title) index if it exists.
    # On MySQL we can't use AUTOINCREMENT (SQLite syntax) so we drop the index directly.
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        # Inspect existing indexes and drop any single-column unique index on title
        result = bind.execute(sa.text("SHOW INDEX FROM shifts WHERE Column_name='title' AND Non_unique=0"))
        indexes = {row[2] for row in result}  # Key_name is column 2
        for index_name in indexes:
            if index_name != "uq_shifts_title_turnus_set":
                bind.execute(sa.text(f"DROP INDEX `{index_name}` ON shifts"))
    else:
        # SQLite path: recreate table
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
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        bind.execute(sa.text("CREATE UNIQUE INDEX title ON shifts (title)"))
    else:
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
